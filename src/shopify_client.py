"""
Shopify GraphQL API client.

Handles authentication and querying the Shopify Admin GraphQL API.
Credentials are read from environment variables — never hardcoded.
"""

import os
import requests
from typing import Optional, Dict, Any, List
from dotenv import load_dotenv

load_dotenv()


class ShopifyGraphQLClient:
    """
    Client for the Shopify Admin GraphQL API.

    Supports both standard GraphQL queries and ShopifyQL analytics queries.
    Requires environment variables:
        SHOPIFY_SHOP_NAME    — store subdomain (e.g., "mystore")
        SHOPIFY_ACCESS_TOKEN — admin API access token (needs read_reports scope)
    """

    def __init__(self):
        self.shop_name = os.getenv("SHOPIFY_SHOP_NAME")
        self.access_token = os.getenv("SHOPIFY_ACCESS_TOKEN")

        if not self.shop_name or not self.access_token:
            raise ValueError(
                "Missing required environment variables:\n"
                "  SHOPIFY_SHOP_NAME (e.g., 'mystore')\n"
                "  SHOPIFY_ACCESS_TOKEN (your admin API access token)\n"
                "Please set these before running the script."
            )

        self.api_url = f"https://{self.shop_name}.myshopify.com/admin/api/2025-10/graphql.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    def query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Shopify API.

        Raises:
            Exception: If the HTTP request fails or Shopify returns GraphQL errors.
        """
        payload = {"query": query_string}
        if variables:
            payload["variables"] = variables

        try:
            response = requests.post(self.api_url, json=payload, headers=self.headers)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to connect to Shopify API: {e}")

        result = response.json()

        if "errors" in result:
            raise Exception(f"Shopify API returned errors: {result['errors']}")

        return result

    def run_shopifyql_report(self, shopifyql_query: str) -> Dict[str, Any]:
        """
        Execute a ShopifyQL analytics query.

        ShopifyQL is Shopify's analytics query language (SQL-like).
        Requires the read_reports scope on the access token.

        Args:
            shopifyql_query: A ShopifyQL string, e.g.:
                "FROM sales SHOW net_sales TIMESERIES day SINCE -30d UNTIL today"

        Returns:
            Dict with keys:
                parseErrors — list of syntax errors (empty if query is valid)
                tableData   — dict with columns and rows
        """
        graphql_query = """
        query RunShopifyQLReport($qlQuery: String!) {
            shopifyqlQuery(query: $qlQuery) {
                parseErrors
                tableData {
                    columns {
                        name
                        displayName
                        dataType
                    }
                    rows
                }
            }
        }
        """
        result = self.query(graphql_query, variables={"qlQuery": shopifyql_query})
        return result.get("data", {}).get("shopifyqlQuery", {})

    def discover_channels(self, since: str, until: str) -> List[Dict[str, Any]]:
        """
        Fetch a breakdown of all active sales channels in the store.
        Returns a list of rows with channel names and high-level sales totals.
        """
        query = f"FROM sales SHOW sales_channel, net_sales, orders GROUP BY sales_channel SINCE {since} UNTIL {until}"
        response = self.run_shopifyql_report(query)
        
        if response.get("parseErrors"):
            raise Exception(f"Discovery query error: {response['parseErrors']}")
            
        return response.get("tableData", {}).get("rows", [])


def test_connection():
    """Verify the Shopify API connection and ShopifyQL access."""
    try:
        client = ShopifyGraphQLClient()
        print(f"✓ Connected to Shopify store: {client.shop_name}")

        result = client.run_shopifyql_report(
            "FROM sales SHOW net_sales SINCE -1d UNTIL today"
        )
        if result.get("parseErrors"):
            print(f"⚠ ShopifyQL parse errors: {result['parseErrors']}")
        else:
            print("✓ ShopifyQL is working (read_reports scope confirmed)")

        return True
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        return False


if __name__ == "__main__":
    test_connection()
