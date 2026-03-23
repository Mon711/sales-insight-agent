#!/usr/bin/env python3
"""
Discovery query helper — finds exact sales_channel names for dropship connectors.

Run this script with valid Shopify credentials to:
1. Get a complete breakdown of all sales_channel values in the store
2. Identify the exact names for Mirakl Connect, fabric, and Maisonette channels
3. Copy the values to src/config.py to enable dropship sub-channel reporting

Usage:
    python discover_channels.py
"""

import json
from src.shopify_client import ShopifyGraphQLClient
from src.config import REPORT_SINCE, REPORT_UNTIL, get_unconfirmed_sub_channels, SUB_CHANNEL_CONFIG


def main():
    print("=" * 70)
    print("Channel Discovery — Finding exact sales_channel names")
    print("=" * 70)

    try:
        client = ShopifyGraphQLClient()
        print(f"\n✓ Connected to: {client.shop_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return

    # Run discovery query
    print(f"\nRunning discovery query ({REPORT_SINCE} → {REPORT_UNTIL})...")
    discovery_query = f"""
        FROM sales
        SHOW sales_channel, net_sales, orders
        GROUP BY sales_channel
        SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
    """

    try:
        response = client.run_shopifyql_report(discovery_query)
        if response.get("parseErrors"):
            print(f"✗ Parse error: {response['parseErrors']}")
            return

        rows = response.get("tableData", {}).get("rows", [])
        print(f"\nFound {len(rows)} distinct sales_channel values:\n")

        # Display all channels
        for row in rows:
            channel = row.get("sales_channel", "Unknown")
            net = float(row.get("net_sales", 0) or 0)
            orders = row.get("orders", 0)
            print(f"  '{channel}'")
            print(f"    → {orders} orders, ${net:.2f} net sales\n")

        # Show candidates for dropship sub-channels
        unconfirmed = get_unconfirmed_sub_channels()
        if unconfirmed:
            print("\n" + "=" * 70)
            print("NEXT STEP: Match discovered channels to dropship sub-channels")
            print("=" * 70 + "\n")

            for sub_channel in unconfirmed:
                cfg = SUB_CHANNEL_CONFIG[sub_channel]
                candidates = cfg.get("shopify_channel_candidates", [])
                print(f"\n{sub_channel} (commission: {cfg['commission_rate']*100:.0f}%)")
                print(f"  Expected candidates: {candidates}")
                print(f"  ➜ Look for these in the channel list above")
                print(f"  ➜ Update src/config.py: shopify_channel = '<EXACT_NAME>'")

            print("\n" + "=" * 70)
            print("EXAMPLE UPDATE:")
            print("=" * 70)
            print("""
In src/config.py, find the dropship_mirakl config and change:

    "shopify_channel": None,

to:

    "shopify_channel": "Mirakl Connect",  # or whatever name appears above
            """)

    except Exception as e:
        print(f"✗ Discovery query failed: {e}")


if __name__ == "__main__":
    main()
