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
from .config import REPORT_SINCE, REPORT_UNTIL, SUB_CHANNEL_CONFIG, get_active_sub_channels


def build_product_query(
    channel_key: str,
    config: Dict[str, Any],
    since: str,
    until: str,
    limit: int = 1000,
) -> str:
    """
    Build a ShopifyQL product query for a specific sub-channel.

    Handles specialized logic for POS and generic logic for others:
    - POS: Detailed location-based query with total_sales ranking.
    - Other channels: Standard title/revenue query.
    """
    
    # 1. Specialized POS query
    if channel_key == "pos":
        return f"""
            FROM sales
            SHOW 
                net_items_sold, 
                gross_sales, 
                discounts, 
                returns, 
                net_sales, 
                taxes, 
                total_sales
            WHERE 
                is_pos_sale = true 
                AND line_type = 'product' 
                AND product_title IS NOT NULL
            GROUP BY 
                product_title, 
                product_type WITH TOTALS
            SINCE {since} UNTIL {until}
            ORDER BY 
                total_sales DESC
            LIMIT {limit}
        """

    # 2. Generic query logic for other channels
    filter_type = config.get("filter_type")
    
    # Define fields and sorting
    # We use a consistent set of fields across all channels for better AI analysis
    show_clause = "net_items_sold, gross_sales, discounts, returns, net_sales, taxes, total_sales"
    order_by = "total_sales DESC"

    # Specialized logic for Online Store (Multi-channel + Exclusions)
    if channel_key == "online_store":
        where_clause = "sales_channel IN ('Online Store', 'Shop', 'Facebook', 'Instagram') AND line_type = 'product' AND product_title IS NOT NULL AND order_tags NOT CONTAINS 'Manymoons' AND order_tags NOT CONTAINS 'shopmy'"
        
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
        GROUP BY product_title, product_type WITH TOTALS
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
) -> List[Dict[str, Any]]:
    """
    Fetch and parse top products for a specific sub-channel.
    """
    try:
        query = build_product_query(channel_key, config, since, until, limit)
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

        products = run_product_report(client, channel_key, config, since, until, limit)
        all_products[channel_key] = products

    return all_products
