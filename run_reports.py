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
from datetime import datetime, timezone
from src.shopify_client import ShopifyGraphQLClient
from src.channel_reports import run_discovery_query, run_all_channel_reports
from src.product_reports import run_all_product_reports
from src.config import REPORT_SINCE, REPORT_UNTIL


def main():
    print("=" * 60)
    print(f"ShopifyQL Channel & Product Reports — {REPORT_SINCE} to {REPORT_UNTIL}")
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

    # Step 3: Run all channel reports
    print("\n[STEP 3] Running all channel reports...")
    try:
        all_reports = run_all_channel_reports(client)
    except Exception as e:
        print(f"✗ Report generation failed: {e}")
        sys.exit(1)

    # Step 4: Run all product reports
    print("\n[STEP 4] Running product reports...")
    try:
        all_products = run_all_product_reports(client)
        # Merge top_products into each channel report
        for channel_key, products in all_products.items():
            if channel_key in all_reports:
                all_reports[channel_key]["top_products"] = products
            else:
                print(f"  ⚠ Product report for {channel_key} has no matching channel report")
    except Exception as e:
        print(f"✗ Product report generation failed: {e}")
        sys.exit(1)

    # Step 5: Add metadata and write JSON output
    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_period": {"since": REPORT_SINCE, "until": REPORT_UNTIL},
        "channels": all_reports,
    }

    output_path = f"/Users/mrinalsood/Downloads/sales_report_{REPORT_SINCE}_to_{REPORT_UNTIL}.json"
    with open(output_path, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print("\n" + "=" * 60)
    print(f"✓ Done — {len(all_reports)} channels with product analysis")
    print(f"✓ Output saved to: {output_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
