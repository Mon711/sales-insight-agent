#!/usr/bin/env python3
"""
Discover active sales channels in the Shopify store.
"""

from src.config import REPORT_SINCE, REPORT_UNTIL
from src.shopify_client import ShopifyGraphQLClient


def main() -> None:
    client = ShopifyGraphQLClient()
    rows = client.discover_channels(REPORT_SINCE, REPORT_UNTIL)

    print(f"Active sales channels for {REPORT_SINCE} to {REPORT_UNTIL}")
    for row in rows:
        name = row.get("sales_channel", "Unknown")
        net_sales = float(row.get("net_sales", 0) or 0)
        orders = float(row.get("orders", 0) or 0)
        print(f"- {name}: ${net_sales:,.2f} net sales, {orders:.0f} orders")


if __name__ == "__main__":
    main()
