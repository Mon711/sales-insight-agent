#!/usr/bin/env python3
"""
Fetch ShopifyQL channel reports and save as JSON.

Usage:
    python run_reports.py

Execution flow:
1. Connect to Shopify API
2. Channel discovery — list all sales_channel values in store
3. Fetch reports for all four channels (online_store, pos, wholesale, dropship)
4. Save JSON output to Downloads folder
"""

import json
import sys
from src.shopify_client import ShopifyGraphQLClient
from src.channel_reports import run_discovery_query, run_all_channel_reports, REPORT_SINCE, REPORT_UNTIL


def main():
    print("=" * 60)
    print(f"ShopifyQL Channel Reports — {REPORT_SINCE} to {REPORT_UNTIL}")
    print("=" * 60)

    # Step 1: Test connection
    print("\n[STEP 1] Connecting to Shopify...")
    try:
        client = ShopifyGraphQLClient()
        print(f"✓ Connected to: {client.shop_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    # Step 2: Discovery — verify channel names in store
    print("\n[STEP 2] Channel breakdown (all sales_channel values in store):")
    try:
        run_discovery_query(client)
    except Exception as e:
        print(f"✗ Discovery query failed: {e}")
        sys.exit(1)

    # Step 3: Run all four channel reports
    print("\n[STEP 3] Running all channel reports...")
    try:
        all_reports = run_all_channel_reports(client)
    except Exception as e:
        print(f"✗ Report generation failed: {e}")
        sys.exit(1)

    # Step 4: Write JSON output to Downloads
    output_path = f"/Users/mrinalsood/Downloads/channel_reports_{REPORT_SINCE}_to_{REPORT_UNTIL}.json"
    with open(output_path, "w") as f:
        json.dump(all_reports, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print(f"✓ Done — {len(all_reports)} channel reports generated")
    print(f"✓ Output saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
