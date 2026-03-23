"""
Channel-specific sales reports using Shopify's ShopifyQL analytics API.

Generates clean, structured reports for each sales channel (Online Store, POS, Wholesale, Dropship).
Output is JSON-serializable for analysis by Claude.

Channel definitions (based on Eddy's store business rules):
- online_store: Online Store + Shop + Facebook & Instagram, excluding Manymoons/shopmy tagged orders
- pos:          Point of Sale channel only
- wholesale:    Any channel where order is tagged 'wholesale'
- dropship:     Everything else — excludes Online Store, POS, Facebook & Instagram, Draft Orders,
                Shopmy Integration, Loop Returns & Exchanges, Shopify Mobile for iPhone,
                and orders tagged Manymoons, shopmy, or wholesale

Excluded order types (not real revenue):
- 'shopmy' tagged / Shopmy Integration channel: gifting orders sent to influencers, $0 revenue
- 'Manymoons' tagged: heavy discount orders, distort sales performance metrics
- Wholesale payment note: Shopify records net_sales = $0 for wholesale because payment is
  collected offline (outside Shopify). Estimated revenue = gross_sales / 2 (50% of retail).
"""

from typing import Dict, Any, List
from .shopify_client import ShopifyGraphQLClient
from .config import REPORT_SINCE, REPORT_UNTIL, SUB_CHANNEL_CONFIG

# ShopifyQL query constants per channel
CHANNEL_QUERIES = {
    "online_store": f"""
        FROM sales
        SHOW gross_sales, discounts, net_sales, orders
        WHERE (sales_channel = 'Online Store'
            AND order_tags NOT CONTAINS 'Manymoons'
            AND order_tags NOT CONTAINS 'shopmy')
          OR sales_channel = 'Shop'
          OR sales_channel = 'Facebook & Instagram'
        TIMESERIES day
        SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    """,
    "pos": f"""
        FROM sales
        SHOW gross_sales, discounts, net_sales, orders
        WHERE sales_channel = 'Point of Sale'
        TIMESERIES day
        SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    """,
    "wholesale": f"""
        FROM sales
        SHOW gross_sales, discounts, net_sales, orders
        WHERE order_tags CONTAINS 'wholesale'
        TIMESERIES day
        SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    """,
    "dropship": f"""
        FROM sales
        SHOW gross_sales, discounts, net_sales, orders
        WHERE sales_channel != 'Online Store'
          AND sales_channel != 'Point of Sale'
          AND sales_channel != 'Facebook & Instagram'
          AND sales_channel != 'Draft Orders'
          AND sales_channel != 'Shopmy Integration'
          AND sales_channel != 'Loop Returns & Exchanges'
          AND sales_channel != 'Shopify Mobile for iPhone'
          AND order_tags NOT CONTAINS 'Manymoons'
          AND order_tags NOT CONTAINS 'shopmy'
          AND order_tags NOT CONTAINS 'wholesale'
        TIMESERIES day
        SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    """,
    # TODO: Add dropship sub-channel queries after running discover_channels.py
    # Once you've confirmed the exact sales_channel names for Mirakl, fabric, and
    # Maisonette, uncomment and update these queries with the confirmed channel names,
    # then update src/config.py with the same channel names.
    #
    # "dropship_mirakl": f"""
    #     FROM sales
    #     SHOW gross_sales, discounts, net_sales, orders
    #     WHERE sales_channel = 'CONFIRMED_MIRAKL_CHANNEL_NAME'
    #     TIMESERIES day
    #     SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    # """,
    # "dropship_fabric": f"""
    #     FROM sales
    #     SHOW gross_sales, discounts, net_sales, orders
    #     WHERE sales_channel = 'CONFIRMED_FABRIC_CHANNEL_NAME'
    #     TIMESERIES day
    #     SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    # """,
    # "dropship_maisonette": f"""
    #     FROM sales
    #     SHOW gross_sales, discounts, net_sales, orders
    #     WHERE sales_channel = 'CONFIRMED_MAISONETTE_CHANNEL_NAME'
    #     TIMESERIES day
    #     SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    # """,
}

# Discovery query — shows a breakdown of all sales_channel values in the store.
# Useful for verifying channel names and diagnosing unexpected data.
DISCOVERY_QUERY = f"""
    FROM sales
    SHOW sales_channel, net_sales, orders
    GROUP BY sales_channel
    SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
"""


