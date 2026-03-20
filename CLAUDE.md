# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Sales Insight Agent for Shopify — AI-Powered Reporting Foundation**

This project builds a reliable, trustworthy Shopify data pipeline that fetches live store data, filters it correctly, and structures it for AI analysis. The goal is to enable Claude (and future agents) to generate rich, context-aware business insights and reports.

This is NOT about generating fixed-template reports. **It's about preparing clean, structured data that an AI can analyze deeply.**

### Long-term Vision

- **Phase 1 (current):** Build a reliable Shopify data pipeline with proper business filtering
- **Phase 2:** Integrate Claude API to generate AI-powered insights
- **Phase 3:** Extend to a broader agent/data foundation for multiple e-commerce roles (marketing manager agent, product manager agent, etc.)

### Key Business Principles

- **Data accuracy first.** Not all order-like records are real revenue. We must correctly filter test orders, cancelled orders, draft orders, internal transfers, etc.
- **Channel awareness.** Different sales channels (website, POS, wholesale, dropship) have different characteristics and need separate analysis.
- **AI-driven insights.** The pipeline's value is in providing trustworthy data, not hardcoded rules. Claude will do the analysis.

## Running the Project

### Setup

```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file (or export these in your shell):

```bash
SHOPIFY_SHOP_NAME=your-shop-name
SHOPIFY_ACCESS_TOKEN=your-access-token
```

### Running the Pipeline

```bash
python src/main.py
```

This will:
1. Fetch live orders from Shopify API
2. Apply business filters (exclude test orders, etc.)
3. Calculate metrics (revenue, units sold, by-channel breakdown)
4. Output structured data for analysis

## Important Rules

### No Hardcoded Secrets
- **Never hardcode API credentials, access tokens, or shop names.**
- Always read from environment variables: `SHOPIFY_SHOP_NAME`, `SHOPIFY_ACCESS_TOKEN`
- `.env` files are in `.gitignore` — safe to use locally

### Correct Filtering is Critical
- Test orders, draft orders, cancelled orders, and refunds must be handled correctly
- Document why we exclude each type of record
- When in doubt, include the record and let the AI decide its relevance

### No Sample Data
**Never create fake Shopify order data unless explicitly asked.** We fetch from the real live store.

## Architecture Notes

The pipeline is divided into **clear layers** that separate concerns:

### Layer 1: Data Fetching
- **`shopify_client.py`** - GraphQL client that authenticates to Shopify and fetches live orders
- Returns raw order data from the API (no filtering yet)
- Handles pagination and errors

### Layer 2: Business Filtering
- **`shopify_filters.py`** - Pure functions that apply business rules
- Examples: `exclude_test_orders()`, `exclude_cancelled()`, `filter_by_channel()`, etc.
- Each filter is independent and composable
- Input: raw orders; Output: clean, trustworthy orders

### Layer 3: Metrics & Structuring
- **`metrics_analyzer.py`** - Calculates structured metrics from cleaned orders
- Output: a clean dictionary/JSON with:
  - Total revenue, order count, currency
  - Breakdown by channel (website, POS, wholesale, etc.)
  - Top products (by units, revenue)
  - Data quality notes (what was excluded and why)
- **This is the product.** This clean data goes to AI for analysis.

### Layer 4: AI Analysis (Manual - Not In-Repo Yet)
- **Not yet automated in this repo.** Currently, you export the structured metrics and use Claude manually in your workflow.
- You take the JSON metrics and ask Claude to analyze them, generate insights, identify anomalies, and provide recommendations.
- This ensures you control the analysis, can iterate, and understand the reasoning.
- Future: May integrate Claude API directly into the repo, but not the current priority.

### Deprecated Components
The following are **no longer used** and should be removed once Step 3 is complete:
- `src/data_loader.py` — Was for CSV files; replaced by `shopify_client.py`
- `src/data_cleaner.py` — Was for CSV processing; replaced by `shopify_filters.py`
- `src/report_generator.py` — Was hardcoded template; replaced by AI analysis

## Development Workflow

Build the pipeline in this order:

1. **Step 1: Data Fetching** ✓ (done)
   - `shopify_client.py` — Fetch orders from Shopify API
   - GraphQL query validated against Shopify schema
   - Handles pagination automatically

2. **Step 2: Business Filtering** ✓ (done)
   - `shopify_filters.py` — Apply business rules to identify "real revenue"
   - Currently active filters (Tier 1 - safe, always-on):
     - Exclude test orders (`test == True`)
     - Exclude cancelled orders (`cancelledAt != null`)
   - Future filters (Tier 2 - documented, waiting for business decisions):
     - Payment status (partially paid vs fully paid?)
     - Fulfillment status (unshipped vs shipped?)
     - Channel filtering (which channels are real revenue?)
     - Draft/internal orders (how to identify?)
     - Refund handling (how to account for refunds?)

3. **Step 3: Metrics & Structuring** (next)
   - `metrics_analyzer.py` — Calculate clean metrics from filtered orders
   - Output: JSON with revenue, units sold, by-channel breakdown, data quality notes
   - This is the product we pass to Claude for analysis

4. **Step 4: AI Analysis** (future - manual for now)
   - Export the structured metrics
   - Use Claude to analyze and generate insights
   - May automate in-repo later if it makes sense

Each step validates that the previous layer works correctly before moving forward.
