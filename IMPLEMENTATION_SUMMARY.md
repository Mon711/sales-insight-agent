# Phase 2.5 Implementation Summary: Sub-Channel Product Analysis

## Overview

This implementation adds product-level analysis and true net sales calculation to the sales-insight-agent. The feature enables the design team to make data-driven collection planning decisions and the finance team to see accurate profitability across channels.

**Branch**: `feature/sub-channel-product-analysis`

---

## What Was Implemented

### 1. Centralized Configuration (`src/config.py`) ✓

**Purpose**: Single source of truth for sub-channel definitions, commission rates, and reporting dates.

**Key Features**:
- `REPORT_SINCE` / `REPORT_UNTIL` — date range for all reports
- `SUB_CHANNEL_CONFIG` — comprehensive sub-channel definitions with:
  - Commission rates (0% for online_store/pos/wholesale, 22%/40%/30% for dropship sub-channels)
  - Filter types (sales_channel, sales_channel_multi, order_tag)
  - Shopify channel name mappings
  - Candidate channel names for discovery matching
- `EXCLUDED_CHANNELS` / `EXCLUDED_TAGS` — order types to filter out
- Helper functions: `get_active_sub_channels()`, `get_unconfirmed_sub_channels()`

**Status**: Ready. Dropship sub-channel `shopify_channel` values are `None` until discovery confirms exact channel names.

---

### 2. Product-Level Reporting (`src/product_reports.py`) ✓

**Purpose**: Fetch top 20 products per sub-channel with true net sales calculation.

**Key Functions**:
- `build_product_query()` — Builds ShopifyQL queries with support for:
  - Single sales_channel queries (dropship sub-channels)
  - Multi-channel OR logic with tag exclusions (online_store)
  - Tag-based filtering (wholesale)
  - Automatic `group by product_title` and `order by net_sales` (or `gross_sales` for wholesale)
