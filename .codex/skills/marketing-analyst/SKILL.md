---
name: marketing-analyst
description: Expert AI marketing analyst for Shopify data. Use when you need to identify which product types and collections are performing best across specific sales channels to inform design and collection planning.
---

# Shopify Marketing and Design Insights Workflow

This skill transforms raw Shopify analytics into actionable insights that connect sales performance to design and collection planning.

## Core Capabilities

- Automated discovery of the latest `reports/files_generation_X/` folder.
- Visualization generation via `python generate_graphs_only.py` or `src/visualizer.py`.
- Channel-aware analysis for Online Store, POS, Wholesale, and Dropship.
- Collection planning support based on product performance and sales efficiency.

## Workflow

### 1. Data Discovery
Find the latest `reports/files_generation_X/` folder by choosing the highest `X`.

### 2. Visualization Generation
Run:

```bash
python generate_graphs_only.py
```

This creates three charts in `~/Desktop/eddy_marketing_insights_X/`:

- `channel_sales_comparison.png`
- `top_products_performance.png`
- `sales_efficiency.png`

### 3. Report Synthesis
Create `MARKETING_REPORT.md` inside `~/Desktop/eddy_marketing_insights_X/`.

Suggested report structure:

```markdown
# Channel Performance and Design Insight Report

## Executive Summary

## Channel Sales and Efficiency

## Design Team Insights

## Collection Recommendations

## Sales Efficiency and Operations

## Strategic Recommendations for Next Collection
```

## Guardrails

- Never include customer PII.
- For wholesale, use `estimated_wholesale_revenue` when `net_sales` is zero.
- Keep image paths relative inside the generated report folder.
