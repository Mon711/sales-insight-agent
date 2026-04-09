"""
Annual product and category reporting via ShopifyQL.
"""

from __future__ import annotations

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
          WHERE product_title IS NOT NULL
          GROUP BY product_title, product_variant_price WITH TOTALS
          SINCE {since} UNTIL {until}
          ORDER BY net_sales {direction}
          LIMIT {limit}
    """


def build_annual_categories_query(*, year: int, limit: int = 20) -> str:
    """
    Build the exact top-categories query requested by the user.
    """
    since, until = _year_bounds(year)
    return f"""
        FROM sales
          SHOW net_sales, net_items_sold
          GROUP BY product_type WITH TOTALS
          SINCE {since} UNTIL {until}
          ORDER BY net_sales DESC
          LIMIT {limit}
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


def _annotate_average_selling_price(rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        net_sales = _to_float(row.get("net_sales"))
        items = _to_float(row.get("net_items_sold"))
        row["average_selling_price"] = round((net_sales / items), 2) if items else 0.0


def _normalize_category_name(raw_value: Any) -> str:
    cleaned = str(raw_value or "").strip()
    lowered = cleaned.lower()
    if lowered in {"dress", "dresses"}:
        return "Dress"
    return cleaned or "Uncategorized"


def _combine_category_rows(rows: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    combined: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        normalized_name = _normalize_category_name(row.get("product_type"))
        bucket = combined.setdefault(
            normalized_name,
            {
                "product_type": normalized_name,
                "net_sales": 0.0,
                "net_items_sold": 0.0,
            },
        )
        bucket["net_sales"] += _to_float(row.get("net_sales"))
        bucket["net_items_sold"] += _to_float(row.get("net_items_sold"))

    combined_rows = list(combined.values())
    combined_rows.sort(key=lambda row: _to_float(row.get("net_sales")), reverse=True)

    for row in combined_rows:
        row["net_sales"] = round(_to_float(row.get("net_sales")), 2)
        items_sold = _to_float(row.get("net_items_sold"))
        row["net_items_sold"] = int(items_sold) if items_sold.is_integer() else round(items_sold, 2)

    return combined_rows[: max(0, limit)]


def select_ranked_rows(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    """Return the first N rows preserving ranking order from ShopifyQL."""
    return list(rows[: max(0, limit)])


def run_annual_report(
    *,
    client: ShopifyGraphQLClient,
    year: int = 2025,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Run the three annual report queries (top products, underperformers, categories).
    """
    top_query = build_annual_products_query(year=year, descending=True, limit=limit)
    under_query = build_annual_products_query(year=year, descending=False, limit=limit)
    categories_query = build_annual_categories_query(year=year, limit=250)

    top_response = client.run_shopifyql_report(top_query)
    under_response = client.run_shopifyql_report(under_query)
    categories_response = client.run_shopifyql_report(categories_query)

    for label, response in [
        ("top performers", top_response),
        ("underperformers", under_response),
        ("top categories", categories_response),
    ]:
        if response.get("parseErrors"):
            raise ValueError(f"ShopifyQL parse error in {label}: {response['parseErrors']}")

    top_rows = parse_product_rows(top_response)
    under_rows = parse_product_rows(under_response)
    category_rows = parse_product_rows(categories_response)

    _clean_totals_columns(top_rows)
    _clean_totals_columns(under_rows)
    _clean_totals_columns(category_rows)
    _annotate_average_selling_price(top_rows)
    _annotate_average_selling_price(under_rows)
    category_rows = _combine_category_rows(category_rows, limit=limit)

    return {
        "year": year,
        "queries": {
            "top_performers": top_query.strip(),
            "underperformers": under_query.strip(),
            "top_categories": categories_query.strip(),
        },
        "top_performers": top_rows,
        "underperformers": under_rows,
        "top_categories": category_rows,
    }
