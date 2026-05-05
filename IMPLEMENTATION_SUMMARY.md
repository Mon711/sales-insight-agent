# Phase 2.5 / Brand-Aware Reporting Summary

## Overview

This implementation originally added product-level analysis and true net sales calculation to the sales-insight-agent. The newer updates on the `codex-general-brand-analysis-tool` branch keep that reporting engine intact while making the workflow brand-aware, so the same pipeline can run for Eddy, Steele, or any future brand profile that is added to the registry.

**Branch**: `codex-general-brand-analysis-tool`

---

## What Was Implemented

### 1. Centralized Configuration (`src/config.py`) ✓

**Purpose**: Single source of truth for sub-channel definitions, commission rates, and reporting dates.

**Key Features**:
- `REPORT_SINCE` / `REPORT_UNTIL` — date range for all reports (e.g., Q1 2026)
- `SUB_CHANNEL_CONFIG` — comprehensive sub-channel definitions with:
  - Commission rates (0% for direct channels, 18-40% for dropship sub-channels)
  - Filter types (`sales_channel`, `sales_channel_multi`, `order_tag`)
  - Mapping to Shopify's identifiers (names, tags)
- `EXCLUDED_CHANNELS` / `EXCLUDED_TAGS` — filters to remove non-revenue orders (Draft, Shopmy, etc.)

**Status**: Ready.

---

### 2. Product-Level Reporting (`src/product_reports.py`) ✓

**Purpose**: Fetch all products per sub-channel with detailed metrics and true net sales calculation.

**Key Functions**:
- `build_product_query()` — Builds specialized ShopifyQL queries with:
  - `WITH TOTALS` modifier for automatic aggregate calculation
  - Support for multi-channel OR logic and tag exclusions
  - Order ranking by `total_sales DESC`
- `run_product_report()` — Executes query and computes `true_net_sales` (Net - Commission) per product row
- `run_all_product_reports()` — Orchestrates reports across all active sub-channels defined in config

**Status**: Ready.

---

### 3. Integrated Channel Summaries (`run_reports.py`) ✓

**Changes**:
- The main runner now fetches detailed product data for all channels.
- **Dynamic Summary**: Instead of a separate query, it extracts top-level totals (Gross, Net, Total Sales, Items Sold) from the `__totals` columns provided by the `WITH TOTALS` ShopifyQL modifier.
- **Wholesale Logic**: Automatically calculates `estimated_wholesale_revenue` as 50% of retail gross sales.
- **JSON Serialization**: Saves segmented, AI-ready JSON files for each channel in `reports/files_generation_N/`.

**Status**: Ready.

---

### 4. Discovery Utility (`src/shopify_client.py`) ✓

**Purpose**: Integrated method to identify exact sales_channel names present in the store.

**Implementation**:
- `discover_channels(since, until)` method in `ShopifyGraphQLClient`.
- Used in `run_reports.py` STEP 2 to log active channels before fetching detailed reports.
- Helps developers confirm exact Shopify channel names for `src/config.py` updates.

**Status**: Ready.

---

## Brand-Aware Additions

These changes turn the single-brand workflow into a reusable brand analysis tool.

### 1. Brand Registry (`src/brand_profiles.py`) ✓

**Purpose**: Define the supported brands and map each brand name to its credentials and output naming.

**Key Features**:
- `BrandProfile` entries for `eddy` and `steele`.
- Alias handling so commands can accept common variations of the brand name.
- Normalized brand slugs for folder names, filenames, and config lookup.

### 2. Brand-Scoped Shopify Credentials (`src/shopify_client.py`) ✓

**Purpose**: Load the correct Shopify shop name and access token for the selected brand.

**Key Features**:
- Prefers brand-specific environment variables such as `EDDY_SHOPIFY_SHOP_NAME` and `STEELE_SHOPIFY_SHOP_NAME`.
- Falls back to the generic `SHOPIFY_SHOP_NAME` and `SHOPIFY_ACCESS_TOKEN` variables.
- Keeps the existing ShopifyQL and Product API behavior unchanged.

### 3. Brand-Aware Report Runner (`run_reports.py`) ✓

**Purpose**: Record the selected brand in the JSON output and keep report generation brand-specific.

