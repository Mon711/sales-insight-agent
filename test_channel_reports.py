#!/usr/bin/env python3
"""
Test script for ShopifyQL channel reports.

Usage:
    python test_channel_reports.py

Runs four checks:
1. API connection
2. Channel discovery (shows all sales_channel values in the store)
3. All four channel reports
4. Prints a clean summary
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

    # Step 4: Print full JSON output
    print("\n[STEP 4] Full report output (JSON):")
    print(json.dumps(all_reports, indent=2, default=str))

    print("\n" + "=" * 60)
    print(f"✓ Done — {len(all_reports)} channel reports generated")
    print("=" * 60)


if __name__ == "__main__":
    main()
