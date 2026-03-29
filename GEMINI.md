# GEMINI.md

This file provides guidance to Gemini CLI when working with code in this repository.

## Project Overview

**Sales Insight Agent for Shopify — AI-Powered Reporting Foundation**

This project fetches live Shopify analytics data via ShopifyQL, structures it by sales channel, and produces clean JSON output for AI analysis. The goal is to give accurate, channel-aware sales data so it can generate rich business insights.

This is NOT about hardcoded report templates. **It's about preparing trustworthy, structured data that can be analyzed deeply.**

### Long-term Vision

- **Phase 1 (done):** Shopify API connection + raw order fetching
- **Phase 2 (current):** ShopifyQL analytics pipeline — fetch pre-aggregated, channel-specific reports directly from Shopify's analytics engine
- **Phase 3:** Integrate AI API to generate insights automatically
- **Phase 4:** Extend to broader agent roles (marketing manager agent, product manager agent, etc.)

### Key Business Principles

- **Data accuracy first.** Use Shopify's own analytics engine (ShopifyQL) as the source of truth — it handles test orders, cancellations, and returns natively.
- **Channel awareness.** Each sales channel (website, POS, wholesale, dropship) has different business logic and must be reported separately.
- **AI-driven insights.** The pipeline's job is trustworthy data. Gemini's job is the analysis.

---

## Running the Project

### Setup
Use `/setup` to install dependencies.
```bash
pip install -r requirements.txt
```

### Running the Test Suite
Use `/test` to run the test suite.
```bash
python test_channel_reports.py
```

### Environment Variables
Ensure a `.env` file exists:
```bash
SHOPIFY_SHOP_NAME=your-shop-name
SHOPIFY_ACCESS_TOKEN=your-access-token
```
The access token requires the **`read_reports`** scope (enables ShopifyQL).

---

## Important Rules

### No Hardcoded Secrets
- Never hardcode API credentials, access tokens, or shop names.
- Always read from environment variables: `SHOPIFY_SHOP_NAME`, `SHOPIFY_ACCESS_TOKEN`.
- `.env` files are in `.gitignore`.

### No Sample Data
Never create fake Shopify order data unless explicitly asked. All data comes from the live store via the API.

### Required API Scope
The access token must have **`read_reports`** scope to use `shopifyqlQuery`. This is different from `read_analytics` — make sure it's `read_reports`.

---

## Architecture

### Layer 1: API Client — `src/shopify_client.py`
- `ShopifyGraphQLClient` — authenticates to Shopify, sends GraphQL queries
- `query()` — raw GraphQL execution
- `run_shopifyql_report()` — executes a ShopifyQL string through the `shopifyqlQuery` GraphQL field

### Layer 2: Channel Reports — `src/channel_reports.py`
- Defines one ShopifyQL query per channel (`CHANNEL_QUERIES` dict)
- `run_channel_report()` — fetches one channel, parses results, returns clean JSON
- `run_all_channel_reports()` — runs all four channels
- `run_discovery_query()` — utility to inspect what `sales_channel` values exist in the store

### Layer 3: AI Analysis
Clean JSON from Layer 2 is passed to Gemini for analysis.

---

## Channel Business Logic

Each channel is defined by specific ShopifyQL WHERE clause rules:

| Channel | Definition |
|---------|-----------|
| **online_store** | `sales_channel = 'Online Store'` (excluding Manymoons/shopmy tags) + `'Shop'` + `'Facebook & Instagram'` |
| **pos** | `sales_channel = 'Point of Sale'` |
| **wholesale** | `order_tags CONTAINS 'wholesale'` — can appear on any sales_channel |
| **dropship** | Everything else |

### Excluded Order Types (not real revenue)

| Type | Identifier | Reason |
|------|-----------|--------|
| Gifting / influencer orders | `order_tags CONTAINS 'shopmy'` or `sales_channel = 'Shopmy Integration'` | Sent to influencers for free. |
| Discount orders | `order_tags CONTAINS 'Manymoons'` | Heavy discounts, non-standard pricing. |
| Draft Orders channel | `sales_channel = 'Draft Orders'` | Internal/manual orders. |
| Loop Returns & Exchanges | `sales_channel = 'Loop Returns & Exchanges'` | Exchanges, not new sales. |
| Shopify Mobile for iPhone | `sales_channel = 'Shopify Mobile for iPhone'` | Internal orders. |

### Wholesale Revenue Note

Wholesale orders show `net_sales = $0` in Shopify because **payment is collected offline**. Estimated wholesale revenue = `gross_sales ÷ 2`.

---

## API Details

- **GraphQL endpoint:** `https://{shop}.myshopify.com/admin/api/2025-10/graphql.json`
- **ShopifyQL field:** `shopifyqlQuery(query: String!)` on `QueryRoot`
- **Required scope:** `read_reports`
- **ShopifyQL dataset:** `FROM sales`
