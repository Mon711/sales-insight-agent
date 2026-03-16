# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Sales Insight Agent for Shopify data (Version 1). The agent loads Shopify order exports and generates sales insights and marketing opportunities.

### Development Goals for Version 1

1. Load Shopify order export data (CSV)
2. Clean product names and group size variants
3. Calculate units sold per product
4. Estimate product revenue using line item price × quantity
5. Calculate total store revenue
6. Generate markdown report with sales insights and marketing opportunities

## Running the Project

### Setup

```bash
pip install -r requirements.txt
```

### Loading and Inspecting Data

The main script is in `src/main.py`. To run it with your Shopify CSV:

```bash
# Option 1: Place CSV at data/raw/orders.csv (default location)
python src/main.py

# Option 2: Pass CSV path as argument
python src/main.py data/raw/your_file.csv
```

The script will print:
- Total row count
- Column names
- First 5 rows of data

## Important Rules

### No Sample Data
**Never create fake sample data unless explicitly asked.** The user provides real Shopify export files. Always work with the actual data they supply in `data/raw/`.

### File Structure

- `src/` - source code
- `data/raw/` - input CSV files (user-provided Shopify exports)
- `data/processed/` - cleaned/processed data (future)
- `tests/` - test files (future)

## Architecture Notes

The project uses a simple, modular approach:

- **ShopifyDataLoader** (`src/data_loader.py`) - Simple CSV loader that reads files without assuming column names. This flexibility allows us to inspect the actual structure before deciding which columns we need.

- **main.py** - Entry point that calls the loader and displays basic information (row count, columns, first rows).

Currently, the loader intentionally does NOT:
- Assume specific column names exist
- Perform type conversion
- Clean or validate data

We inspect the actual CSV structure first, then add processing steps incrementally.

## Development Workflow

Focus on one feature at a time:
1. Data loading ✓ (current)
2. Data inspection (current - inspecting user's real file)
3. Data cleaning (next)
4. Analysis and calculations
5. Report generation

This incremental approach helps learn pandas step-by-step and catch issues early.
