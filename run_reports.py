#!/usr/bin/env python3
"""
The main entry point for the Sales Insight Agent.

This script orchestrates the annual reporting process:
1. Connects to Shopify.
2. Fetches annual product/category data.
3. Enriches product rows with images.
4. Saves manager JSON output into numbered generation folders.
"""

import os
import json
import sys
import re
from datetime import datetime, timezone

# We import our specialized tools from the 'src' folder
from src.shopify_client import ShopifyGraphQLClient
from src.product_reports import run_annual_report, select_dress_rows
from src.image_enrichment import (
    TOP_PRODUCTS_IMAGE_LIMIT,
    enrich_channel_product_rows,
    mark_channel_image_enrichment_skipped,
)

ANNUAL_REPORT_YEAR = 2025
ANNUAL_REPORT_SINCE = f"{ANNUAL_REPORT_YEAR}-01-01"
ANNUAL_REPORT_UNTIL = f"{ANNUAL_REPORT_YEAR}-12-31"


def get_next_generation_dir(base_dir="reports"):
    """
    Manages the 'reports/' folder.
    It looks at existing folders like 'files_generation_1' and finds the
    next available number, filling in any gaps if a folder was deleted.
    """
    if not os.path.exists(base_dir):
        os.makedirs(base_dir)
        return os.path.join(base_dir, "files_generation_1")

    # This regular expression helps us find the numbers in folder names
    pattern = re.compile(r"^files_generation_(\d+)$")
    
    existing_nums = []
    for d in os.listdir(base_dir):
        full_path = os.path.join(base_dir, d)
        if os.path.isdir(full_path):
            match = pattern.match(d)
            if match:
                existing_nums.append(int(match.group(1)))

    # Find the highest number and add 1
    if existing_nums:
        next_num = max(existing_nums) + 1
    else:
        next_num = 1
    
    return os.path.join(base_dir, f"files_generation_{next_num}")


def main():
    print("=" * 60)
    print(f"Shopify Sales Insight Agent — Annual Report ({ANNUAL_REPORT_YEAR})")
    print("=" * 60)

    # --- STEP 0: Create the Output Folder ---
    gen_dir = get_next_generation_dir()
    os.makedirs(gen_dir, exist_ok=True)
    print(f"\n[STEP 0] Saving reports to: {gen_dir}")

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

    # --- STEP 2.5: Probe ShopifyQL support for product_id ---
    print("\n[STEP 2.5] Checking ShopifyQL support for product_id...")
    include_product_id = False
    try:
        include_product_id = client.probe_shopifyql_product_id_support(
            ANNUAL_REPORT_SINCE,
            ANNUAL_REPORT_UNTIL,
        )
        if include_product_id:
            print("✓ product_id is available in ShopifyQL output (ID-first image matching enabled)")
        else:
            print("⚠ product_id not available in ShopifyQL output (title fallback will be used)")
    except Exception as e:
        print(f"⚠ Could not probe product_id support: {e}")
        print("  Falling back to title-based image matching only.")
        include_product_id = False

    annual_report_data = None
    print(f"\n[STEP 3] Fetching annual report data ({ANNUAL_REPORT_YEAR})...")
    try:
        annual_report_data = run_annual_report(
            client=client,
            year=ANNUAL_REPORT_YEAR,
            include_product_id=include_product_id,
        )
        print(
            "  ✓ Annual report rows: "
            f"top={len(annual_report_data.get('top_performers', []))}, "
            f"under={len(annual_report_data.get('underperformers', []))}, "
            f"categories={len(annual_report_data.get('top_categories', []))}"
        )
    except Exception as e:
        print(f"  ⚠ Annual report fetch failed: {e}")
        sys.exit(1)

    # --- STEP 4: Save the Files ---
    print("\n[STEP 4] Saving annual JSON files...")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    saved_count = 0
    product_image_index = []
    year = int(annual_report_data.get("year", ANNUAL_REPORT_YEAR))
    since_year = f"{year}-01-01"
    until_year = f"{year}-12-31"

    top_rows = annual_report_data.get("top_performers", [])
    under_rows = annual_report_data.get("underperformers", [])
    category_rows = annual_report_data.get("top_categories", [])

    annual_top_limit = min(20, TOP_PRODUCTS_IMAGE_LIMIT)
    if products_access_ok:
        top_image_summary, top_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_top_{year}",
            product_rows=top_rows,
            generation_dir=gen_dir,
            top_limit=annual_top_limit,
        )
        under_image_summary, under_image_index_rows = enrich_channel_product_rows(
            client=client,
            channel_key=f"annual_under_{year}",
            product_rows=under_rows,
            generation_dir=gen_dir,
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

    top_5_dresses = select_dress_rows(top_rows, limit=5)
    bottom_5_dresses = select_dress_rows(under_rows, limit=5)

    annual_output = {
        "generated_at": timestamp,
        "report_period": {"since": since_year, "until": until_year},
        "report_name": f"annual_performance_{year}",
        "query_capabilities": annual_report_data.get("query_capabilities", {}),
        "top_performers": {
            "query_year": year,
            "ranking": "net_sales_desc",
            "image_enrichment_summary": top_image_summary,
            "rows": top_rows,
        },
        "underperformers": {
            "query_year": year,
            "ranking": "net_sales_asc",
            "image_enrichment_summary": under_image_summary,
            "rows": under_rows,
        },
        "top_categories": {
            "query_year": year,
            "ranking": "net_sales_desc",
            "rows": category_rows,
        },
        "dress_image_focus": {
            "top_5_dresses": top_5_dresses,
            "bottom_5_dresses": bottom_5_dresses,
            "note": "Dresses selected from product lists for report image embedding.",
        },
    }

    annual_filename = f"annual_report_{year}.json"
    annual_path = os.path.join(gen_dir, annual_filename)
    try:
        with open(annual_path, "w") as f:
            json.dump(annual_output, f, indent=2, default=str)
        print(f"  ✓ Saved: {annual_filename}")
        saved_count += 1
    except Exception as e:
        print(f"  ✗ Failed to save {annual_filename}: {e}")

    index_path = os.path.join(gen_dir, "product_image_index.json")
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
    print(f"✓ Success — {saved_count} reports generated in {gen_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
