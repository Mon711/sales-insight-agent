"""
Shopify GraphQL API client.

Handles authentication and querying the Shopify Admin GraphQL API.
Credentials are read from environment variables — never hardcoded.
"""

import os
import time
import requests
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
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

        max_attempts = 5
        for attempt in range(1, max_attempts + 1):
            try:
                response = requests.post(self.api_url, json=payload, headers=self.headers, timeout=60)
                response.raise_for_status()
            except requests.exceptions.RequestException as e:
                raise Exception(f"Failed to connect to Shopify API: {e}")

            result = response.json()
            errors = result.get("errors")
            if not errors:
                return result

            if self._is_throttled_error(errors) and attempt < max_attempts:
                wait_seconds = self._throttle_wait_seconds(errors, attempt)
                print(
                    f"[Shopify throttle] attempt {attempt}/{max_attempts}, "
                    f"waiting {wait_seconds}s before retry..."
                )
                time.sleep(wait_seconds)
                continue

            raise Exception(f"Shopify API returned errors: {errors}")

        raise Exception("Shopify API retry loop exhausted unexpectedly.")

    @staticmethod
    def _is_throttled_error(errors: Any) -> bool:
        if not isinstance(errors, list):
            return False
        for err in errors:
            code = (((err or {}).get("extensions") or {}).get("code") or "").upper()
            if code == "THROTTLED":
                return True
        return False

    @staticmethod
    def _throttle_wait_seconds(errors: List[Dict[str, Any]], attempt: int) -> int:
        default_wait = min(30, 3 * attempt)
        for err in errors:
            extensions = (err or {}).get("extensions") or {}
            cost = extensions.get("cost") or {}
            reset_at = cost.get("windowResetAt")
            if not reset_at:
                continue
            try:
                # Shopify returns UTC ISO timestamps, usually ending with 'Z' or '+00:00'.
                reset_dt = datetime.fromisoformat(reset_at.replace("Z", "+00:00"))
                now_dt = datetime.now(timezone.utc)
                seconds = int((reset_dt - now_dt).total_seconds()) + 1
                return max(2, min(60, seconds))
            except ValueError:
                continue
        return default_wait

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

    def probe_shopifyql_product_id_support(self, since: str, until: str) -> bool:
        """
        Check whether ShopifyQL supports `product_id` in the current store context.

        Returns:
            True when the query parses successfully, False on ShopifyQL parse errors.

        Raises:
            Exception for transport/auth failures from the underlying API call.
        """
        probe_query = (
            "FROM sales "
            "SHOW product_title, product_id, net_sales "
            "WHERE line_type = 'product' AND product_title IS NOT NULL "
            "GROUP BY product_title, product_id "
            f"SINCE {since} UNTIL {until} "
            "LIMIT 1"
        )
        response = self.run_shopifyql_report(probe_query)
        return not bool(response.get("parseErrors"))

    def check_read_products_access(self) -> Tuple[bool, Optional[str]]:
        """
        Verify whether the current token can read Product data (read_products scope).

        Returns:
            (True, None) when access works, else (False, error_message).
        """
        graphql_query = """
        query ProductScopeCheck {
            products(first: 1) {
                nodes {
                    id
                }
            }
        }
        """
        try:
            self.query(graphql_query)
            return True, None
        except Exception as e:
            return False, str(e)

    @staticmethod
    def to_product_gid(raw_product_id: Any) -> Optional[str]:
        """
        Convert a Shopify product identifier into gid://shopify/Product/<id> format.
        """
        if raw_product_id is None:
            return None

        value = str(raw_product_id).strip()
        if not value:
            return None

        if value.startswith("gid://shopify/Product/"):
            return value

        if value.isdigit():
            return f"gid://shopify/Product/{value}"

        return None

    @staticmethod
    def _extract_primary_media_image(product_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Return the best available image metadata for a product node."""
        featured_media = product_node.get("featuredMedia")
        if featured_media and featured_media.get("__typename") == "MediaImage":
            image = featured_media.get("image") or {}
            url = image.get("url")
            if url:
                return {
                    "source": "featured_media",
                    "media_id": featured_media.get("id"),
                    "url": url,
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "alt_text": image.get("altText") or featured_media.get("alt"),
                }

        media_nodes = (
            product_node.get("media", {})
            .get("nodes", [])
        )
        for media in media_nodes:
            if not media or media.get("__typename") != "MediaImage":
                continue
            image = media.get("image") or {}
            url = image.get("url")
            if url:
                return {
                    "source": "media_first",
                    "media_id": media.get("id"),
                    "url": url,
                    "width": image.get("width"),
                    "height": image.get("height"),
                    "alt_text": image.get("altText") or media.get("alt"),
                }

        return None

    def _build_product_image_record(self, product_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a Product node into a compact image record."""
        product_id = product_node.get("id")
        if not product_id:
            return None

        return {
            "id": product_id,
            "title": product_node.get("title"),
            "handle": product_node.get("handle"),
            "primary_image": self._extract_primary_media_image(product_node),
        }

    def fetch_product_image_records_by_ids(
        self,
        product_gids: List[str],
        batch_size: int = 50,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch product image metadata for a list of product GIDs.

        Returns:
            Mapping: product_gid -> normalized product image record.
        """
        unique_ids: List[str] = []
        seen = set()
        for pid in product_gids:
            if not pid or pid in seen:
                continue
            seen.add(pid)
            unique_ids.append(pid)

        if not unique_ids:
            return {}

        graphql_query = """
        query ProductImagesByIds($ids: [ID!]!) {
            nodes(ids: $ids) {
                __typename
                ... on Product {
                    id
                    title
                    handle
                    featuredMedia {
                        __typename
                        ... on MediaImage {
                            id
                            alt
                            image {
                                url
                                width
                                height
                                altText
                            }
                        }
                    }
                    media(first: 5, query: "media_type:IMAGE", sortKey: POSITION) {
                        nodes {
                            __typename
                            ... on MediaImage {
                                id
                                alt
                                image {
                                    url
                                    width
                                    height
                                    altText
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        batch_size = max(1, min(batch_size, 250))
        records: Dict[str, Dict[str, Any]] = {}

        for start in range(0, len(unique_ids), batch_size):
            batch = unique_ids[start:start + batch_size]
            result = self.query(graphql_query, variables={"ids": batch})
            nodes = result.get("data", {}).get("nodes", [])

            for node in nodes:
                if not node or node.get("__typename") != "Product":
                    continue
                record = self._build_product_image_record(node)
                if record:
                    records[record["id"]] = record

        return records

    def find_product_image_records_by_exact_title(
        self,
        title: str,
        first: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Search products by title and return exact title matches with image metadata.
        """
        cleaned_title = (title or "").strip()
        if not cleaned_title:
            return []

        escaped = cleaned_title.replace("\\", "\\\\").replace('"', '\\"')
        search_query = f'title:"{escaped}"'

        graphql_query = """
        query FindProductsForTitle($query: String!, $first: Int!) {
            products(first: $first, query: $query, sortKey: TITLE) {
                nodes {
                    id
                    title
                    handle
                    featuredMedia {
                        __typename
                        ... on MediaImage {
                            id
                            alt
                            image {
                                url
                                width
                                height
                                altText
                            }
                        }
                    }
                    media(first: 5, query: "media_type:IMAGE", sortKey: POSITION) {
                        nodes {
                            __typename
                            ... on MediaImage {
                                id
                                alt
                                image {
                                    url
                                    width
                                    height
                                    altText
                                }
                            }
                        }
                    }
                }
            }
        }
        """

        result = self.query(
            graphql_query,
            variables={"query": search_query, "first": first},
        )
        nodes = result.get("data", {}).get("products", {}).get("nodes", [])
        normalized_target = cleaned_title.lower()

        matches = []
        for node in nodes:
            if not node:
                continue
            node_title = (node.get("title") or "").strip().lower()
            if node_title != normalized_target:
                continue
            record = self._build_product_image_record(node)
            if record:
                matches.append(record)

        return matches

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
