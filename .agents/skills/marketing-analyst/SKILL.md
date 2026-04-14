---
name: marketing-analyst
description: Create and analyze the annual Shopify performance report (Top 20 performers, Top 20 underperformers, consolidated product breadth, and dress variant families) with local product images and practical recommendations.
---

# Marketing Analyst Skill

Use this skill to produce the annual product-performance report for Eddy from ShopifyQL outputs.

## Goal

Produce one Markdown report that:

- analyzes annual Top 20 performers, Top 20 underperformers, consolidated all-products sales, and Top/Bottom 20 dress variant families
- explains what the numbers mean in plain English
- includes product images inline where the product is analyzed
- embeds only local image paths (no CDN image links)
- includes full query-result tables for:
  - Top 20 performers
  - Top 20 underperformers
  - Top 20 dress variant families
  - Bottom 20 dress variant families
- ends with concrete recommendations by function (marketing, design, merchandising)

## Source Of Truth

- Primary data file: `annual_report_2025.json`
- Location: latest `files_generation_X` folder under the run output directory
- Query strings used for generation are stored under `queries` in the JSON

## Workflow

1. If annual report JSON is missing, run:
   ```bash
   ./scripts/annual_report_2025.sh
   ```
2. Read `annual_report_2025.json`.
3. Validate report scope from JSON:
   - `top_performers.rows`
   - `underperformers.rows`
   - `all_products_sold.rows`
   - `dress_variant_families.top_rows`
   - `dress_variant_families.bottom_rows`
   - `product_image_focus.top_5_products`
   - `product_image_focus.bottom_5_products`
4. Write one Markdown report body.
   - Place product images inline near the exact product discussion.
   - Prefer `product_image.local_path`.
   - If local image path is absent, do not embed an image for that product.
   - Never use `product_image.remote_url` in markdown embeds.
5. Keep image count controlled:
   - Must include visuals for products in `top_5_products` and `bottom_5_products` when local paths exist.
   - You may analyze additional products/images where local image paths exist and it improves the analysis.
6. Include complete query-result tables in Markdown for each required report slice.
   - The top/bottom performer tables must reflect the exact ShopifyQL output only.
   - Do not add computed columns such as product IDs, variant prices, or calculated selling prices.

## Analysis Rules

- Use Shopify data only. No synthetic numbers.
- Keep ranking integrity:
  - top products are from rank order in `top_performers.rows`
  - bottom products are from rank order in `underperformers.rows`
- Use `returned_quantity_rate` as return-rate signal where present.
- Distinguish product-level findings from category-level findings.
- Use `all_products_sold.rows` to describe the overall product mix and breadth.
- For dress variant family analysis, use the grouped top/bottom rows and keep the calculations exactly as stored in JSON.
- If image match status is `ambiguous`, `not_found`, `skipped`, or missing `local_path`, avoid visual claims for that product.
- When inferring fabric/material or construction cues from photos, explicitly label it as visual inference.
- Ground recommendations in observed report patterns and practical industry standards.

## Report Structure

1. Executive Summary
2. Methodology and Data Window
3. Top 20 Performers
4. Top 20 Underperformers
5. All Products Sold
6. Dress Variant Family Insights
7. Query Result Tables
8. Recommendations and Next Actions

## Writing Style

- Plain English, concise, action-oriented.
- For each major claim:
  - what happened
  - why it matters
  - what to do next
- Recommendations must be specific and owner-oriented (marketing, design, merchandising).

## Output

- Return Markdown only.
- No preamble, no process notes, no tool logs.