def parse_table_to_dicts(response: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract rows from a ShopifyQL response.

    ShopifyQL returns rows as an array of dicts (not arrays),
    so we return tableData.rows directly.
    """
    return response.get("tableData", {}).get("rows", [])


def run_discovery_query(client: ShopifyGraphQLClient) -> List[Dict[str, Any]]:
    """
    Show a breakdown of all sales channels in the store for the report period.

    Useful for verifying that channel names match expected values.
    """
    print(f"\n[DISCOVERY] Sales by channel ({REPORT_SINCE} → {REPORT_UNTIL})...")
    response = client.run_shopifyql_report(DISCOVERY_QUERY)

    if response.get("parseErrors"):
        raise ValueError(f"ShopifyQL syntax error: {response['parseErrors']}")

    rows = parse_table_to_dicts(response)
    for row in rows:
        channel = row.get("sales_channel", "Unknown")
        net = float(row.get("net_sales", 0) or 0)
        order_count = row.get("orders", 0)
        print(f"  - {channel}: {order_count} orders, ${net:.2f} net sales")

    return rows


def run_channel_report(client: ShopifyGraphQLClient, channel_key: str) -> Dict[str, Any]:
    """
    Fetch and parse a daily sales report for one channel.

    Returns a clean JSON-serializable dict:
    {
        "channel": "pos",
        "date_range": {"since": "2026-02-01", "until": "2026-02-28"},
        "rows": [{"day": "2026-02-01", "gross_sales": "...", ...}, ...],
        "summary": {
            "total_gross_sales": <float>,
            "total_net_sales": <float>,
            "total_discounts": <float>,
            "total_orders": <int>,
            "commission_rate": <float>,
            "true_net_sales": <float>,
            "commission_deducted": <float>
        }
    }
    """
    if channel_key not in CHANNEL_QUERIES:
        valid_keys = ", ".join(CHANNEL_QUERIES.keys())
        raise ValueError(f"Invalid channel: '{channel_key}'. Must be one of: {valid_keys}")

    print(f"\n[REPORT] Fetching {channel_key} ({REPORT_SINCE} → {REPORT_UNTIL})...")
    response = client.run_shopifyql_report(CHANNEL_QUERIES[channel_key])

    if response.get("parseErrors"):
        raise ValueError(f"ShopifyQL syntax error in {channel_key}: {response['parseErrors']}")

    rows = parse_table_to_dicts(response)

    total_gross_sales = sum(float(row.get("gross_sales", 0) or 0) for row in rows)
    total_net_sales = sum(float(row.get("net_sales", 0) or 0) for row in rows)
    total_discounts = sum(float(row.get("discounts", 0) or 0) for row in rows)
    total_orders = sum(int(row.get("orders", 0) or 0) for row in rows)

    # Get commission rate from config, default to 0% if not found
    commission_rate = SUB_CHANNEL_CONFIG.get(channel_key, {}).get("commission_rate", 0.0)
    true_net_sales = total_net_sales * (1 - commission_rate)
    commission_deducted = total_net_sales - true_net_sales

    summary = {
        "total_gross_sales": round(total_gross_sales, 2),
        "total_net_sales": round(total_net_sales, 2),
        "total_discounts": round(total_discounts, 2),
        "total_orders": total_orders,
        "commission_rate": commission_rate,
        "true_net_sales": round(true_net_sales, 2),
        "commission_deducted": round(commission_deducted, 2),
    }

    # Wholesale: payment is collected offline so Shopify always records net_sales = $0.
    # Estimated revenue uses 50% of gross (standard wholesale pricing approximation).
    if channel_key == "wholesale":
        summary["estimated_revenue"] = round(total_gross_sales / 2, 2)
        summary["data_note"] = (
            "net_sales = $0 because wholesale payment is collected offline (outside Shopify). "
            "estimated_revenue = gross_sales / 2 (approx. 50% wholesale pricing)."
        )

    return {
        "channel": channel_key,
        "date_range": {"since": REPORT_SINCE, "until": REPORT_UNTIL},
        "rows": rows,
        "summary": summary,
    }


def run_all_channel_reports(client: ShopifyGraphQLClient) -> Dict[str, Dict[str, Any]]:
    """
    Fetch reports for all four channels and return them as a combined dict.
    """
    reports = {}
    for channel_key in CHANNEL_QUERIES.keys():
        try:
            reports[channel_key] = run_channel_report(client, channel_key)
            summary = reports[channel_key]["summary"]
            print(f"[OK] {channel_key}: {summary['total_orders']} orders, ${summary['total_net_sales']:.2f} net sales")
        except Exception as e:
            print(f"[ERROR] {channel_key}: {e}")

    return reports
