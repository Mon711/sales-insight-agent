"""
Season-aware product reporting helpers.

This module builds a season-specific ShopifyQL query, fetches product-level sales
rows, and enriches the selected rows with local product images so the downstream
report can do true image-led analysis.
"""

from __future__ import annotations

from copy import deepcopy
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


def _empty_product_detail_enrichment_summary() -> Dict[str, Any]:
    """Return the product detail enrichment summary contract."""
    return {
        "product_ids_seen": 0,
        "product_details_found": 0,
        "product_details_missing": 0,
        "official_materials_found": 0,
        "official_fabric_compositions_found": 0,
        "official_colours_found": 0,
        "official_fit_fields_found": 0,
        "metafield_access_ok": False,
        "errors": [],
    }


def _matching_variant_for_row(
    product_detail: Dict[str, Any],
    row: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Return the product variant matching the ShopifyQL SKU row, when present."""
    row_sku = str(row.get("product_variant_sku") or "").strip()
    if not row_sku:
        return None
    for variant in product_detail.get("variants") or []:
        if str(variant.get("sku") or "").strip() == row_sku:
            return variant
    return None


def _attach_product_detail_to_rows(
    *,
    client: ShopifyGraphQLClient,
    rows: List[Dict[str, Any]],
    product_access_ok: bool,
    product_access_error: Optional[str],
) -> Dict[str, Any]:
    """
    Attach official Admin GraphQL product details to ShopifyQL rows.

    This enrichment is intentionally non-fatal. ShopifyQL remains the commercial
    source of truth even when Product API detail fields are unavailable.
    """
    summary = _empty_product_detail_enrichment_summary()
    if not product_access_ok:
        summary["errors"].append(f"Product API unavailable: {product_access_error}")
        for row in rows:
            row["product_detail"] = None
        return summary

    gid_to_rows: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        product_gid = client.to_product_gid(row.get("product_id"))
        if not product_gid:
            row["product_detail"] = None
            continue
        gid_to_rows.setdefault(product_gid, []).append(row)

    summary["product_ids_seen"] = len(gid_to_rows)
    if not gid_to_rows:
        summary["metafield_access_ok"] = True
        return summary

    try:
        records = client.fetch_product_detail_records_by_ids(list(gid_to_rows.keys()))
        summary["metafield_access_ok"] = True
    except Exception as exc:
        summary["errors"].append(f"Product detail enrichment failed: {exc}")
        for row_group in gid_to_rows.values():
            for row in row_group:
                row["product_detail"] = None
        return summary

    summary["product_details_found"] = len(records)
    summary["product_details_missing"] = max(0, len(gid_to_rows) - len(records))

    for product_gid, row_group in gid_to_rows.items():
        product_detail = records.get(product_gid)
        for row in row_group:
            if not product_detail:
                row["product_detail"] = None
                continue
            row_detail = deepcopy(product_detail)
            matching_variant = _matching_variant_for_row(row_detail, row)
            if matching_variant:
                row_detail["selected_option_values"] = matching_variant.get("selected_options") or {}
                row_detail["selected_variant"] = matching_variant
            row["product_detail"] = row_detail

    for record in records.values():
        attrs = record.get("official_product_attributes") or {}
        if attrs.get("official_material_text"):
            summary["official_materials_found"] += 1
        if attrs.get("official_fabric_composition") not in [None, "", "Unknown"]:
            summary["official_fabric_compositions_found"] += 1
        if attrs.get("official_colour"):
            summary["official_colours_found"] += 1
        if attrs.get("official_fit"):
            summary["official_fit_fields_found"] += 1

    return summary


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
    product_detail_summary = _attach_product_detail_to_rows(
        client=client,
        rows=rows,
        product_access_ok=product_access_ok,
        product_access_error=product_access_error,
    )
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
            "product_detail_enrichment_summary": product_detail_summary,
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
        "product_detail_enrichment_summary": product_detail_summary,
        "product_count": len(rows),
        "product_access_ok": product_access_ok,
        "product_access_error": product_access_error,
    }
