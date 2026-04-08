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


def _is_dress_row(row: Dict[str, Any]) -> bool:
    product_title = str(row.get("product_title") or "").strip().lower()
    return "dress" in product_title


def select_dress_rows(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    dresses = [row for row in rows if _is_dress_row(row)]
    return dresses[: max(0, limit)]


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
    categories_query = build_annual_categories_query(year=year, limit=limit)

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