- `run_product_report()` — Executes a query and computes `true_net_sales` per product
- `run_all_product_reports()` — Orchestrates all active sub-channels
  - Gracefully handles parse errors (logs + skips, doesn't crash)
  - Returns dict keyed by channel_key with product lists

**Output Format**:
```json
{
  "product_title": "Product A",
  "gross_sales": 900.00,
  "net_sales": 850.00,
  "orders": 7,
  "true_net_sales": 663.00  // net_sales * (1 - commission_rate)
}
```

**Status**: Ready. Will only query active sub-channels (online_store, pos, wholesale) until dropship channels are confirmed.

---

### 3. Enhanced Channel Reports (`src/channel_reports.py`) ✓

**Changes**:
- Now imports configuration from `src/config.py` (single source of truth for dates)
- Added three fields to each channel's summary:
  - `commission_rate` — from config
  - `true_net_sales` — `net_sales * (1 - commission_rate)`
  - `commission_deducted` — `net_sales - true_net_sales`
- Added TODO comments showing where to add dropship sub-channel queries once confirmed

**Example Summary**:
```json
{
  "total_gross_sales": 5000.00,
  "total_net_sales": 4500.00,
  "total_discounts": -500.00,
  "total_orders": 50,
  "commission_rate": 0.22,
  "true_net_sales": 3510.00,
  "commission_deducted": 990.00
}
```

**Status**: Ready. Dropship queries will be added after channel confirmation.

---

### 4. Unified Reporting (`run_reports.py`) ✓

**Changes**:
- Imports from centralized config
- Calls `run_all_product_reports()` after channel reports
- Merges top_products into each channel report
- Adds `generated_at` ISO timestamp and `report_period` metadata
- Updated output filename to `sales_report_{SINCE}_to_{UNTIL}.json`

**Output Structure**:
```json
{
  "generated_at": "2026-03-23T12:34:56.789+00:00",
  "report_period": { "since": "2026-02-01", "until": "2026-02-28" },
  "channels": {
    "online_store": {
      "channel": "online_store",
      "date_range": { ... },
      "rows": [ ... ],
      "summary": { ... },
      "top_products": [ ... ]
    },
    ...
  }
}
```

**Status**: Ready.

---

### 5. Discovery Helper (`discover_channels.py`) ✓

**Purpose**: Interactive script to identify exact sales_channel names for dropship connectors.

**Usage**:
```bash
python discover_channels.py
```

**Output**:
- Lists all sales_channel values in the store
- Shows revenue and order count per channel
- Displays which names are still unconfirmed
- Provides step-by-step instructions for updating config.py

**Status**: Ready.

---

## Next Steps (for the user)

### Step 1: Run Discovery Query
```bash
python discover_channels.py
```

This will show all sales_channel values in your store. Look for the exact names matching:
- Mirakl (candidates: "Mirakl Connect", "Mirakl", "Mirakl Connector")
- fabric (candidates: "fabric Dropship Platform", "fabric Marketplace", "fabric")
- Maisonette (candidates: "Maisonette", "Maisonette Marketplace")

### Step 2: Update `src/config.py`

For each discovered channel name, update the corresponding entry:

```python
SUB_CHANNEL_CONFIG = {
    ...
    "dropship_mirakl": {
        ...
        "shopify_channel": "Mirakl Connect",  # ← CHANGE FROM None
        ...
    },
    ...
}
```

### Step 3: Uncomment and Update `src/channel_reports.py`

Once config.py is updated, uncomment the dropship sub-channel query templates (around line 73) and replace placeholders:

```python
"dropship_mirakl": f"""
    FROM sales
    SHOW gross_sales, discounts, net_sales, orders
    WHERE sales_channel = 'Mirakl Connect'  # ← USE CONFIRMED NAME
    TIMESERIES day
    SINCE {REPORT_SINCE} UNTIL {REPORT_UNTIL}
""",
```

### Step 4: Run Full Report

```bash
python run_reports.py
```

The output will include:
- ✓ All 4 base channels (online_store, pos, wholesale, dropship catch-all)
- ✓ 3 dropship sub-channels (once confirmed)
- ✓ Top 20 products per sub-channel with true_net_sales
- ✓ All commission calculations included

### Step 5: Validate

Check the generated `sales_report_2026-02-01_to_2026-02-28.json`:
1. Verify `true_net_sales = net_sales * (1 - commission_rate)` for each channel
2. Check dropship_* sub-channels are present
3. Verify top_products are ranked correctly
4. Spot-check totals against financial plan spreadsheet

---

## Data Model Reference

### Commission Rates (from financial plan)
| Sub-channel | Rate | Notes |
|---|---|---|
| online_store | 0% | Direct sales |
| pos | 0% | In-store |
| wholesale | 0% | Offline payment, estimated_revenue = gross/2 |
| dropship_mirakl | 22% | Blended Nordstrom commission |
| dropship_fabric | 40% | Regional retailers |
| dropship_maisonette | 30% | Maisonette marketplace |

### True Net Sales Formula
```
true_net_sales = net_sales * (1 - commission_rate)
```

Example:
- Dropship fabric order: net_sales = $100
- Commission rate: 40%
- true_net_sales = $100 * (1 - 0.40) = $60

---

## Architecture Notes

### Active vs Unconfirmed Channels
- **Active** (ready to query): online_store, pos, wholesale
- **Unconfirmed** (awaiting discovery): dropship_mirakl, dropship_fabric, dropship_maisonette

The product_reports module automatically filters to active channels using `get_active_sub_channels()`. Once dropship channels are confirmed and added to CHANNEL_QUERIES, they'll be queried automatically.

### Error Handling
- `build_product_query()` raises `ValueError` if shopify_channel is None for sales_channel filter type
- `run_product_report()` catches exceptions, logs, and returns empty list (graceful degradation)
- `run_all_product_reports()` skips failed channels but continues with others

### Graceful Fallbacks
If `product_title` is not available in `FROM sales`:
1. `run_product_report()` catches the parse error
2. Logs "ShopifyQL parse error"
3. Returns empty product list
4. Channel report continues normally (just without top_products)

Future: Could fallback to Orders API for product details if ShopifyQL doesn't support product_title.

---

## Testing Checklist

- [x] All Python files compile (syntax check)
- [x] Config module loads correctly
- [x] Active sub-channels identified correctly (online_store, pos, wholesale)
- [x] Unconfirmed sub-channels identified correctly (dropship_*)
- [x] Product query builder supports all filter types
- [ ] Live API test with valid credentials (when ready)
- [ ] End-to-end report generation (when dropship channels confirmed)
- [ ] True net sales calculations verified
- [ ] Top products ranking validated

---

## Files Modified / Created

### Created
- `src/config.py` — Centralized configuration
- `src/product_reports.py` — Product-level reporting
- `discover_channels.py` — Discovery helper script
- `IMPLEMENTATION_SUMMARY.md` — This file

### Modified
- `src/channel_reports.py` — Import config, add true_net_sales to summary
- `run_reports.py` — Integrate product reports, add metadata

### Unchanged
- `src/shopify_client.py` — No changes needed
- `requirements.txt` — No new dependencies
- `.env` — User provides credentials

---

## Future Phases

### Phase 2.5.1 (Optional)
- Add retailer-level commission breakdown for Mirakl (Nordstrom 20%, Bloomingdale's 25%, Macy 18%)
  - Requires Orders API + order tag parsing
  - Would replace blended 22% with actual per-retailer rates

### Phase 3 (Claude API Integration)
- Call Claude API with product reports + channel summaries
- Generate AI-powered insights:
  - "Top 3 products by profitability across all channels"
  - "Which collections are underperforming on dropship vs online?"
  - "Recommendations for consolidation or expansion"

### Phase 4 (Broader Agent Roles)
- Marketing manager agent — channel marketing effectiveness
- Product manager agent — collection assortment optimization
- Operations agent — fulfillment cost analysis

---

## Questions / Support

If `product_title` is not available in ShopifyQL:
1. Check Shopify API version (currently 2025-10)
2. Verify `read_reports` scope is active
3. May need to switch to Orders API for product details

If dropship channel names don't match candidates:
1. Run `python discover_channels.py` to see exact names
2. Add any new candidates to config.py comments
3. Update based on what discovery shows

---

**End of Implementation Summary**
