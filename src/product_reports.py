"""
Product-level sales reports by sub-channel using ShopifyQL.

This module fetches top products per sub-channel to support:
- Design team collection planning decisions
- Product performance analysis across channels/sub-channels
- Revenue contribution tracking per product

Products are ranked by net_sales (or gross_sales for wholesale where net=$0).
Each product includes true_net_sales after deducting sub-channel commission rates.
"""

from typing import Dict, Any, List
from .shopify_client import ShopifyGraphQLClient
from .config import (
    REPORT_SINCE,
    REPORT_UNTIL,
    SUB_CHANNEL_CONFIG,
    get_active_sub_channels,
    EXCLUDED_CHANNELS,
    EXCLUDED_TAGS,
)


def build_product_query(
    channel_key: str,
    config: Dict[str, Any],
    since: str,
    until: str,
    limit: int = 1000,
    include_product_id: bool = False,
) -> str:
    """
    Build a ShopifyQL product query for a specific sub-channel.

    Handles specialized logic for POS and generic logic for others:
    - POS: Detailed location-based query with total_sales ranking.
    - Other channels: Standard title/revenue query.
    """
    
    group_fields = ["product_title", "product_type"]
    if include_product_id:
        group_fields.append("product_id")

    metric_fields = [
        "orders",
        "net_items_sold",
        "gross_sales",
        "discounts",
        "returns",
        "net_sales",
        "taxes",
        "total_sales",
    ]
    show_clause = ", ".join(group_fields + metric_fields)
    group_by_clause = ", ".join(group_fields)

    # 1. Specialized POS query
    if channel_key == "pos":
        return f"""
            FROM sales
            SHOW 
                {show_clause}
            WHERE 
                is_pos_sale = true 
                AND line_type = 'product' 
                AND product_title IS NOT NULL
            GROUP BY 
                {group_by_clause} WITH TOTALS
            SINCE {since} UNTIL {until}
            ORDER BY 
                total_sales DESC
            LIMIT {limit}
        """

    # 2. Generic query logic for other channels
    filter_type = config.get("filter_type")
    
    # Define fields and sorting
    # We use a consistent set of fields across all channels for better AI analysis
    order_by = "total_sales DESC"

    # Specialized logic for Online Store (Multi-channel + Exclusions)
    if channel_key == "online_store":
        where_clause = "sales_channel IN ('Online Store', 'Shop', 'Facebook & Instagram') AND line_type = 'product' AND product_title IS NOT NULL AND order_tags NOT CONTAINS 'Manymoons' AND order_tags NOT CONTAINS 'shopmy'"
        
    # Specialized logic for Wholesale (Tag-based)
    elif channel_key == "wholesale":
        where_clause = "order_tags CONTAINS 'wholesale' AND line_type = 'product' AND product_title IS NOT NULL"

    # Generic logic for any other tag-based channel (Dropshippers)
    elif filter_type == "order_tag":
        tag = config.get("tag")
        if not tag:
            raise ValueError(f"Channel {channel_key} has no tag defined in config.")
        where_clause = f"order_tags CONTAINS '{tag}' AND line_type = 'product' AND product_title IS NOT NULL"

    # Default logic for others (like individual dropship channels)
    elif filter_type == "sales_channel":
        channel = config.get("shopify_channel")
        if not channel:
            raise ValueError(f"Channel {channel_key} has no shopify_channel defined.")
        where_clause = f"sales_channel = '{channel}' AND line_type = 'product' AND product_title IS NOT NULL"

    else:
        raise ValueError(f"Unknown filter_type: {filter_type} for channel {channel_key}")

    return f"""
        FROM sales
        SHOW {show_clause}
        WHERE {where_clause}
        GROUP BY {group_by_clause} WITH TOTALS
        SINCE {since} UNTIL {until}
        ORDER BY {order_by}
        LIMIT {limit}
    """


