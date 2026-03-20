"""
Shopify GraphQL API client for fetching live order data.

This module handles authentication and querying the Shopify Admin GraphQL API.
Credentials are read from environment variables for security.
"""

import os
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

# Load environment variables from .env file (if it exists)
load_dotenv()


class ShopifyGraphQLClient:
    """
    Simple client for querying the Shopify Admin GraphQL API.

    Authenticates using an access token (obtained via OAuth or custom app flow).
    Fetches orders and other data from a live Shopify store.
    """

    def __init__(self):
        """
        Initialize the Shopify GraphQL client from environment variables.

        Required environment variables:
        - SHOPIFY_SHOP_NAME: Store name (e.g., "mystore")
        - SHOPIFY_ACCESS_TOKEN: Admin access token

        Raises:
            ValueError: If required environment variables are missing
        """
        self.shop_name = os.getenv("SHOPIFY_SHOP_NAME")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

        if not self.shop_name or not self.access_token:
            raise ValueError(
                "Missing required environment variables:\n"
                "  SHOPIFY_SHOP_NAME (e.g., 'mystore')\n"
                "  SHOPIFY_ACCESS_TOKEN (your admin API access token)\n"
                "Please set these before running the script."
            )

        # Construct the API endpoint
        self.api_url = f"https://{self.shop_name}.myshopify.com/admin/api/2024-10/graphql.json"

        # Headers for GraphQL requests
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    def query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Shopify API.

        Args:
            query_string: The GraphQL query string
            variables: Optional dict of variables to pass to the query

        Returns:
            The parsed JSON response from Shopify

        Raises:
            Exception: If the API request fails or returns errors
        """
        payload = {
            "query": query_string,
        }
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(self.api_url, json=payload, headers=self.headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to connect to Shopify API: {e}")

        result = response.json()

        # Check for GraphQL-level errors
        if "errors" in result:
            raise Exception(f"Shopify API returned errors: {result['errors']}")

        return result

    def fetch_orders(self, limit: int = 50, after_cursor: Optional[str] = None) -> tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Fetch a batch of orders from the Shopify store.

        Retrieves orders with all relevant business fields:
        - Order ID, name, creation/processing dates
        - Revenue (totalPriceSet in shop currency)
        - Test flag, cancellation, fulfillment status
        - Line items (products sold)
        - Channel (website, POS, etc.)
        - Payment status

        Args:
            limit: Number of orders to fetch (max 250)
            after_cursor: Pagination cursor for fetching next batch

        Returns:
            Tuple of (orders_list, next_cursor)
            - orders_list: List of order dicts
            - next_cursor: Cursor to fetch next batch (None if no more)
        """
        query = """
        query getOrders($first: Int!, $after: String) {
            orders(first: $first, after: $after) {
                pageInfo {
                    hasNextPage
                    endCursor
                }
                edges {
                    node {
                        id
                        name
                        createdAt
                        processedAt
                        cancelledAt
                        test
                        closed
                        fullyPaid
                        displayFulfillmentStatus
                        currencyCode
                        totalPriceSet {
                            shopMoney {
                                amount
                                currencyCode
                            }
                        }
                        channelInformation {
                            channelId
                        }
                        lineItems(first: 100) {
                            edges {
                                node {
                                    id
                                    title
                                    quantity
                                    originalUnitPriceSet {
                                        shopMoney {
                                            amount
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        variables = {
            "first": min(limit, 250),  # Shopify API max is 250
            "after": after_cursor,
        }

        result = self.query(query, variables)

        # Extract orders from the response
        orders = []
        edges = result.get("data", {}).get("orders", {}).get("edges", [])
        for edge in edges:
            orders.append(edge["node"])

        # Get pagination info
        page_info = result.get("data", {}).get("orders", {}).get("pageInfo", {})
        next_cursor = page_info.get("endCursor") if page_info.get("hasNextPage") else None

        return orders, next_cursor

    def fetch_all_orders(self) -> List[Dict[str, Any]]:
        """
        Fetch ALL orders from the store, handling pagination automatically.

        Caution: This may take a while for stores with many orders.
        Consider adding date filtering in future versions.

        Returns:
            List of all orders
        """
        all_orders = []
        cursor = None
        batch_count = 0

        while True:
            orders, cursor = self.fetch_orders(limit=250, after_cursor=cursor)
            all_orders.extend(orders)
            batch_count += 1
            print(f"Fetched batch {batch_count}: {len(orders)} orders (total so far: {len(all_orders)})")

            if not cursor:
                break

        return all_orders


def test_connection():
    """Quick test to verify the Shopify API connection works."""
    try:
        client = ShopifyGraphQLClient()
        print(f"✓ Connected to Shopify store: {client.shop_name}")

        # Fetch a single order to verify the API is working
        orders, _ = client.fetch_orders(limit=1)
        if orders:
            print(f"✓ Successfully fetched {len(orders)} order(s)")
            print(f"  Sample order: {orders[0]['name']}")
        else:
            print("⚠ No orders found in store (may be a new store)")

        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    # Simple test: try to connect and fetch one order
    test_connection()
