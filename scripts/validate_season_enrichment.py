#!/usr/bin/env python3
"""
Validate generated season JSON enrichment quality.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List


METAOBJECT_FIELDS = [
    "fabric",
    "color_pattern",
    "fit",
    "neckline",
    "sleeve_length_type",
    "clothing_features",
    "collection_name",
]
BAD_FABRIC_PATTERNS = [
    re.compile(r"\bCare\s*:", re.I),
    re.compile(r"\bCountry\s+of\s+Origin\b", re.I),
    re.compile(r"\bDesigned\s+in\b", re.I),
    re.compile(r"\bMade\s+in\b", re.I),
]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as file_obj:
        return json.load(file_obj)


def _color_candidate_available(row: Dict[str, Any], detail: Dict[str, Any]) -> bool:
    metafields = detail.get("metafields_normalized") or {}
    if _clean((metafields.get("sibling_color") or {}).get("value")):
        return True

    selected_variant = detail.get("selected_variant") or {}
    selected_options = selected_variant.get("selected_options") or detail.get("selected_option_values") or {}
    if isinstance(selected_options, dict):
        for option_name, option_value in selected_options.items():
            if option_name.lower() in {"color", "colour"} and _clean(option_value):
                return True

    for tag in detail.get("tags") or []:
        if re.match(r"^(?:colour|color)[ _-]+.+$", _clean(tag), re.I):
            return True

    if " - " in _clean(detail.get("title") or row.get("product_title")):
        return True

    if (metafields.get("color_pattern") or {}).get("labels"):
        return True
    return False


def _validate_row(row: Dict[str, Any], index: int) -> List[str]:
    issues: List[str] = []
    detail = row.get("product_detail")
    if not isinstance(detail, dict):
        return [f"row {index}: missing product_detail"]

    if row.get("product_image") is None:
        issues.append(f"row {index}: missing product_image")

    selected_variant = detail.get("selected_variant") or {}
    selected_variant_sku = _clean(selected_variant.get("sku"))
    row_sku = _clean(row.get("product_variant_sku"))
    if row_sku and selected_variant_sku and row_sku != selected_variant_sku:
        issues.append(
            f"row {index}: selected_variant.sku {selected_variant_sku!r} does not match product_variant_sku {row_sku!r}"
        )

    metafields = detail.get("metafields_normalized") or {}
    for key in METAOBJECT_FIELDS:
        payload = metafields.get(key) or {}
        raw_value = _clean(payload.get("value"))
        labels = payload.get("labels") or []
        if "gid://shopify/Metaobject/" in raw_value and not labels:
            issues.append(f"row {index}: metafield {key} contains raw metaobject GIDs but has no resolved labels")

    attrs = detail.get("official_product_attributes") or {}
    fabric_composition = _clean(attrs.get("official_fabric_composition"))
    if fabric_composition:
        for pattern in BAD_FABRIC_PATTERNS:
            if pattern.search(fabric_composition):
                issues.append(
                    f"row {index}: official_fabric_composition contains care/origin text: {fabric_composition!r}"
                )
                break

    if _color_candidate_available(row, detail) and not _clean(attrs.get("official_colour")):
        issues.append(f"row {index}: official_colour missing despite available colour sources")

    return issues


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate a generated season JSON enrichment payload.")
    parser.add_argument("--season-json", required=True, help="Path to the generated season JSON report.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    payload = _load_json(Path(args.season_json))
    rows = ((payload.get("season_product_performance") or {}).get("rows") or [])
    if not rows:
        print("No rows found in season JSON.")
        return 1

    issues: List[str] = []
    for index, row in enumerate(rows, start=1):
        issues.extend(_validate_row(row, index))

    if issues:
        print("Validation failed:")
        for issue in issues:
            print(f"- {issue}")
        print(f"\nTotal issues: {len(issues)}")
        return 1

    print(f"Validation passed for {len(rows)} rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