def parse_product_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract product rows from a ShopifyQL response."""
    return response.get("tableData", {}).get("rows", [])


def run_product_report(
    client: ShopifyGraphQLClient,
    channel_key: str,
    config: Dict[str, Any],
    since: str = REPORT_SINCE,
    until: str = REPORT_UNTIL,
    limit: int = 1000,
    include_product_id: bool = False,
) -> List[Dict[str, Any]]:
    """
    Fetch and parse top products for a specific sub-channel.
    """
    try:
        query = build_product_query(
            channel_key=channel_key,
            config=config,
            since=since,
            until=until,
            limit=limit,
            include_product_id=include_product_id,
        )
        print(f"  [PRODUCTS] Fetching top {limit} products for {channel_key}...")

        response = client.run_shopifyql_report(query)

        if response.get("parseErrors"):
            print(f"    ⚠ ShopifyQL parse error: {response['parseErrors']}")
            return []

        rows = parse_product_rows(response)

        # Compute true_net_sales and wholesale-specific logic
        commission_rate = config.get("commission_rate", 0.0)
        for row in rows:
            # Standard calculation for all channels
            net_val = float(row.get("net_sales", 0) or 0)
            true_net = net_val * (1 - commission_rate)
            row["true_net_sales"] = round(true_net, 2)
            
            # Specialized Wholesale logic: net_sale = gross_sale / 2
            if channel_key == "wholesale":
                gross_val = float(row.get("gross_sales", 0) or 0)
                row["estimated_net_sales"] = round(gross_val / 2, 2)

        print(f"    ✓ {len(rows)} products fetched")
        return rows

    except Exception as e:
        print(f"    ✗ Error fetching products for {channel_key}: {e}")
        return []


def run_all_product_reports(
    client: ShopifyGraphQLClient,
    since: str = REPORT_SINCE,
    until: str = REPORT_UNTIL,
    limit: int = 1000,
    include_product_id: bool = False,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch product reports for all active sub-channels.
    """
    print(f"\n[PRODUCTS] Fetching top products by sub-channel ({since} → {until})...")

    all_products = {}
    active_channels = get_active_sub_channels()

    for channel_key in active_channels:
        config = SUB_CHANNEL_CONFIG.get(channel_key)
        if not config:
            print(f"  ⚠ Skipping {channel_key} — not found in config")
            continue

        products = run_product_report(
            client=client,
            channel_key=channel_key,
            config=config,
            since=since,
            until=until,
            limit=limit,
            include_product_id=include_product_id,
        )
        all_products[channel_key] = products

    return all_products


def _year_bounds(year: int) -> tuple[str, str]:
    return f"{year}-01-01", f"{year}-12-31"


def _annual_product_where_clause() -> str:
    clauses = [
        "line_type = 'product'",
        "product_title IS NOT NULL",
    ]
    for channel in EXCLUDED_CHANNELS:
        clauses.append(f"sales_channel != '{channel}'")
    for tag in EXCLUDED_TAGS:
        clauses.append(f"order_tags NOT CONTAINS '{tag}'")
    return " AND ".join(clauses)


def _annual_category_where_clause() -> str:
    clauses = [
        "line_type = 'product'",
        "product_type IS NOT NULL",
    ]
    for channel in EXCLUDED_CHANNELS:
        clauses.append(f"sales_channel != '{channel}'")
    for tag in EXCLUDED_TAGS:
        clauses.append(f"order_tags NOT CONTAINS '{tag}'")
    return " AND ".join(clauses)


def build_annual_products_query(
    *,
    year: int,
    limit: int = 20,
    descending: bool = True,
    include_product_id: bool = False,
    include_product_variant_price: bool = True,
    return_metric: str = "returned_quantity_rate",
) -> str:
    """
    Build annual top/underperforming products query.
    """
    since, until = _year_bounds(year)
    order_direction = "DESC" if descending else "ASC"

    group_fields = ["product_title"]
    if include_product_variant_price:
        group_fields.append("product_variant_price")
    if include_product_id:
        group_fields.append("product_id")

    metrics = [
        "net_sales",
        "net_items_sold",
        "gross_sales",
        "average_order_value",
        return_metric,
    ]

    show_clause = ", ".join(group_fields + metrics)
    group_by_clause = ", ".join(group_fields)
    where_clause = _annual_product_where_clause()
    return f"""
        FROM sales
        SHOW {show_clause}
        WHERE {where_clause}
        GROUP BY {group_by_clause} WITH TOTALS
        SINCE {since} UNTIL {until}
        ORDER BY net_sales {order_direction}
        LIMIT {limit}
    """


