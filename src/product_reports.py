"""
Annual product and dress-variant reporting via ShopifyQL.
"""

from __future__ import annotations

import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List

from .shopify_client import ShopifyGraphQLClient


def _year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"


def build_annual_products_query(*, year: int, descending: bool = True, limit: int = 20) -> str:
    """
    Build the exact top/underperforming products query requested by the user.
    """
    since, until = _year_bounds(year)
    direction = "DESC" if descending else "ASC"
    return f"""
        FROM sales
          SHOW net_sales, net_items_sold, gross_sales, average_order_value,
            returned_quantity_rate
          WHERE product_variant_title IS NOT NULL
          GROUP BY product_title WITH TOTALS
          SINCE {since} UNTIL {until}
          ORDER BY net_sales {direction}
          LIMIT {limit}
        VISUALIZE net_sales TYPE list
    """


def build_annual_all_products_query(*, year: int) -> str:
    """
    Build the consolidated product ranking query used for broader analysis.
    """
    since, until = _year_bounds(year)
    return f"""
        FROM sales
          SHOW net_items_sold, net_sales
          GROUP BY product_title WITH TOTALS
          SINCE {since} UNTIL {until}
          ORDER BY net_items_sold DESC
        VISUALIZE net_items_sold
    """


def build_annual_dress_variant_query(*, year: int) -> str:
    """
    Build the raw dress-variant query that returns all rows for later grouping.
    """
    since, until = _year_bounds(year)
    return f"""
        FROM sales
          SHOW product_id, net_sales, net_items_sold, gross_sales, returns
          WHERE product_variant_title_at_time_of_sale IS NOT NULL
            AND product_title CONTAINS 'Dress'
          GROUP BY product_id, product_title, product_variant_title WITH TOTALS
          SINCE {since} UNTIL {until}
          ORDER BY net_sales DESC
        VISUALIZE net_sales
    """


def parse_product_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    return response.get("tableData", {}).get("rows", [])


