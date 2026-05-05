#!/usr/bin/env python3
"""
Season-aware entry point for Steele-style product analysis.

This script fetches one season's product rows, enriches every row with product
images when possible, and writes JSON outputs into the report source directory.
The shell wrapper uses these artifacts as the source for a Codex-written report.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from src.brand_profiles import resolve_brand_profile
from src.season_profiles import resolve_season_profile
from src.season_reports import run_season_report
from src.shopify_client import ShopifyGraphQLClient


DEFAULT_BRAND_SLUG = os.getenv("REPORT_BRAND_SLUG", "steele")
DEFAULT_SEASON_SLUG = os.getenv("REPORT_SEASON_SLUG", "winter25")
DEFAULT_OUTPUT_ROOT = os.getenv("REPORT_OUTPUT_ROOT", "/Users/mrinalsood/temp")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a season-aware Shopify product report.")
    parser.add_argument("--brand", default=DEFAULT_BRAND_SLUG, help="Brand slug, e.g. steele")
    parser.add_argument("--season", default=DEFAULT_SEASON_SLUG, help="Season slug, e.g. winter25")
    parser.add_argument(
        "--reports-base-dir",
        default=os.getenv("REPORTS_BASE_DIR"),
        help="Directory where JSON outputs should be written.",
    )
    parser.add_argument(
        "--output-dir",
        default=os.getenv("REPORT_OUTPUT_DIR"),
        help="Directory where product images and packaged report assets should be written.",
    )
    parser.add_argument(
        "--brand-display-name",
        default=os.getenv("REPORT_BRAND_DISPLAY_NAME"),
        help="Optional display name override for the brand.",
    )
    parser.add_argument(
        "--season-display-name",
        default=os.getenv("REPORT_SEASON_DISPLAY_NAME"),
        help="Optional display name override for the season.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    brand_profile = resolve_brand_profile(args.brand)
    season_profile = resolve_season_profile(args.season)
    brand_display_name = args.brand_display_name or brand_profile.display_name
    season_display_name = args.season_display_name or season_profile.display_name

    reports_base_dir = args.reports_base_dir or os.path.join(
        DEFAULT_OUTPUT_ROOT,
        "reports",
        f"{brand_profile.slug}_{season_profile.slug}_report_source",
    )
    output_dir = args.output_dir or os.path.join(
        DEFAULT_OUTPUT_ROOT,
        "reports",
        f"{brand_profile.slug}_{season_profile.slug}_output",
    )

    os.makedirs(reports_base_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    print("=" * 72)
    print(
        f"Shopify Season Insight Agent - {brand_display_name} "
        f"({season_display_name})"
    )
    print("=" * 72)
    print(f"[STEP 0] Report source dir: {reports_base_dir}")
    print(f"[STEP 0] Output dir: {output_dir}")

    print("\n[STEP 1] Connecting to Shopify...")
    try:
        client = ShopifyGraphQLClient(brand_slug=brand_profile.slug)
        print(f"  ✓ Connected to store: {client.shop_name}")
    except Exception as exc:
        print(f"  ✗ Connection failed: {exc}")
        return 1

    print("\n[STEP 2] Building season report...")
    try:
        season_report_data = run_season_report(
            client=client,
            brand_slug=brand_profile.slug,
            season_profile=season_profile,
            report_output_dir=output_dir,
        )
    except Exception as exc:
        print(f"  ✗ Season report fetch failed: {exc}")
        return 1

    print(
        "  ✓ Rows fetched: "
        f"{len(season_report_data.get('season_product_performance', {}).get('rows', []))}"
    )
    print(
        "  ✓ Image enrichment summary: "
        f"{season_report_data.get('season_product_performance', {}).get('image_enrichment_summary', {})}"
    )
    print(
        "  ✓ Product detail enrichment summary: "
        f"{season_report_data.get('product_detail_enrichment_summary', {})}"
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    report_filename = f"{brand_profile.slug}_{season_profile.slug}_report.json"
    report_path = os.path.join(reports_base_dir, report_filename)
    index_filename = f"{brand_profile.slug}_{season_profile.slug}_product_image_index.json"
    index_path = os.path.join(reports_base_dir, index_filename)

    season_output = {
        "generated_at": timestamp,
        "brand": {
            "slug": brand_profile.slug,
            "display_name": brand_display_name,
        },
        "season": {
            "slug": season_profile.slug,
            "display_name": season_display_name,
            "shopify_tag": season_profile.shopify_tag,
        },
        "report_period": season_report_data.get("report_period", {}),
        "report_name": season_report_data.get("report_name"),
        "queries": season_report_data.get("queries", {}),
        "query_flags": season_report_data.get("query_flags", {}),
        "season_product_performance": season_report_data.get("season_product_performance", {}),
        "product_image_focus": season_report_data.get("product_image_focus", {}),
        "product_detail_enrichment_summary": season_report_data.get("product_detail_enrichment_summary", {}),
        "product_count": season_report_data.get("product_count", 0),
        "product_access_ok": season_report_data.get("product_access_ok", False),
        "product_access_error": season_report_data.get("product_access_error"),
    }

    try:
        with open(report_path, "w", encoding="utf-8") as file_obj:
            json.dump(season_output, file_obj, indent=2, default=str)
        print(f"  ✓ Saved: {report_filename}")
    except Exception as exc:
        print(f"  ✗ Failed to save {report_filename}: {exc}")
        return 1

    try:
        with open(index_path, "w", encoding="utf-8") as file_obj:
            json.dump(
                {
                    "generated_at": timestamp,
                    "report_period": season_output["report_period"],
                    "top_limit": len(season_report_data.get("season_product_performance", {}).get("rows", [])),
                    "entries": season_report_data.get("product_image_index", []),
                },
                file_obj,
                indent=2,
                default=str,
            )
        print(f"  ✓ Saved: {index_filename}")
    except Exception as exc:
        print(f"  ✗ Failed to save {index_filename}: {exc}")
        return 1

    print("\n" + "=" * 72)
    print(f"✓ Success - season report generated in {reports_base_dir}")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