**Key Features**:
- Reads `REPORT_BRAND_SLUG` and optional `REPORT_BRAND_DISPLAY_NAME`.
- Stores brand metadata in the output JSON.
- Names the report output using the brand slug so different brands do not collide.

### 4. Season Comparison Shell Entry Point (`scripts/season_analysis.sh`) ✓

**Purpose**: Let the user run a single-season report or a same-season cross-year comparison from one command.

**Key Features**:
- `./scripts/season_analysis.sh steele winter25`
- `./scripts/season_analysis.sh steele winter25 winter26`
- Optional `MODEL` and `REASONING_EFFORT` overrides before the command

---

## Data Model Reference

### Commission Rates (from financial plan)
| Sub-channel | Rate | Notes |
|---|---|---|
| online_store | 0% | Direct sales (Online, Shop, Social) |
| pos | 0% | In-store |
| wholesale | 0% | Offline payment, estimated_revenue = gross / 2 |
| dropship_nordstrom | 20% | Mirakl |
| dropship_bloomingdales | 25% | Mirakl |
| dropship_macys | 18% | Macy's |
| dropship_shop_couper | 40% | Shop Couper |
| dropship_over_the_moon | 40% | fabric |

### True Net Sales Formula
```
true_net_sales = net_sales * (1 - commission_rate)
```

Example:
- Dropship order: net_sales = $100
- Commission rate: 40%
- true_net_sales = $100 * (1 - 0.40) = $60

---

## Architecture Notes

### ShopifyQL `WITH TOTALS`
The agent uses the `WITH TOTALS` modifier in ShopifyQL. This appends additional columns (e.g., `net_sales__totals`) to every row in the result set, representing the sum of that metric across all matching records. This allows the agent to get both row-level product details and aggregate channel totals in a single API call.

### Graceful Fallbacks
- If a channel has no sales in the period, it is skipped.
- Parse errors in ShopifyQL are caught and logged without crashing the full reporting run.
- `product_title` is required; rows with null titles are filtered out in the query.

---

## Files Structure

### Core Logic
- `src/config.py` — Centralized configuration
- `src/shopify_client.py` — API communication and discovery
- `src/product_reports.py` — ShopifyQL query building and parsing
- `src/visualizer.py` — Chart generation engine
- `run_reports.py` — Main orchestration script

### Output
- `reports/files_generation_N/` — Numbered folders containing JSON reports
- `~/Desktop/<brand>_<season>_insights_N/` — Season-specific analysis folders generated by the season wrapper

---

## Future Phases

## Phase 2.6 Addendum: Product Image Enrichment + Portable Report Export

This section reflects the newer implementation merged after Phase 2.5.

### What Was Added

### 1. Product Image Enrichment (`src/image_enrichment.py`) ✓

**Purpose**: Attach product visuals to report rows so AI analysis can reason about product style themes, not only sales numbers.

**Key Features**:
- Enriches top **20** products per channel (by channel-relevant sales score).
- Matching strategy:
  - First tries Shopify product ID (`product_id`) when available.
  - Falls back to exact-title search when ID matching is not available.
- Stores both metadata and local image path:
  - `remote_url` (Shopify CDN URL)
  - `local_path` (saved asset path)
  - match confidence + status (`enriched`, `metadata_only`, `ambiguous`, `not_found`, etc.)

### 2. Shopify Product API Helpers (`src/shopify_client.py`) ✓

**Purpose**: Retrieve product media from the Admin GraphQL Product API.

**Key Features**:
- Scope check for Product API access (`read_products`).
- ShopifyQL probe to detect whether `product_id` is available in the current store query context.
- Product media fetch methods using Admin GraphQL `Product` media fields.

### 3. Main Pipeline Integration (`run_reports.py`) ✓

**Purpose**: Keep image enrichment in the main report generation workflow without breaking existing reporting.

**Key Features**:
- Adds `product_image` object to product rows in each `report_*.json`.
- Adds channel-level `image_enrichment_summary`.
- Writes generation-level `product_image_index.json`.
- Graceful fallback behavior:
  - If Product API scope/access fails, the report still generates; image enrichment is marked skipped with reason.

### 4. Portable Desktop Output + PDF (`scripts/marketing_report.sh`, `scripts/package_marketing_report.py`) ✓

**Purpose**: Make the final report sharable without manual path fixing.

