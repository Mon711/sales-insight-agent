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
    limit: int = 20,
) -> str:
    """
    Build a ShopifyQL product query for a specific sub-channel.

    Handles multiple filter types:
    - sales_channel: single specific channel (most dropship sub-channels)
    - sales_channel_multi: multiple OR'd channels (online_store)
    - order_tag: tag-based filtering (wholesale)

    Returns a ShopifyQL query string that GROUPs BY product_title and ranks by net_sales
    (or gross_sales for wholesale where net_sales = $0).
    """
    filter_type = config.get("filter_type")

    # Shared columns and base structure
    if channel_key == "wholesale":
        # Wholesale: rank by gross_sales since net_sales = $0
        show_clause = "product_title, gross_sales, net_sales, orders"
        order_by = "gross_sales DESC"
    else:
        show_clause = "product_title, gross_sales, net_sales, orders"
        order_by = "net_sales DESC"

    if filter_type == "sales_channel":
        # Single channel
        channel = config.get("shopify_channel")
        if not channel:
            raise ValueError(f"Channel {channel_key} has no shopify_channel defined. Run discovery query first.")

        query = f"""
            FROM sales
            SHOW {show_clause}
            WHERE sales_channel = '{channel}'
            GROUP BY product_title
            SINCE {since} UNTIL {until}
            ORDER BY {order_by}
            LIMIT {limit}
        """

    elif filter_type == "sales_channel_multi":
        # Multiple channels with OR logic (online_store)
        channels = config.get("shopify_channels", [])
        exclude_tags = config.get("exclude_tags", [])

        # Build WHERE clause: (channel1 OR channel2 OR ...) AND NOT exclude_tags
        channel_conditions = " OR ".join([f"sales_channel = '{ch}'" for ch in channels])
        exclude_conditions = " AND ".join([f"order_tags NOT CONTAINS '{tag}'" for tag in exclude_tags])

        where_clause = f"({channel_conditions}) AND {exclude_conditions}" if exclude_conditions else channel_conditions

        query = f"""
            FROM sales
            SHOW {show_clause}
            WHERE {where_clause}
            GROUP BY product_title
            SINCE {since} UNTIL {until}
            ORDER BY {order_by}
            LIMIT {limit}
        """

    elif filter_type == "order_tag":
        # Tag-based filtering (wholesale)
        tag = config.get("tag")
        if not tag:
            raise ValueError(f"Channel {channel_key} has no tag defined.")

        query = f"""
            FROM sales
            SHOW {show_clause}
            WHERE order_tags CONTAINS '{tag}'
            GROUP BY product_title
            SINCE {since} UNTIL {until}
            ORDER BY {order_by}
            LIMIT {limit}
        """

    else:
        raise ValueError(f"Unknown filter_type: {filter_type} for channel {channel_key}")

    return query


def parse_product_rows(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract product rows from a ShopifyQL response."""
    return response.get("tableData", {}).get("rows", [])


def run_product_report(
    client: ShopifyGraphQLClient,
    channel_key: str,
    config: Dict[str, Any],
    since: str = REPORT_SINCE,
    until: str = REPORT_UNTIL,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """
    Fetch and parse top products for a specific sub-channel.

    Args:
        client: Shopify GraphQL client
        channel_key: Sub-channel identifier (e.g., "online_store", "dropship_mirakl")
        config: Sub-channel config dict from SUB_CHANNEL_CONFIG
        since: Report start date
        until: Report end date
        limit: Max number of top products to fetch

    Returns:
        List of product dicts with keys: product_title, gross_sales, net_sales, orders, true_net_sales
        Returns empty list if query fails (logs error, doesn't crash).
    """
    try:
        query = build_product_query(channel_key, config, since, until, limit)
        print(f"  [PRODUCTS] Fetching top {limit} products for {channel_key}...")

        response = client.run_shopifyql_report(query)

        if response.get("parseErrors"):
            print(f"    ⚠ ShopifyQL parse error: {response['parseErrors']}")
            return []

        rows = parse_product_rows(response)

        # Compute true_net_sales for each product
        commission_rate = config.get("commission_rate", 0.0)
        for row in rows:
            net_sales = float(row.get("net_sales", 0) or 0)
            true_net = net_sales * (1 - commission_rate)
            row["true_net_sales"] = round(true_net, 2)

        print(f"    ✓ {len(rows)} products fetched")
        return rows

    except Exception as e:
        print(f"    ✗ Error fetching products for {channel_key}: {e}")
        return []


def run_all_product_reports(
    client: ShopifyGraphQLClient,
    since: str = REPORT_SINCE,
    until: str = REPORT_UNTIL,
    limit: int = 20,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Fetch product reports for all active sub-channels.

    Returns a dict keyed by channel_key, each containing a list of top products.
    If a channel has an error, that channel is skipped (but others continue).

    Example return value:
    {
        "online_store": [
            {
                "product_title": "Product A",
                "gross_sales": 900.0,
                "net_sales": 850.0,
                "orders": 7,
                "true_net_sales": 850.0  # 0% commission
            },
            ...
        ],
        "pos": [...],
        ...
    }
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
