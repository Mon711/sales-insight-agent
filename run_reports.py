#!/usr/bin/env python3
"""
The main entry point for the Sales Insight Agent.

This script orchestrates the entire reporting process:
1. Connects to Shopify.
2. Identifies active sales channels.
3. Fetches detailed product-wise data.
4. Saves organized JSON files into numbered generation folders.
"""

import os
import json
import sys
import re
from datetime import datetime, timezone

# We import our specialized tools from the 'src' folder
from src.shopify_client import ShopifyGraphQLClient
from src.product_reports import run_all_product_reports
from src.config import REPORT_SINCE, REPORT_UNTIL
from src.image_enrichment import (
    TOP_PRODUCTS_IMAGE_LIMIT,
    enrich_channel_product_rows,
    mark_channel_image_enrichment_skipped,
)


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
    print(f"Shopify Sales Insight Agent — {REPORT_SINCE} to {REPORT_UNTIL}")
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

    # --- STEP 2: Discovery (Check what channels are active) ---
    print("\n[STEP 2] Identifying active sales channels...")
    try:
        # We ask Shopify for a high-level list of where sales are coming from
        channels = client.discover_channels(REPORT_SINCE, REPORT_UNTIL)
        for row in channels:
            name = row.get("sales_channel", "Unknown")
            net = float(row.get("net_sales", 0) or 0)
            print(f"  - {name}: ${net:,.2f} net sales")
    except Exception as e:
        print(f"✗ Discovery failed: {e}")
        sys.exit(1)

    # --- STEP 2.5: Probe ShopifyQL support for product_id ---
    print("\n[STEP 2.5] Checking ShopifyQL support for product_id...")
    include_product_id = False
    try:
        include_product_id = client.probe_shopifyql_product_id_support(REPORT_SINCE, REPORT_UNTIL)
        if include_product_id:
            print("✓ product_id is available in ShopifyQL output (ID-first image matching enabled)")
        else:
            print("⚠ product_id not available in ShopifyQL output (title fallback will be used)")
    except Exception as e:
        print(f"⚠ Could not probe product_id support: {e}")
        print("  Falling back to title-based image matching only.")
        include_product_id = False

    # --- STEP 3: Run Product-Wise Reports ---
    print("\n[STEP 3] Fetching detailed product data...")
    try:
        # This reaches out to Shopify for every product in every channel
        all_products = run_all_product_reports(client, include_product_id=include_product_id)
    except Exception as e:
        print(f"✗ Product report failed: {e}")
        sys.exit(1)

    # --- STEP 4: Save the Files ---
    print("\n[STEP 4] Saving individual JSON files...")
    
    timestamp = datetime.now(timezone.utc).isoformat()
    saved_count = 0
    product_image_index = []

    for channel_key, product_rows in all_products.items():
        if not product_rows:
            continue

        # ShopifyQL with 'WITH TOTALS' appends top-level totals as '__totals' columns to every row.
        # We take these from the first row and convert them to numbers for clean analysis.
        summary_row = product_rows[0]
        summary = {
            "total_gross_sales": float(summary_row.get("gross_sales__totals") or 0),
            "total_net_sales": float(summary_row.get("net_sales__totals") or 0),
            "total_sales": float(summary_row.get("total_sales__totals") or 0),
            "total_items_sold": float(summary_row.get("net_items_sold__totals") or 0),
            "total_orders": float(summary_row.get("orders__totals") or 0),
        }
        
        # Special math for Wholesale (estimating revenue at 50% of retail)
        if channel_key == "wholesale" and summary["total_gross_sales"]:
            summary["estimated_wholesale_revenue"] = round(summary["total_gross_sales"] / 2, 2)

        # Clean up each row to remove these extra totals columns before final JSON output
        for row in product_rows:
            for key in list(row.keys()):
                if key.endswith("__totals"):
                    del row[key]

        if products_access_ok:
            image_summary, image_index_rows = enrich_channel_product_rows(
                client=client,
                channel_key=channel_key,
                product_rows=product_rows,
                generation_dir=gen_dir,
                top_limit=TOP_PRODUCTS_IMAGE_LIMIT,
            )
        else:
            image_summary, image_index_rows = mark_channel_image_enrichment_skipped(
                product_rows=product_rows,
                reason=f"Product API unavailable: {products_access_error}",
                top_limit=TOP_PRODUCTS_IMAGE_LIMIT,
            )

        product_image_index.extend(image_index_rows)

        # Structure the final data for this specific channel
        channel_output = {
            "generated_at": timestamp,
            "report_period": {"since": REPORT_SINCE, "until": REPORT_UNTIL},
            "channel_name": channel_key,
            "channel_summary": summary,
            "image_enrichment_summary": image_summary,
            "product_sales_performance": product_rows
        }

        # Build the filename and save it
        safe_name = channel_key.lower().replace(" ", "_")
        filename = f"report_{safe_name}_{REPORT_SINCE}_to_{REPORT_UNTIL}.json"
        output_path = os.path.join(gen_dir, filename)
        
        try:
            with open(output_path, "w") as f:
                json.dump(channel_output, f, indent=2, default=str)
            print(f"  ✓ Saved: {filename}")
            saved_count += 1
        except Exception as e:
            print(f"  ✗ Failed to save {filename}: {e}")

    index_path = os.path.join(gen_dir, "product_image_index.json")
    try:
        with open(index_path, "w") as f:
            json.dump(
                {
                    "generated_at": timestamp,
                    "report_period": {"since": REPORT_SINCE, "until": REPORT_UNTIL},
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
