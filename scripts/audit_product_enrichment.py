#!/usr/bin/env python3
"""
Audit one enriched season-report product row, with optional live Shopify diff.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.shopify_client import ShopifyGraphQLClient


AUDIT_QUERY_PATH = REPO_ROOT / "scripts" / "graphql" / "audit_product_details.graphql"
METAOBJECT_FIELDS = [
    "fabric",
    "color_pattern",
    "fit",
    "neckline",
    "sleeve_length_type",
    "clothing_features",
    "collection_name",
]


def _clean(value: Any) -> Optional[str]:
    text = str(value or "").strip()
    return text or None


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _product_gid_for_row(row: Dict[str, Any]) -> Optional[str]:
    detail = row.get("product_detail") or {}
    gid = _clean(detail.get("id"))
    if gid:
        return gid
    return ShopifyGraphQLClient.to_product_gid(row.get("product_id"))


def _selected_variant_for_row(row: Dict[str, Any]) -> Dict[str, Any]:
    detail = row.get("product_detail") or {}
    selected_variant = detail.get("selected_variant")
    if isinstance(selected_variant, dict):
        return selected_variant
    sku = _clean(row.get("product_variant_sku"))
    for variant in detail.get("variants") or []:
        if _clean(variant.get("sku")) == sku:
            return variant
    return {}


def _match_row(
    rows: List[Dict[str, Any]],
    *,
    sku: Optional[str],
    product_id: Optional[str],
    product_title: Optional[str],
) -> Dict[str, Any]:
    for row in rows:
        if sku and _clean(row.get("product_variant_sku")) == _clean(sku):
            return row
        if product_title and _clean(row.get("product_title")) == _clean(product_title):
            return row
        if product_id:
            raw_product_id = _clean(row.get("product_id"))
            row_gid = ShopifyGraphQLClient.to_product_gid(raw_product_id)
            wanted_gid = ShopifyGraphQLClient.to_product_gid(product_id) or _clean(product_id)
            if raw_product_id == product_id or row_gid == wanted_gid:
                return row
            detail_gid = _clean((row.get("product_detail") or {}).get("id"))
            if detail_gid and detail_gid == wanted_gid:
                return row
    raise SystemExit("No matching row found in season JSON.")


def _collections_titles(detail: Dict[str, Any]) -> List[str]:
    return [str(item.get("title")) for item in (detail.get("collections") or []) if item.get("title")]


def _media_urls(detail: Dict[str, Any]) -> List[str]:
    return [str(item.get("url")) for item in (detail.get("media") or []) if item.get("url")]


def _print_summary(row: Dict[str, Any]) -> None:
    detail = row.get("product_detail") or {}
    attrs = detail.get("official_product_attributes") or {}
    selected_variant = _selected_variant_for_row(row)
    image_payload = row.get("product_image") or {}
    metafields = detail.get("metafields_normalized") or {}

    print(f"Product title: {row.get('product_title')}")
    print(f"Product ID: {row.get('product_id')}")
    print(f"Product GID: {detail.get('id')}")
    print(f"Selected SKU: {row.get('product_variant_sku')}")
    print(f"Selected variant ID: {selected_variant.get('id')}")
    print(
        "Commercial metrics: "
        f"net_sales={row.get('net_sales')} gross_sales={row.get('gross_sales')} "
        f"net_items_sold={row.get('net_items_sold')} returns={row.get('returns')} "
        f"returned_quantity_rate={row.get('returned_quantity_rate')} discounts={row.get('discounts')}"
    )
    print(f"Description text: {detail.get('description_text')}")
    print(f"Tags: {detail.get('tags')}")
    print(f"Collections: {_collections_titles(detail)}")
    print(f"Media count: {len(detail.get('media') or [])}")
    print(f"Product image local path: {image_payload.get('local_path')}")
    print(f"Variant selected options: {selected_variant.get('selected_options') or detail.get('selected_option_values')}")
    print(f"custom.materials parsed text: {(metafields.get('materials') or {}).get('text')}")
    print(f"official_fabric_composition: {attrs.get('official_fabric_composition')}")
    print(f"care_instructions: {attrs.get('care_instructions')}")
    print(f"origin_country: {attrs.get('origin_country')}")
    print(f"official_colour: {attrs.get('official_colour')}")
    print(f"official_colour_source: {attrs.get('official_colour_source')}")
    for key in METAOBJECT_FIELDS:
        payload = metafields.get(key) or {}
        print(
            f"metafield.{key}: raw={payload.get('value')} labels={payload.get('labels')} "
            f"references={payload.get('references')}"
        )


def _read_audit_query() -> str:
    return AUDIT_QUERY_PATH.read_text(encoding="utf-8")


def _fetch_live_product_detail(client: ShopifyGraphQLClient, product_gid: str) -> Dict[str, Any]:
    query = _read_audit_query()
    result = client.query(query, variables={"id": product_gid})
    product = (result.get("data") or {}).get("product")
    if not product:
        raise SystemExit(f"Live Shopify query returned no product for {product_gid}")
    resolved_metaobjects = client._fetch_metaobjects_by_ids(
        client._collect_unresolved_metaobject_gids([{"__typename": "Product", **product}])
    )
    normalized = ShopifyGraphQLClient._normalize_product_detail_record(
        {"__typename": "Product", **product},
        resolved_metaobjects=resolved_metaobjects,
    )
    if not normalized:
        raise SystemExit(f"Failed to normalize live Shopify product {product_gid}")
    return normalized


def _compare_values(json_value: Any, shopify_value: Any) -> str:
    left_missing = json_value in [None, "", [], {}]
    right_missing = shopify_value in [None, "", [], {}]
    if left_missing and right_missing:
        return "MATCH"
    if left_missing and not right_missing:
        return "MISSING_IN_JSON"
    if not left_missing and right_missing:
        return "MISSING_IN_SHOPIFY"
    if json_value == shopify_value:
        return "MATCH"
    return "DIFFERENT"


def _print_diff(label: str, json_value: Any, shopify_value: Any) -> None:
    status = _compare_values(json_value, shopify_value)
    print(f"{status} | {label}")
    print(f"  json: {json_value}")
    print(f"  shopify: {shopify_value}")


def _run_live_diff(row: Dict[str, Any], brand_slug: str) -> None:
    product_gid = _product_gid_for_row(row)
    if not product_gid:
        raise SystemExit("Selected row has no product ID/GID to audit live.")

    client = ShopifyGraphQLClient(brand_slug=brand_slug)
    live_detail = _fetch_live_product_detail(client, product_gid)
    json_detail = row.get("product_detail") or {}
    json_attrs = json_detail.get("official_product_attributes") or {}
    live_attrs = live_detail.get("official_product_attributes") or {}
    json_metafields = json_detail.get("metafields_normalized") or {}
    live_metafields = live_detail.get("metafields_normalized") or {}

    json_variant = _selected_variant_for_row(row)
    live_variant = {}
    for variant in live_detail.get("variants") or []:
        if _clean(variant.get("sku")) == _clean(row.get("product_variant_sku")):
            live_variant = variant
            break

    print("\nLive Shopify diff:")
    _print_diff("product.title", _clean(row.get("product_title")), _clean(live_detail.get("title")))
    _print_diff("product.handle", _clean(json_detail.get("handle")), _clean(live_detail.get("handle")))
    _print_diff("product.tags", sorted(json_detail.get("tags") or []), sorted(live_detail.get("tags") or []))
    _print_diff("variant.sku", _clean(row.get("product_variant_sku")), _clean(live_variant.get("sku")))
    _print_diff("variant.id", _clean(json_variant.get("id")), _clean(live_variant.get("id")))
    _print_diff(
        "custom.materials",
        _clean((json_metafields.get("materials") or {}).get("text")),
        _clean((live_metafields.get("materials") or {}).get("text")),
    )
    _print_diff(
        "custom.product_features",
        _clean((json_metafields.get("product_features") or {}).get("text")),
        _clean((live_metafields.get("product_features") or {}).get("text")),
    )
    _print_diff(
        "custom.product_size",
        _clean((json_metafields.get("product_size") or {}).get("text")),
        _clean((live_metafields.get("product_size") or {}).get("text")),
    )
    _print_diff(
        "custom.sibling_color",
        _clean((json_metafields.get("sibling_color") or {}).get("value")),
        _clean((live_metafields.get("sibling_color") or {}).get("value")),
    )
    for key in ["fabric", "color_pattern", "fit", "neckline", "sleeve_length_type"]:
        _print_diff(
            f"metaobject.{key}.labels",
            (json_metafields.get(key) or {}).get("labels") or [],
            (live_metafields.get(key) or {}).get("labels") or [],
        )
    _print_diff("official_colour", _clean(json_attrs.get("official_colour")), _clean(live_attrs.get("official_colour")))
    _print_diff("media.urls", sorted(_media_urls(json_detail)), sorted(_media_urls(live_detail)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit one enriched product in a season JSON report.")
    parser.add_argument("--season-json", required=True, help="Path to the generated season JSON report.")
    parser.add_argument("--brand", help="Brand slug for live Shopify checks. Defaults to report brand slug.")
    selector_group = parser.add_mutually_exclusive_group(required=True)
    selector_group.add_argument("--sku", help="Exact SKU to audit, e.g. STC200-S")
    selector_group.add_argument("--product-id", help="Numeric product ID or Product GID to audit.")
    selector_group.add_argument("--product-title", help='Exact product title, e.g. "Gabrielle Dress - Chene Stripe"')
    parser.add_argument(
        "--live-shopify-check",
        action="store_true",
        help="Fetch the selected product live from Shopify and print a compact diff.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = _load_json(Path(args.season_json))
    rows = ((payload.get("season_product_performance") or {}).get("rows") or [])
    if not rows:
        raise SystemExit("Season JSON contains no product rows.")

    row = _match_row(
        rows,
        sku=args.sku,
        product_id=args.product_id,
        product_title=args.product_title,
    )
    _print_summary(row)

    if args.live_shopify_check:
        brand_slug = args.brand or ((payload.get("brand") or {}).get("slug"))
        if not brand_slug:
            raise SystemExit("Brand slug is required for --live-shopify-check.")
        _run_live_diff(row, brand_slug)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
