"""
Season-aware product reporting helpers.

This module builds a season-specific ShopifyQL query, fetches product-level sales
rows, and enriches the selected rows with local product images so the downstream
report can do true image-led analysis.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from .image_enrichment import (
    enrich_channel_product_rows,
    mark_channel_image_enrichment_skipped,
)
from .product_reports import _clean_totals_columns, parse_product_rows, select_ranked_rows
from .season_profiles import SeasonProfile
from .shopify_client import ShopifyGraphQLClient


ImageEnrichmentFn = Callable[..., Tuple[Dict[str, Any], List[Dict[str, Any]]]]
ImageSkipFn = Callable[..., Tuple[Dict[str, Any], List[Dict[str, Any]]]]


def _quoted(value: str) -> str:
    """Return a single-quoted ShopifyQL string literal."""
    return value.replace("'", "\\'")


def build_season_products_query(
    *,
    season_profile: SeasonProfile,
    include_product_id: bool = True,
    include_variant_sku: bool = True,
    limit: int | None = None,
) -> str:
    """
    Build a season-level product performance query.

    The query intentionally keeps the output row-granularity at product/variant
    level so the report can pair quantitative performance with visual analysis.
    """
    show_fields = [
        "net_sales",
        "gross_sales",
        "net_items_sold",
        "returns",
        "returned_quantity_rate",
        "discounts",
        "product_title",
    ]
    group_fields = [
        "product_title",
    ]

    if include_variant_sku:
        show_fields.append("product_variant_sku")
        group_fields.append("product_variant_sku")

    show_fields.append("product_type")
    group_fields.append("product_type")

    if include_product_id:
        show_fields.append("product_id")
        group_fields.append("product_id")

    query_lines = [
        "FROM sales",
        f"  SHOW {', '.join(show_fields)}",
        f"  WHERE product_tags CONTAINS '{_quoted(season_profile.shopify_tag)}'",
        "    AND product_title IS NOT NULL",
        f"  GROUP BY {', '.join(group_fields)} WITH TOTALS",
        f"  SINCE {season_profile.since} UNTIL {season_profile.until}",
        "  ORDER BY net_sales DESC",
    ]
    if limit is not None:
        query_lines.append(f"  LIMIT {max(0, int(limit))}")
    return "\n".join(query_lines)


def _candidate_query_configs() -> List[Tuple[bool, bool]]:
    """Return query variants ordered from richest context to simplest fallback."""
    return [
        (True, True),
        (False, True),
        (True, False),
        (False, False),
    ]


def _run_season_query_with_fallbacks(
    *,
    client: ShopifyGraphQLClient,
    season_profile: SeasonProfile,
) -> Tuple[str, Dict[str, Any], Dict[str, bool]]:
    """
    Execute the season query, falling back to a simpler field set if ShopifyQL
    rejects a product field that is unavailable in the current store.
    """
    candidates = _candidate_query_configs()
    try:
        product_id_supported = client.probe_shopifyql_product_id_support(
            season_profile.since,
            season_profile.until,
        )
        if product_id_supported:
            candidates = [(True, True), (False, True), (True, False), (False, False)]
        else:
            candidates = [(False, True), (False, False), (True, True), (True, False)]
    except Exception:
        # If the probe fails, fall back to the default ordered attempts.
        pass

    seen: set[Tuple[bool, bool]] = set()
    last_parse_errors: Any = None
    for include_product_id, include_variant_sku in candidates:
        config = (include_product_id, include_variant_sku)
        if config in seen:
            continue
        seen.add(config)

        query = build_season_products_query(
            season_profile=season_profile,
            include_product_id=include_product_id,
            include_variant_sku=include_variant_sku,
        )
        response = client.run_shopifyql_report(query)
        parse_errors = response.get("parseErrors")
        if not parse_errors:
            return query, response, {
                "include_product_id": include_product_id,
                "include_variant_sku": include_variant_sku,
            }
        last_parse_errors = parse_errors

    raise ValueError(
        "ShopifyQL parse error in season query: "
        f"{last_parse_errors or 'unknown error'}"
    )


def _bottom_ranked_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    """Return the worst-ranked rows from a net-sales-sorted list."""
    if limit <= 0:
        return []
    sliced = rows[-limit:]
    return list(reversed(sliced))


def run_season_report(
    *,
    client: ShopifyGraphQLClient,
    brand_slug: str,
    season_profile: SeasonProfile,
    report_output_dir: str,
    image_enrichment_fn: ImageEnrichmentFn = enrich_channel_product_rows,
    image_skip_fn: ImageSkipFn = mark_channel_image_enrichment_skipped,
) -> Dict[str, Any]:
    """
    Run the season report query and enrich all returned rows with images.

    The resulting JSON is the analysis-ready source of truth for the downstream
    markdown report generator.
    """
    query, response, query_flags = _run_season_query_with_fallbacks(
        client=client,
        season_profile=season_profile,
    )

    rows = parse_product_rows(response)
    _clean_totals_columns(rows)

    product_access_ok, product_access_error = client.check_read_products_access()
    image_channel_key = f"{brand_slug}_{season_profile.slug}"
    top_limit = len(rows)

    if product_access_ok:
        image_summary, image_index_rows = image_enrichment_fn(
            client=client,
            channel_key=image_channel_key,
            product_rows=rows,
            generation_dir=report_output_dir,
            top_limit=top_limit,
        )
    else:
        reason = f"Product API unavailable: {product_access_error}"
        image_summary, image_index_rows = image_skip_fn(
            product_rows=rows,
            reason=reason,
            top_limit=top_limit,
        )

    ranked_rows = list(rows)
    top_rows = select_ranked_rows(ranked_rows, limit=min(20, len(ranked_rows)))
    bottom_rows = _bottom_ranked_rows(ranked_rows, limit=min(20, len(ranked_rows)))
    top_10_rows = select_ranked_rows(ranked_rows, limit=min(10, len(ranked_rows)))
    bottom_10_rows = _bottom_ranked_rows(ranked_rows, limit=min(10, len(ranked_rows)))

    generated_at = datetime.now(timezone.utc).isoformat()

    return {
        "generated_at": generated_at,
        "brand": {
            "slug": brand_slug,
        },
        "season": {
            "slug": season_profile.slug,
            "display_name": season_profile.display_name,
            "shopify_tag": season_profile.shopify_tag,
        },
        "report_period": {
            "since": season_profile.since,
            "until": season_profile.until,
        },
        "report_name": f"{brand_slug}_{season_profile.slug}_season_performance",
        "queries": {
            "season_products": query.strip(),
        },
        "query_flags": query_flags,
        "season_product_performance": {
            "query_year": None,
            "ranking": "net_sales_desc",
            "image_enrichment_summary": image_summary,
            "rows": rows,
            "top_20_rows": top_rows,
            "bottom_20_rows": bottom_rows,
            "note": (
                "Season-level product rows sorted by net sales descending. "
                "All rows were image-enriched where product access was available."
            ),
        },
        "product_image_focus": {
            "top_10_products": top_10_rows,
            "bottom_10_products": bottom_10_rows,
            "note": (
                "Representative views for narrative analysis. "
                "The downstream report should still inspect the full season rows."
            ),
        },
        "product_image_index": image_index_rows,
        "product_count": len(rows),
        "product_access_ok": product_access_ok,
        "product_access_error": product_access_error,
    }
