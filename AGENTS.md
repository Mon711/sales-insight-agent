# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**Sales Insight Agent for Shopify — AI-Powered Reporting Foundation**

This project fetches live Shopify analytics data via ShopifyQL, structures it by sales channel, and produces clean JSON output for AI analysis. The goal is to give Codex accurate, channel-aware sales data so it can generate rich business insights.

This is NOT about hardcoded report templates. **It's about preparing trustworthy, structured data that Codex can analyze deeply.**

### Long-term Vision

- **Phase 1 (done):** Shopify API connection + raw order fetching
- **Phase 2 (current):** ShopifyQL analytics pipeline — fetch pre-aggregated, channel-specific reports directly from Shopify's analytics engine
- **Phase 3:** Integrate Codex API to generate AI-powered insights automatically
- **Phase 4:** Extend to broader agent roles (marketing manager agent, product manager agent, etc.)

### Key Business Principles

- **Data accuracy first.** Use Shopify's own analytics engine (ShopifyQL) as the source of truth — it handles test orders, cancellations, and returns natively.
- **Channel awareness.** Each sales channel (website, POS, wholesale, dropship) has different business logic and must be reported separately.
- **AI-driven insights.** The pipeline's job is trustworthy data. Codex does the analysis.

---

## Running the Project

### Setup

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:

```bash
SHOPIFY_SHOP_NAME=your-shop-name
SHOPIFY_ACCESS_TOKEN=your-access-token
```

For multiple brands, you can keep brand-prefixed credentials side by side:

```bash
EDDY_SHOPIFY_SHOP_NAME=eddy-store-name
EDDY_SHOPIFY_ACCESS_TOKEN=eddy-access-token
STEELE_SHOPIFY_SHOP_NAME=steele-store-name
STEELE_SHOPIFY_ACCESS_TOKEN=steele-access-token
```

The access token requires the **`read_reports`** scope (enables ShopifyQL).
For product-image enrichment, it also needs **`read_products`**.

### Running the Test Suite

```bash
python test_channel_reports.py
```

This will:
1. Verify the Shopify API connection
2. Run a discovery query (shows all `sales_channel` values in the store)
3. Fetch reports for all four channels (online store, POS, wholesale, dropship)
4. Print clean JSON output for each channel

---

## Important Rules

### No Hardcoded Secrets
- Never hardcode API credentials, access tokens, or shop names.
- Always read from environment variables, either generic or brand-prefixed: `SHOPIFY_SHOP_NAME`, `SHOPIFY_ACCESS_TOKEN`, `EDDY_SHOPIFY_SHOP_NAME`, `STEELE_SHOPIFY_SHOP_NAME`, and so on.
- `.env` files are in `.gitignore`.

### No Sample Data
Never create fake Shopify order data unless explicitly asked. All data comes from the live store via the API.

### Required API Scope
The access token must have **`read_reports`** scope to use `shopifyqlQuery`. This is different from `read_analytics` — make sure it's `read_reports`.
If you enable product image pull, include **`read_products`** on the same token.

---

## Architecture

### Layer 1: API Client — `shopify_client.py`
- `ShopifyGraphQLClient` — authenticates to Shopify, sends GraphQL queries
- `query()` — raw GraphQL execution
- `run_shopifyql_report()` — executes a ShopifyQL string through the `shopifyqlQuery` GraphQL field

### Layer 2: Product Reports — `product_reports.py`
- Builds ShopifyQL queries for the active sub-channels from `src/config.py`
- `run_product_report()` — fetches one channel, computes `true_net_sales`, and returns cleaned rows
- `run_all_product_reports()` — runs all active product reports

### Layer 3: Main Runner — `run_reports.py`
- Orchestrates connection, discovery, report generation, and JSON output
- Writes `reports/files_generation_N/` folders for downstream analysis
- Enriches top 20 products per channel with Shopify product-image metadata/local assets when scope is available

### Layer 4: Chart Generation — `generate_graphs_only.py` and `src/visualizer.py`
- Turns the latest report folder into the local charts that support the report
- Uses `estimated_wholesale_revenue` for wholesale visualizations

### Layer 5: AI Analysis (manual for now)
Clean JSON and charts are passed to Codex for analysis. Codex generates insights, identifies anomalies, and provides recommendations.

Future: may integrate an LLM API directly into the repo.

### Codex Entry Point

The Codex app command `report/marketing_report` is the repo workflow entry point for the full marketing pipeline.
The brand-aware terminal wrapper is `./scripts/brand_analysis.sh <brand>`.
The season-aware wrapper is `./scripts/season_analysis.sh <brand> <season>`.
The older `./scripts/annual_report_2025.sh` wrapper now delegates to Eddy for compatibility.
The reusable marketing skill lives in `.agents/skills/marketing-analyst/`.
The wrapper now bundles image assets into the report output folder and exports a brand-specific PDF for portable sharing.

---

## Channel Business Logic

Each channel is defined by specific ShopifyQL WHERE clause rules (based on Eddy's store):

| Channel | Definition |
|---------|-----------|
| **online_store** | `sales_channel = 'Online Store'` (excluding Manymoons/shopmy tags) + `'Shop'` + `'Facebook & Instagram'` |
| **pos** | `sales_channel = 'Point of Sale'` |
| **wholesale** | `order_tags CONTAINS 'wholesale'` — can appear on any sales_channel |
| **dropship** | Everything else — see exclusion list below |

Note: Wholesale is identified by order tag, not by sales_channel. A wholesale order can originate from any channel.

### Excluded Order Types (not real revenue)

| Type | Identifier | Reason |
|------|-----------|--------|
| Gifting / influencer orders | `order_tags CONTAINS 'shopmy'` or `sales_channel = 'Shopmy Integration'` | Sent to influencers for free. $0 revenue, distort sales data. |
| Discount orders | `order_tags CONTAINS 'Manymoons'` | Heavy discounts, non-standard pricing. Excluded to avoid skewing performance metrics. |
| Draft Orders channel | `sales_channel = 'Draft Orders'` | Internal/manual orders, not customer-facing revenue. |
| Loop Returns & Exchanges | `sales_channel = 'Loop Returns & Exchanges'` | Exchanges, not new sales. |
| Shopify Mobile for iPhone | `sales_channel = 'Shopify Mobile for iPhone'` | Internal orders placed via the Shopify app. |

### Wholesale Revenue Note

Wholesale orders always show `net_sales = $0` in Shopify because **payment is collected offline** (manual invoicing outside Shopify). The store uses Shopify only for warehouse fulfillment tracking.

Estimated wholesale revenue = `gross_sales ÷ 2` (wholesale pricing is approximately 50% of retail). This `estimated_revenue` field is added to the wholesale summary automatically.

---

## API Details

- **GraphQL endpoint:** `https://{shop}.myshopify.com/admin/api/2025-10/graphql.json`
- **ShopifyQL field:** `shopifyqlQuery(query: String!)` on `QueryRoot`
- **Required scope:** `read_reports`
- **ShopifyQL dataset:** `FROM sales` — pre-aggregated transaction data; natively excludes test orders and correctly accounts for returns/refunds
