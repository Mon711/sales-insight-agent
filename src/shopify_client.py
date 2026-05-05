"""
Shopify GraphQL API client.

Handles authentication and querying the Shopify Admin GraphQL API.
Credentials are read from environment variables — never hardcoded.
"""

import json
import os
import re
import time
import requests
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from typing import Optional, Dict, Any, List, Tuple
from dotenv import load_dotenv

from .brand_profiles import BrandProfile, resolve_brand_profile

load_dotenv()


class _PlainTextHTMLParser(HTMLParser):
    """Small HTML-to-text parser for Shopify product descriptions."""

    _BLOCK_TAGS = {"br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []

    def handle_starttag(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> None:
        _ = attrs
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if data:
            self.parts.append(data)

    def text(self) -> str:
        return _clean_plain_text(" ".join(self.parts))


def _clean_plain_text(value: Any) -> str:
    """Normalize whitespace in text extracted from Shopify fields."""
    text = unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def description_html_to_text(description_html: Any) -> str:
    """Convert Shopify `descriptionHtml` into compact plain text."""
    if not description_html:
        return ""
    parser = _PlainTextHTMLParser()
    parser.feed(str(description_html))
    return parser.text()


def shopify_rich_text_to_plain_text(value: Any) -> str:
    """
    Convert Shopify rich-text JSON metafield values into plain text.

    Shopify rich-text metafields are JSON trees where text nodes carry `value`.
    If the field is already plain text, this returns a cleaned version unchanged.
    """
    if value in [None, ""]:
        return ""

    try:
        payload = json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError):
        return _clean_plain_text(value)

    parts: List[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            node_type = str(node.get("type") or "").lower()
            if node_type == "text" and node.get("value") not in [None, ""]:
                parts.append(str(node.get("value")))
            for child in node.get("children") or []:
                walk(child)
            if node_type in {"paragraph", "list-item", "heading"}:
                parts.append("\n")
        elif isinstance(node, list):
            for child in node:
                walk(child)
        elif node not in [None, ""]:
            parts.append(str(node))

    walk(payload)
    return _clean_plain_text(" ".join(parts))


def _connection_nodes(connection: Any) -> List[Dict[str, Any]]:
    """Return nodes from either Shopify `nodes` or `edges.node` connection shapes."""
    if not isinstance(connection, dict):
        return []
    if isinstance(connection.get("nodes"), list):
        return [node for node in connection["nodes"] if isinstance(node, dict)]
    nodes: List[Dict[str, Any]] = []
    for edge in connection.get("edges") or []:
        node = (edge or {}).get("node")
        if isinstance(node, dict):
            nodes.append(node)
    return nodes


def _metafield_reference_labels(metafield: Optional[Dict[str, Any]]) -> Tuple[List[str], List[Dict[str, Any]]]:
    """Resolve Shopify metaobject reference metafields into readable labels."""
    if not metafield:
        return [], []

    raw_nodes: List[Dict[str, Any]] = []
    raw_nodes.extend(_connection_nodes(metafield.get("references") or {}))
    reference = metafield.get("reference")
    if isinstance(reference, dict):
        raw_nodes.append(reference)

    labels: List[str] = []
    references: List[Dict[str, Any]] = []
    seen_labels: set[str] = set()
    for node in raw_nodes:
        fields = [
            {"key": field.get("key"), "value": field.get("value")}
            for field in (node.get("fields") or [])
            if isinstance(field, dict)
        ]
        display_name = _clean_plain_text(node.get("displayName"))
        fallback_values = [
            _clean_plain_text(field.get("value"))
            for field in fields
            if field.get("key") in {"name", "label", "title"} and field.get("value")
        ]
        label = display_name or (fallback_values[0] if fallback_values else "")
        if label and label not in seen_labels:
            labels.append(label)
            seen_labels.add(label)
        references.append({"display_name": display_name or None, "fields": fields})

    return labels, references


def _normalize_metafield(
    metafield: Optional[Dict[str, Any]],
    *,
    rich_text: bool = False,
    references: bool = False,
) -> Dict[str, Any]:
    """Normalize a Shopify metafield while preserving useful debug snippets."""
    payload = {
        "value": (metafield or {}).get("value"),
        "type": (metafield or {}).get("type"),
    }
    if rich_text:
        payload["text"] = shopify_rich_text_to_plain_text(payload["value"])
    if references:
        labels, reference_records = _metafield_reference_labels(metafield)
        payload["labels"] = labels
        payload["references"] = reference_records
    return payload


def _option_dicts(options_payload: Any) -> List[Dict[str, Any]]:
    """Flatten Shopify product options into serializable dictionaries."""
    options = options_payload if isinstance(options_payload, list) else _connection_nodes(options_payload)
    normalized = []
    for option in options or []:
        if not isinstance(option, dict):
            continue
        normalized.append(
            {
                "id": option.get("id"),
                "name": option.get("name"),
                "position": option.get("position"),
                "values": list(option.get("values") or []),
            }
        )
    return normalized


def _selected_options_dict(selected_options: Any) -> Dict[str, str]:
    """Flatten variant selected options into `{option_name: value}`."""
    result: Dict[str, str] = {}
    for option in selected_options or []:
        if not isinstance(option, dict):
            continue
        name = _clean_plain_text(option.get("name"))
        value = _clean_plain_text(option.get("value"))
        if name and value:
            result[name] = value
    return result


def _extract_option_value(selected_options: Dict[str, str], candidates: List[str]) -> Optional[str]:
    """Find a selected option value using a list of case-insensitive option names."""
    normalized_candidates = {candidate.lower() for candidate in candidates}
    for name, value in selected_options.items():
        if name.lower() in normalized_candidates and value:
            return value
    return None


_FABRIC_TERMS = [
    "cotton",
    "linen",
    "silk",
    "wool",
    "cashmere",
    "viscose",
    "rayon",
    "modal",
    "lyocell",
    "tencel",
    "polyester",
    "polyamide",
    "nylon",
    "elastane",
    "spandex",
    "acrylic",
    "ramie",
    "hemp",
    "leather",
    "acetate",
    "cupro",
    "denim",
    "poplin",
    "twill",
    "chiffon",
    "georgette",
    "organza",
    "satin",
    "crepe",
    "lace",
    "jacquard",
    "velvet",
    "jersey",
    "knit",
    "woven",
]


def _find_exact_fabric_composition(text: str) -> Optional[str]:
    """
    Return an official exact composition snippet when percentages are present.

    This intentionally avoids treating visual or generic fabric names as exact
    fibre composition.
    """
    cleaned = _clean_plain_text(text)
    if "%" not in cleaned:
        return None

    term_pattern = "|".join(re.escape(term) for term in _FABRIC_TERMS)
    sentence_pattern = re.compile(rf"[^.\n;]*(?:\d{{1,3}}(?:\.\d+)?\s*%\s*(?:{term_pattern})).*?(?:[.;]|$)", re.I)
    matches = [match.group(0).strip(" .;") for match in sentence_pattern.finditer(cleaned)]
    if matches:
        return "; ".join(dict.fromkeys(matches))

    fallback_pattern = re.compile(rf"(?:\d{{1,3}}(?:\.\d+)?\s*%\s*(?:{term_pattern})(?:\s*[,/&+-]\s*)?)+", re.I)
    fallback = fallback_pattern.search(cleaned)
    if fallback:
        return fallback.group(0).strip(" ,;/&+-")
    return None


def _extract_fabric_family(*texts: str) -> Optional[str]:
    """Extract generic official fabric families from official text/metafields."""
    found: List[str] = []
    haystack = " ".join(text for text in texts if text).lower()
    for term in _FABRIC_TERMS:
        if re.search(rf"\b{re.escape(term)}\b", haystack) and term not in found:
            found.append(term)
    return ", ".join(found) if found else None


def _first_non_empty(values: List[Any]) -> Optional[str]:
    for value in values:
        cleaned = _clean_plain_text(value)
        if cleaned:
            return cleaned
    return None


class ShopifyGraphQLClient:
    """
    Client for the Shopify Admin GraphQL API.

    Supports both standard GraphQL queries and ShopifyQL analytics queries.
    Requires environment variables:
        SHOPIFY_SHOP_NAME    — store subdomain (e.g., "mystore")
        SHOPIFY_ACCESS_TOKEN — admin API access token (needs read_reports scope)
    """

    def __init__(
        self,
        *,
        brand_slug: Optional[str] = None,
        shop_name: Optional[str] = None,
        access_token: Optional[str] = None,
    ):
        self.brand_profile: Optional[BrandProfile] = (
            resolve_brand_profile(brand_slug) if brand_slug else None
        )
        self.brand_slug = self.brand_profile.slug if self.brand_profile else None
        self.brand_name = self.brand_profile.display_name if self.brand_profile else None

        self.shop_name = shop_name or self._get_env_value(
            self._candidate_env_names("SHOPIFY_SHOP_NAME")
        )
        self.access_token = access_token or self._get_env_value(
            self._candidate_env_names("SHOPIFY_ACCESS_TOKEN")
        )

        if not self.shop_name or not self.access_token:
            brand_hint = ""
            if self.brand_profile:
                brand_hint = (
                    f" for brand '{self.brand_profile.display_name}' "
                    f"({self.brand_profile.slug})"
                )
            raise ValueError(
                f"Missing required environment variables{brand_hint}:\n"
                f"  {self._candidate_env_names('SHOPIFY_SHOP_NAME')[0]} (preferred) or SHOPIFY_SHOP_NAME\n"
                f"  {self._candidate_env_names('SHOPIFY_ACCESS_TOKEN')[0]} (preferred) or SHOPIFY_ACCESS_TOKEN\n"
                "Please set these before running the script."
            )

        self.api_url = f"https://{self.shop_name}.myshopify.com/admin/api/2025-10/graphql.json"
        self.headers = {
            "Content-Type": "application/json",
            "X-Shopify-Access-Token": self.access_token,
        }

    def _candidate_env_names(self, suffix: str) -> List[str]:
        """Return env var names to try for a given credential suffix."""
        names: List[str] = []
        if self.brand_profile:
            names.append(self.brand_profile.env_var(suffix))
        names.append(suffix)
        return names

    @staticmethod
    def _get_env_value(names: List[str]) -> Optional[str]:
        """Return the first non-empty environment value from a list of variable names."""
        for name in names:
            value = os.getenv(name)
            if value:
                return value
        return None

    def query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Shopify API.

        Raises:
            Exception: If the HTTP request fails or Shopify returns GraphQL errors.
        """
        payload = {"query": query_string}
        if variables:
            payload["variables"] = variables

        # Retry up to 5 times to handle transient Shopify rate-limit (throttle) errors.
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

            # If Shopify is throttling us, wait the recommended time and retry.
            # Any other error type is a hard failure — no retry.
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
        """Return True if any error in the list has the THROTTLED extension code."""
        if not isinstance(errors, list):
            return False
        for err in errors:
            code = (((err or {}).get("extensions") or {}).get("code") or "").upper()
            if code == "THROTTLED":
                return True
        return False

    @staticmethod
    def _throttle_wait_seconds(errors: List[Dict[str, Any]], attempt: int) -> int:
        """
        Calculate how long to wait before retrying after a throttle error.

        Shopify includes a windowResetAt timestamp in the error payload.
        We use it when available so we don't wait longer than necessary.
        Falls back to an exponential-ish default (3s * attempt, capped at 30s).
        """
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

        variant_prices = []
        variant_nodes = (product_node.get("variants") or {}).get("nodes", [])
        for variant in variant_nodes:
            price = variant.get("price")
            if price in [None, ""]:
                continue
            variant_prices.append(str(price))

        return {
            "id": product_id,
            "title": product_node.get("title"),
            "handle": product_node.get("handle"),
            "status": product_node.get("status"),
            "primary_image": self._extract_primary_media_image(product_node),
            "variant_prices": variant_prices,
        }

    @staticmethod
    def _normalize_product_detail_record(product_node: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize a Product node into the product-detail JSON contract."""
        product_id = product_node.get("id")
        if not product_id:
            return None

        description_text = description_html_to_text(product_node.get("descriptionHtml"))

        metafields_normalized = {
            "fabric": _normalize_metafield(product_node.get("fabric"), references=True),
            "color_pattern": _normalize_metafield(product_node.get("colorPattern"), references=True),
            "fit": _normalize_metafield(product_node.get("fit"), references=True),
            "neckline": _normalize_metafield(product_node.get("neckline"), references=True),
            "sleeve_length_type": _normalize_metafield(product_node.get("sleeveLengthType"), references=True),
            "clothing_features": _normalize_metafield(product_node.get("clothingFeatures"), references=True),
            "materials": _normalize_metafield(product_node.get("materials"), rich_text=True),
            "product_size": _normalize_metafield(product_node.get("productSize"), rich_text=True),
            "product_features": _normalize_metafield(product_node.get("productFeatures"), rich_text=True),
            "origin_country": _normalize_metafield(product_node.get("originCountry")),
            "siblings": _normalize_metafield(product_node.get("siblings")),
            "sibling_color": _normalize_metafield(product_node.get("siblingColor")),
            "collection_name": _normalize_metafield(product_node.get("collectionName"), references=True),
        }

        variants = []
        selected_option_values: Dict[str, List[str]] = {}
        for variant in _connection_nodes(product_node.get("variants") or {}):
            selected_options = _selected_options_dict(variant.get("selectedOptions"))
            for option_name, option_value in selected_options.items():
                bucket = selected_option_values.setdefault(option_name, [])
                if option_value not in bucket:
                    bucket.append(option_value)
            image = variant.get("image") or {}
            variants.append(
                {
                    "id": variant.get("id"),
                    "title": variant.get("title"),
                    "sku": variant.get("sku"),
                    "price": variant.get("price"),
                    "compare_at_price": variant.get("compareAtPrice"),
                    "barcode": variant.get("barcode"),
                    "available_for_sale": variant.get("availableForSale"),
                    "inventory_quantity": variant.get("inventoryQuantity"),
                    "selected_options": selected_options,
                    "colour": _extract_option_value(selected_options, ["color", "colour", "color pattern"]),
                    "size": _extract_option_value(selected_options, ["size"]),
                    "image": {
                        "url": image.get("url"),
                        "alt_text": image.get("altText"),
                    } if image else None,
                }
            )

        collections = [
            {"id": node.get("id"), "title": node.get("title")}
            for node in _connection_nodes(product_node.get("collections") or {})
        ]
        media = []
        for node in _connection_nodes(product_node.get("media") or {}):
            image = node.get("image") or {}
            if not node.get("id") and not image.get("url"):
                continue
            media.append(
                {
                    "id": node.get("id"),
                    "url": image.get("url"),
                    "alt_text": image.get("altText"),
                    "width": image.get("width"),
                    "height": image.get("height"),
                }
            )

        materials_text = metafields_normalized["materials"].get("text") or ""
        fabric_labels = metafields_normalized["fabric"].get("labels") or []
        color_labels = metafields_normalized["color_pattern"].get("labels") or []
        fit_labels = metafields_normalized["fit"].get("labels") or []
        neckline_labels = metafields_normalized["neckline"].get("labels") or []
        sleeve_labels = metafields_normalized["sleeve_length_type"].get("labels") or []
        feature_labels = metafields_normalized["clothing_features"].get("labels") or []
        collection_labels = metafields_normalized["collection_name"].get("labels") or []

        composition_sources = [
            ("custom.materials", materials_text),
            ("shopify.fabric", "; ".join(fabric_labels)),
            ("descriptionHtml", description_text),
        ]
        exact_composition = None
        exact_source = None
        for source, text in composition_sources:
            exact_composition = _find_exact_fabric_composition(text)
            if exact_composition:
                exact_source = source
                break

        fabric_family = _extract_fabric_family(
            materials_text,
            "; ".join(fabric_labels),
            description_text,
        )
        option_colour_values: List[str] = []
        for values in selected_option_values.items():
            option_name, option_list = values
            if option_name.lower() in {"color", "colour", "color pattern"}:
                option_colour_values.extend(option_list)

        official_colour = _first_non_empty(
            [
                "; ".join(color_labels),
                "; ".join(option_colour_values),
                metafields_normalized["sibling_color"].get("value"),
            ]
        )
        colour_source = None
        if color_labels:
            colour_source = "shopify.color-pattern"
        elif option_colour_values:
            colour_source = "variant.selectedOptions"
        elif metafields_normalized["sibling_color"].get("value"):
            colour_source = "custom.sibling_color"

        official_product_attributes = {
            "official_fabric_composition": exact_composition or "Unknown",
            "official_fabric_source": exact_source,
            "official_fabric_confidence": "high" if exact_composition else "none",
            "official_material_text": materials_text or None,
            "official_fabric_family": fabric_family,
            "official_colour": official_colour,
            "official_colour_source": colour_source,
            "official_fit": "; ".join(fit_labels) or None,
            "official_neckline": "; ".join(neckline_labels) or None,
            "official_sleeve_length": "; ".join(sleeve_labels) or None,
            "official_clothing_features": "; ".join(feature_labels) or None,
            "official_collection_name": "; ".join(collection_labels) or None,
            "official_product_features": metafields_normalized["product_features"].get("text") or None,
            "official_product_size": metafields_normalized["product_size"].get("text") or None,
            "origin_country": metafields_normalized["origin_country"].get("value"),
        }

        return {
            "id": product_id,
            "title": product_node.get("title"),
            "handle": product_node.get("handle"),
            "description_text": description_text,
            "tags": list(product_node.get("tags") or []),
            "product_type": product_node.get("productType"),
            "vendor": product_node.get("vendor"),
            "status": product_node.get("status"),
            "options": _option_dicts(product_node.get("options")),
            "collections": collections,
            "media": media,
            "variants": variants,
            "selected_option_values": selected_option_values,
            "metafields_normalized": metafields_normalized,
            "official_product_attributes": official_product_attributes,
        }

    def fetch_product_detail_records_by_ids(
        self,
        product_gids: List[str],
        batch_size: int = 25,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Fetch official product detail records for Product GIDs via Admin GraphQL.

        Returns:
            Mapping: product_gid -> normalized product detail record.
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
        query ProductDetailsByIds($ids: [ID!]!) {
          nodes(ids: $ids) {
            __typename
            ... on Product {
              id
              title
              descriptionHtml
              handle
              productType
              vendor
              tags
              status

              options {
                id
                name
                position
                values
              }

              collections(first: 10) {
                edges {
                  node { id title }
                }
              }

              media(first: 10) {
                edges {
                  node {
                    ... on MediaImage {
                      id
                      image { url altText width height }
                    }
                  }
                }
              }

              fabric: metafield(namespace: "shopify", key: "fabric") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              colorPattern: metafield(namespace: "shopify", key: "color-pattern") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              fit: metafield(namespace: "shopify", key: "fit") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              neckline: metafield(namespace: "shopify", key: "neckline") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              sleeveLengthType: metafield(namespace: "shopify", key: "sleeve-length-type") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              clothingFeatures: metafield(namespace: "shopify", key: "clothing-features") {
                value
                references(first: 10) {
                  nodes {
                    ... on Metaobject {
                      displayName
                      fields { key value }
                    }
                  }
                }
              }

              materials: metafield(namespace: "custom", key: "materials") {
                value
                type
              }

              productSize: metafield(namespace: "custom", key: "product_size") {
                value
                type
              }

              productFeatures: metafield(namespace: "custom", key: "product_features") {
                value
                type
              }

              originCountry: metafield(namespace: "custom", key: "origin_country") {
                value
              }

              siblings: metafield(namespace: "custom", key: "siblings") {
                value
              }

              siblingColor: metafield(namespace: "custom", key: "sibling_color") {
                value
              }

              collectionName: metafield(namespace: "custom", key: "collection_name") {
                value
                reference {
                  ... on Metaobject {
                    displayName
                    fields { key value }
                  }
                }
              }

              variants(first: 50) {
                edges {
                  node {
                    id
                    title
                    sku
                    price
                    compareAtPrice
                    barcode
                    availableForSale
                    inventoryQuantity
                    selectedOptions { name value }
                    image { url altText }
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
                record = self._normalize_product_detail_record(node)
                if record:
                    records[record["id"]] = record

        return records

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
        # Deduplicate IDs before hitting the API to avoid redundant fetches.
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
                    status
                    variants(first: 50) {
                        nodes {
                            price
                        }
                    }
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

        # Shopify's nodes() lookup accepts at most 250 IDs per request.
        batch_size = max(1, min(batch_size, 250))
        records: Dict[str, Dict[str, Any]] = {}

        # Process in pages so large ID lists don't exceed the per-request limit.
        for start in range(0, len(unique_ids), batch_size):
            batch = unique_ids[start:start + batch_size]
            result = self.query(graphql_query, variables={"ids": batch})
            nodes = result.get("data", {}).get("nodes", [])

            for node in nodes:
                # nodes() can return non-Product types (e.g. variants) — skip them.
                if not node or node.get("__typename") != "Product":
                    continue
                record = self._build_product_image_record(node)
                if record:
                    records[record["id"]] = record

        return records

    def find_product_image_records_by_exact_title(
        self,
        title: str,
        first: int = 25,
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
                    status
                    variants(first: 50) {
                        nodes {
                            price
                        }
                    }
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
