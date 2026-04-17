#!/usr/bin/env python3
"""
The main entry point for the Sales Insight Agent.

This script orchestrates the annual reporting process:
1. Connects to Shopify.
2. Fetches annual product and dress-variant data.
3. Enriches product rows with images.
4. Saves annual JSON output into numbered generation folders.
"""

import os
import json
import sys
from datetime import datetime, timezone

# We import our specialized tools from the 'src' folder
from src.shopify_client import ShopifyGraphQLClient
from src.product_reports import run_annual_report, select_ranked_rows
from src.image_enrichment import (
    TOP_PRODUCTS_IMAGE_LIMIT,
    enrich_channel_product_rows,
    mark_channel_image_enrichment_skipped,
)

ANNUAL_REPORT_YEAR = 2025
DEFAULT_REPORTS_BASE_DIR = os.path.expanduser("~/Desktop/annual_report_runs")


def get_reports_source_dir(base_dir: str | None = None):
    """
    Resolve the JSON output directory for a report run.
    """
    if base_dir is None:
        base_dir = os.getenv("REPORTS_BASE_DIR", DEFAULT_REPORTS_BASE_DIR)

    os.makedirs(base_dir, exist_ok=True)
    return base_dir


def main():
    print("=" * 60)
    print(f"Shopify Sales Insight Agent — Annual Report ({ANNUAL_REPORT_YEAR})")
    print("=" * 60)

    # --- STEP 0: Create the Output Folder ---
    reports_dir = get_reports_source_dir()
    output_root_dir = os.getenv("REPORT_OUTPUT_DIR", reports_dir)
    os.makedirs(output_root_dir, exist_ok=True)
    print(f"\n[STEP 0] Saving report JSON to: {reports_dir}")
    print(f"[STEP 0] Saving report assets to: {output_root_dir}")

    # --- STEP 1: Connect to Shopify ---
    print("\n[STEP 1] Connecting to Shopify...")
    try:
        client = ShopifyGraphQLClient()
        print(f"✓ Connected to store: {client.shop_name}")
    except Exception as e:
        print(f"✗ Connection failed: {e}")
        sys.exit(1)

    # --- STEP 1.5: Verify Product API Access (for image enrichment) ---
    print("\n[STEP 1.5] Checking Product API access for image enrichment...")
    products_access_ok, products_access_error = client.check_read_products_access()
    if products_access_ok:
        print("✓ Product API access confirmed (read_products scope available)")
    else:
        print("⚠ Product API access unavailable. Reports will still run without images.")
        print(f"  Reason: {products_access_error}")

    annual_report_data = None
    print(f"\n[STEP 3] Fetching annual report data ({ANNUAL_REPORT_YEAR})...")
    try:
        annual_report_data = run_annual_report(
            client=client,
            year=ANNUAL_REPORT_YEAR,
        )
        print(
            "  ✓ Annual report rows: "
            f"top={len(annual_report_data.get('top_performers', []))}, "
            f"under={len(annual_report_data.get('underperformers', []))}, "
            f"all_products={len(annual_report_data.get('all_products_sold', {}).get('rows', []))}, "
            f"dress_variants={len(annual_report_data.get('dress_variant_families', {}).get('rows', []))}"
        )
    except Exception as e:
        print(f"  ⚠ Annual report fetch failed: {e}")
        sys.exit(1)

    # --- STEP 4: Save the Files ---
    print("\n[STEP 4] Saving annual JSON files...")

    timestamp = datetime.now(timezone.utc).isoformat()
    saved_count = 0
    # Collects one entry per enriched product row for a flat, easy-to-query index file.
    product_image_index = []
    year = int(annual_report_data.get("year", ANNUAL_REPORT_YEAR))
    since_year = f"{year}-01-01"
    until_year = f"{year}-12-31"

    # Unpack report sections for clarity — each variable maps to a distinct query result.
    top_rows = annual_report_data.get("top_performers", [])
    under_rows = annual_report_data.get("underperformers", [])
    all_products_sold = annual_report_data.get("all_products_sold", {})
    all_products_rows = all_products_sold.get("rows", [])
    dress_variant_families = annual_report_data.get("dress_variant_families", {})
    dress_variant_rows = dress_variant_families.get("rows", [])
    dress_variant_top_rows = dress_variant_families.get("top_rows", [])
    dress_variant_bottom_rows = dress_variant_families.get("bottom_rows", [])

    annual_top_limit = min(20, TOP_PRODUCTS_IMAGE_LIMIT)
    # Run image enrichment only if the Product API token scope is confirmed.
    if products_access_ok:
        top_image_summary, top_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_top_{year}",
            product_rows=top_rows,
            generation_dir=output_root_dir,
            top_limit=annual_top_limit,
        )
        under_image_summary, under_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_under_{year}",
            product_rows=under_rows,
            generation_dir=output_root_dir,
            top_limit=annual_top_limit,
        )
    else:
        top_image_summary, top_image_index_rows = mark_channel_image_enrichment_skipped(
            product_rows=top_rows,
            reason=f"Product API unavailable: {products_access_error}",
            top_limit=annual_top_limit,
        )
        under_image_summary, under_image_index_rows = mark_channel_image_enrichment_skipped(
            product_rows=under_rows,
            reason=f"Product API unavailable: {products_access_error}",
            top_limit=annual_top_limit,
        )

    product_image_index.extend(top_image_index_rows)
    product_image_index.extend(under_image_index_rows)

    if products_access_ok:
        dress_top_image_summary, dress_top_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_dress_variant_top_{year}",
            product_rows=dress_variant_top_rows,
            generation_dir=output_root_dir,
            top_limit=20,
        )
        dress_bottom_image_summary, dress_bottom_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_dress_variant_bottom_{year}",
            product_rows=dress_variant_bottom_rows,
            generation_dir=output_root_dir,
            top_limit=20,
        )
    else:
        dress_top_image_summary, dress_top_image_index_rows = mark_channel_image_enrichment_skipped(
            product_rows=dress_variant_top_rows,
            reason=f"Product API unavailable: {products_access_error}",
            top_limit=20,
        )
        dress_bottom_image_summary, dress_bottom_image_index_rows = mark_channel_image_enrichment_skipped(
            product_rows=dress_variant_bottom_rows,
            reason=f"Product API unavailable: {products_access_error}",
            top_limit=20,
        )

    product_image_index.extend(dress_top_image_index_rows)
    product_image_index.extend(dress_bottom_image_index_rows)

    # Pre-slice convenience lists used by the AI agent and marketing report templates.
    top_20_products = select_ranked_rows(top_rows, limit=20)
    bottom_20_products = select_ranked_rows(under_rows, limit=20)
    top_5_products = select_ranked_rows(top_rows, limit=5)
    bottom_5_products = select_ranked_rows(under_rows, limit=5)

    annual_output = {
        "generated_at": timestamp,
        "report_period": {"since": since_year, "until": until_year},
        "report_name": f"annual_performance_{year}",
        "queries": annual_report_data.get("queries", {}),
        "top_performers": {
            "query_year": year,
            "ranking": "net_sales_desc",
            "image_enrichment_summary": top_image_summary,
            "rows": top_rows,
            "top_20_rows": top_20_products,
        },
        "underperformers": {
            "query_year": year,
            "ranking": "net_sales_asc",
            "image_enrichment_summary": under_image_summary,
            "rows": under_rows,
            "bottom_20_rows": bottom_20_products,
        },
        "all_products_sold": {
            "query_year": year,
            "ranking": "net_items_sold_desc",
            "rows": all_products_rows,
            "note": "Consolidated by product title with size and color variants combined.",
        },
        "dress_variant_families": {
            "query_year": year,
            "ranking": "grouped_variant_net_sales_desc",
            "rows": dress_variant_rows,
            "top_rows": dress_variant_top_rows,
            "bottom_rows": dress_variant_bottom_rows,
            "top_image_enrichment_summary": dress_top_image_summary,
            "bottom_image_enrichment_summary": dress_bottom_image_summary,
            "note": "Grouped by product title plus normalized variant family after stripping size-only segments.",
        },
        "product_image_focus": {
            "top_20_products": top_20_products,
            "bottom_20_products": bottom_20_products,
            "top_5_products": top_5_products,
            "bottom_5_products": bottom_5_products,
            "top_20_dress_variants": dress_variant_top_rows,
            "bottom_20_dress_variants": dress_variant_bottom_rows,
            "note": "Top and bottom products preserve ShopifyQL rank order; dress variant families are grouped by normalized size-stripped variant titles.",
        },
    }

    annual_filename = f"annual_report_{year}.json"
    annual_path = os.path.join(reports_dir, annual_filename)
    try:
        with open(annual_path, "w") as f:
            json.dump(annual_output, f, indent=2, default=str)
        print(f"  ✓ Saved: {annual_filename}")
        saved_count += 1
    except Exception as e:
        print(f"  ✗ Failed to save {annual_filename}: {e}")

    index_path = os.path.join(reports_dir, "product_image_index.json")
    try:
        with open(index_path, "w") as f:
            json.dump(
                {
                    "generated_at": timestamp,
                    "report_period": {"since": since_year, "until": until_year},
                    "top_limit": TOP_PRODUCTS_IMAGE_LIMIT,
                    "entries": product_image_index,
                },
                f,
                indent=2,
                default=str,
            )
        print(f"  ✓ Saved: {os.path.basename(index_path)}")
    except Exception as e:
        print(f"  ✗ Failed to save {os.path.basename(index_path)}: {e}")

    print("\n" + "=" * 60)
    print(f"✓ Success — {saved_count} reports generated in {reports_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