**Key Features**:
- Bundles report assets into Desktop output folder under `report_assets/`.
- Rewrites markdown image links to local portable paths.
- Converts plain product image path mentions into markdown image embeds during packaging.
- Exports `MARKETING_REPORT.pdf` from packaged markdown.
- Improved PDF rendering behavior:
  - better markdown handling for tables and image embeds
  - section-based page breaks

### 5. Prompt/Skill Updates for Image Embeds ✓

Updated the report generation command + skill instructions so product images are embedded as real markdown images (`![...](...)`) instead of plain text paths.

---

## Updated Output Contract

### Report JSON (`reports/files_generation_N/report_*.json`)
- Existing fields remain.
- Added:
  - `image_enrichment_summary` (channel level)
  - `product_sales_performance[].product_image` (row level)

### Generation Assets
- `reports/files_generation_N/assets/product_images/...`
- `reports/files_generation_N/product_image_index.json`

### Desktop Deliverables
- `~/Desktop/<brand>_annual_insights_N/ANNUAL_REPORT_2025_<brand>.md`
- `~/Desktop/<brand>_annual_insights_N/ANNUAL_REPORT_2025_<brand>.pdf`
- `~/Desktop/<brand>_annual_insights_N/report_assets/...`
- chart PNGs + log files

---

## Scope Requirements (Updated)

- `read_reports` is required for ShopifyQL reporting.
- `read_products` is required for product image enrichment.

If `read_products` is missing, report generation still succeeds but image enrichment is skipped gracefully.

---

## Validation Added

- New unit tests in `test_image_enrichment.py` for:
  - ID-based match and successful download
  - title-match ambiguity handling
  - top-limit behavior (20 per channel)

## Phase 2.7 Addendum: Seasonal Official Product Detail + Visual-First Reports

### Evidence Layers

Season reports now combine three separate evidence layers:

- **ShopifyQL commercial metrics**: sales, units, returns, return rate, discounts, product title, SKU, type, and product ID remain the commercial source of truth.
- **Admin GraphQL product detail**: product descriptions, tags, selected options, variants, collections, media, and product-level metafields provide official product-detail evidence.
- **Local product images**: images remain a first-class visual/design evidence layer for silhouette, proportion, styling, print scale, colour impression, drape, opacity, texture, and use case.

Image analysis should enhance the qualitative read, but exact fabric composition and fibre percentages must only come from official product data. If exact composition is not present in official fields, reports should state `Official composition: Unknown` and label any image-based fabric read as `Visual inference`.

### Product Detail Enrichment

`src/shopify_client.py` now includes `fetch_product_detail_records_by_ids()`, which batches `nodes(ids:)` Admin GraphQL lookups and normalizes product detail into clean JSON. It resolves `shopify.*` metaobject metafields through reference display names, parses Shopify rich-text JSON for `custom.materials`, `custom.product_size`, and `custom.product_features`, and derives `official_product_attributes`.

`src/season_reports.py` attaches the official detail record to each ShopifyQL row as `product_detail` and records `product_detail_enrichment_summary`. If product detail enrichment fails, the report still generates from ShopifyQL rows and image enrichment, with the error recorded in the summary.

### Report Prompt + Skill Contract

`scripts/season_analysis.sh` and `.agents/skills/season-product-analyst/SKILL.md` now instruct Codex to produce visual-first Markdown reports using compact product cards, grids, boards, and evidence tables. Reports must stay generic across every season in `src/season_profiles.py` and every brand in `src/brand_profiles.py`; no Winter-specific or brand-specific product assumptions should be hardcoded.

### Validation Added

- Rich-text metafield parsing.
- Metaobject reference label resolution.
- Exact fabric composition is not invented when only generic material language exists.
- Rows without product IDs do not crash product-detail enrichment.
- Product-detail enrichment failures do not break ShopifyQL reporting.
  - metadata-only fallback when download fails

---

### Phase 3 (AI Integration)
- Feed JSON reports to Gemini/Claude to generate cross-channel insights.
- Example: "Identify the top 5 products by profitability after commission across all dropship channels."

### Phase 4 (Multi-Agent Workflows)
- Expand to dedicated agents for Marketing, Inventory, and Financial planning.

---

**End of Implementation Summary**
