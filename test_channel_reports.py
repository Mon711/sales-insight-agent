#!/usr/bin/env python3
"""
Basic end-to-end validation for Shopify connection and reporting.
"""

import sys

from src.config import REPORT_SINCE, REPORT_UNTIL
from src.product_reports import run_all_product_reports
from src.shopify_client import ShopifyGraphQLClient, test_connection


def main() -> None:
    print("=" * 60)
    print("Testing Shopify connection and report generation")
    print("=" * 60)

    if not test_connection():
        sys.exit(1)

    client = ShopifyGraphQLClient()

    print(f"\nDiscovery for {REPORT_SINCE} to {REPORT_UNTIL}")
    channels = client.discover_channels(REPORT_SINCE, REPORT_UNTIL)
    for row in channels:
        name = row.get("sales_channel", "Unknown")
        net_sales = float(row.get("net_sales", 0) or 0)
        print(f"- {name}: ${net_sales:,.2f} net sales")

    print("\nRunning report generation...")
    all_products = run_all_product_reports(client, REPORT_SINCE, REPORT_UNTIL)
    for channel_key, rows in all_products.items():
        print(f"- {channel_key}: {len(rows)} product rows")

    print("\n✓ Test run completed successfully")


if __name__ == "__main__":
    main()
