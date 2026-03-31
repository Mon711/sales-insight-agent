# Phase 2.5 Implementation Summary: Sub-Channel Product Analysis

## Overview

This implementation adds product-level analysis and true net sales calculation to the sales-insight-agent. The feature enables the design team to make data-driven collection planning decisions and the finance team to see accurate profitability across channels.

**Branch**: `feature/sub-channel-product-analysis`

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
- `~/Desktop/eddy_marketing_insights_N/` — Visualizations (generated via `generate_graphs_only.py`)

---

## Future Phases

### Phase 3 (AI Integration)
- Feed JSON reports to Gemini/Claude to generate cross-channel insights.
- Example: "Identify the top 5 products by profitability after commission across all dropship channels."

### Phase 4 (Multi-Agent Workflows)
- Expand to dedicated agents for Marketing, Inventory, and Financial planning.

---

**End of Implementation Summary**