def _clean_totals_columns(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        for key in list(row.keys()):
            if key.endswith("__totals"):
                del row[key]


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _round_half_up(value: Any, places: int = 2) -> float:
    quantizer = Decimal("1").scaleb(-places)
    return float(Decimal(str(value)).quantize(quantizer, rounding=ROUND_HALF_UP))


_SIZE_TOKEN_PATTERN = re.compile(
    r"^(?:"
    r"\d{1,2}(?:\s*(?:year|years|yr|yrs|month|months|mo|m))?|"
    r"\d{1,2}|"
    r"xxs|xxsized|xs|x-small|xsmall|small|s|"
    r"medium|m|large|l|x-large|xlarge|xl|"
    r"xxl|2xl|3xl|xx-large|xxlarge|one size|onesize|one-size"
    r")$",
    flags=re.IGNORECASE,
)


def _normalize_variant_segment(segment: str) -> str:
    normalized = segment.strip().lower().replace(".", "")
    normalized = re.sub(r"[\s_-]+", "", normalized)
    return normalized


def _is_size_only_segment(segment: str) -> bool:
    return bool(_SIZE_TOKEN_PATTERN.match(_normalize_variant_segment(segment)))


def _normalize_variant_family_title(raw_title: Any) -> str:
    text = str(raw_title or "").strip()
    if not text:
        return "Unspecified"

    segments = [part.strip() for part in re.split(r"\s*/\s*", text) if part.strip()]
    kept_segments = [segment for segment in segments if not _is_size_only_segment(segment)]

    if not kept_segments:
        return "Unspecified"

    return " / ".join(kept_segments)


def select_ranked_rows(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """Return the first N rows preserving ranking order from ShopifyQL."""
    return list(rows[: max(0, limit)])


def _is_dress_row(row: Dict[str, Any]) -> bool:
    title = str(row.get("product_title") or "").strip().lower()
    return "dress" in title


def _finalize_metric(value: float) -> float | int:
    decimal_value = Decimal(str(value))
    if decimal_value == decimal_value.to_integral():
        return int(decimal_value)
    return _round_half_up(value, places=2)


def _aggregate_dress_variant_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[tuple[str, str], Dict[str, Any]] = {}

    for row in rows:
        if not _is_dress_row(row):
            continue

        product_title = str(row.get("product_title") or "").strip() or "Uncategorized"
        variant_family = _normalize_variant_family_title(
            row.get("product_variant_title")
            or row.get("product_variant_title_at_time_of_sale")
            or ""
        )
        product_id = str(row.get("product_id") or "").strip() or None
        key = (product_title, variant_family)
        bucket = grouped.setdefault(
            key,
            {
                "product_title": product_title,
                "product_variant_family": variant_family,
                "product_id": product_id,
                "net_sales": 0.0,
                "net_items_sold": 0.0,
                "gross_sales": 0.0,
                "returns": 0.0,
                "_aov_weighted_sum": 0.0,
                "_aov_weight_total": 0.0,
                "_source_row_count": 0,
            },
        )

        net_items = _to_float(row.get("net_items_sold"))
        bucket["net_sales"] += _to_float(row.get("net_sales"))
        bucket["net_items_sold"] += net_items
        bucket["gross_sales"] += _to_float(row.get("gross_sales"))
        bucket["returns"] += _to_float(row.get("returns"))
        if not bucket.get("product_id") and product_id:
            bucket["product_id"] = product_id
        bucket["_source_row_count"] += 1

    aggregated_rows: List[Dict[str, Any]] = []
    for row in grouped.values():
        row.pop("_source_row_count", None)
        row["net_sales"] = _round_half_up(row["net_sales"], places=2)
        row["net_items_sold"] = _finalize_metric(_to_float(row["net_items_sold"]))
        row["gross_sales"] = _round_half_up(row["gross_sales"], places=2)
        row["returns"] = _round_half_up(row["returns"], places=2)
        aggregated_rows.append(row)

    aggregated_rows.sort(key=lambda row: _to_float(row.get("net_sales")), reverse=True)
    return aggregated_rows


def _rank_variant_rows(rows: List[Dict[str, Any]], limit: int = 20) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    ranked = list(rows)
    limit_count = max(0, limit)
    top_rows = ranked[:limit_count]
    bottom_rows = list(reversed(ranked[-limit_count:])) if limit_count else []
    return top_rows, bottom_rows


def run_annual_report(
    *,
    client: ShopifyGraphQLClient,
    year: int = 2025,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Run the annual report queries (top products, underperformers, all products sold, dress variants).
    """
    top_query = build_annual_products_query(year=year, descending=True, limit=limit)
    under_query = build_annual_products_query(year=year, descending=False, limit=limit)
    all_products_query = build_annual_all_products_query(year=year)
    dress_variants_query = build_annual_dress_variant_query(year=year)

    top_response = client.run_shopifyql_report(top_query)
    under_response = client.run_shopifyql_report(under_query)
    all_products_response = client.run_shopifyql_report(all_products_query)
    dress_variants_response = client.run_shopifyql_report(dress_variants_query)

    for label, response in [
        ("top performers", top_response),
        ("underperformers", under_response),
        ("all products sold", all_products_response),
        ("dress variant families", dress_variants_response),
    ]:
        if response.get("parseErrors"):
            raise ValueError(f"ShopifyQL parse error in {label}: {response['parseErrors']}")

    top_rows = parse_product_rows(top_response)
    under_rows = parse_product_rows(under_response)
    all_products_rows = parse_product_rows(all_products_response)
    dress_variant_rows = parse_product_rows(dress_variants_response)

    _clean_totals_columns(top_rows)
    _clean_totals_columns(under_rows)
    _clean_totals_columns(all_products_rows)
    _clean_totals_columns(dress_variant_rows)
    grouped_dress_variant_rows = _aggregate_dress_variant_rows(dress_variant_rows)
    top_dress_variants, bottom_dress_variants = _rank_variant_rows(grouped_dress_variant_rows, limit=20)

    return {
        "year": year,
        "queries": {
            "top_performers": top_query.strip(),
            "underperformers": under_query.strip(),
            "all_products_sold": all_products_query.strip(),
            "dress_variant_families": dress_variants_query.strip(),
        },
        "top_performers": top_rows,
        "underperformers": under_rows,
        "all_products_sold": {
            "query_year": year,
            "ranking": "net_items_sold_desc",
            "rows": all_products_rows,
            "note": "Consolidated by product title with size and color variants combined.",
        },
        "dress_variant_families": {
            "query_year": year,
            "ranking": "grouped_variant_net_sales_desc",
            "rows": grouped_dress_variant_rows,
            "top_rows": top_dress_variants,
            "bottom_rows": bottom_dress_variants,
            "note": "Grouped by product title plus normalized variant family after stripping size-only segments.",
        },
    }