def build_annual_categories_query(*, year: int, limit: int = 20) -> str:
    """
    Build annual top categories query.
    """
    since, until = _year_bounds(year)
    where_clause = _annual_category_where_clause()
    return f"""
        FROM sales
        SHOW net_sales, net_items_sold
        WHERE {where_clause}
        GROUP BY product_type WITH TOTALS
        SINCE {since} UNTIL {until}
        ORDER BY net_sales DESC
        LIMIT {limit}
    """


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
    product_type = str(row.get("product_type") or "").strip().lower()
    product_title = str(row.get("product_title") or "").strip().lower()
    return product_type == "dress" or "dress" in product_title


def select_dress_rows(rows: List[Dict[str, Any]], limit: int = 5) -> List[Dict[str, Any]]:
    dress_rows = [row for row in rows if _is_dress_row(row)]
    return dress_rows[: max(0, limit)]


def run_annual_report(
    *,
    client: ShopifyGraphQLClient,
    year: int = 2025,
    limit: int = 20,
    include_product_id: bool = False,
) -> Dict[str, Any]:
    """
    Execute annual top/bottom/category queries and normalize rows.
    """
    categories_query = build_annual_categories_query(year=year, limit=limit)
    categories_resp = client.run_shopifyql_report(categories_query)
    if categories_resp.get("parseErrors"):
        raise ValueError(f"ShopifyQL parse error in top categories: {categories_resp['parseErrors']}")

    query_attempts = [
        {"include_product_variant_price": True, "return_metric": "returned_quantity_rate"},
        {"include_product_variant_price": True, "return_metric": "returns"},
        {"include_product_variant_price": False, "return_metric": "returns"},
    ]

    top_resp = None
    under_resp = None
    selected_attempt = None
    parse_errors: List[Any] = []

    for attempt in query_attempts:
        top_query = build_annual_products_query(
            year=year,
            limit=limit,
            descending=True,
            include_product_id=include_product_id,
            include_product_variant_price=attempt["include_product_variant_price"],
            return_metric=attempt["return_metric"],
        )
        under_query = build_annual_products_query(
            year=year,
            limit=limit,
            descending=False,
            include_product_id=include_product_id,
            include_product_variant_price=attempt["include_product_variant_price"],
            return_metric=attempt["return_metric"],
        )

        top_resp = client.run_shopifyql_report(top_query)
        under_resp = client.run_shopifyql_report(under_query)

        top_errors = top_resp.get("parseErrors")
        under_errors = under_resp.get("parseErrors")
        if not top_errors and not under_errors:
            selected_attempt = attempt
            break

        parse_errors.append(
            {
                "attempt": attempt,
                "top_parse_errors": top_errors,
                "under_parse_errors": under_errors,
            }
        )

    if selected_attempt is None or top_resp is None or under_resp is None:
        raise ValueError(f"ShopifyQL parse error in product ranking queries: {parse_errors}")

    top_rows = parse_product_rows(top_resp)
    under_rows = parse_product_rows(under_resp)
    category_rows = parse_product_rows(categories_resp)

    _clean_totals_columns(top_rows)
    _clean_totals_columns(under_rows)
    _clean_totals_columns(category_rows)
    _annotate_average_selling_price(top_rows)
    _annotate_average_selling_price(under_rows)

    return {
        "year": year,
        "query_capabilities": {
            "return_metric": selected_attempt["return_metric"],
            "includes_product_variant_price": selected_attempt["include_product_variant_price"],
            "includes_product_id": include_product_id,
        },
        "top_performers": top_rows,
        "underperformers": under_rows,
        "top_categories": category_rows,
    }
