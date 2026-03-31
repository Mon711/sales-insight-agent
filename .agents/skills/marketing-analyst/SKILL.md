---
name: marketing-analyst
description: Create and analyze the Shopify marketing report pipeline for the latest sales data. Use when the user wants a single report with separate channel sections, cross-channel analysis, chart generation, or strategic recommendations from the newest report folder.
---

# Marketing Analyst Skill

Use this skill to turn the latest Shopify sales exports into one comprehensive report for Eddy.

## Goal

Produce one Markdown report that:

- breaks out each channel separately
- ends with aggregate cross-channel analysis
- translates data into plain English
- gives concrete recommendations for marketing, design, merchandising, and brand leadership

## Workflow

1. If the latest `reports/files_generation_X/` folder does not exist yet, run:
   ```bash
   python run_reports.py
   ```
2. Find the newest `reports/files_generation_X/` folder.
3. Run the chart engine:
   ```bash
   python src/visualizer.py reports/files_generation_X/
   ```
4. Read the JSON reports and generated charts, then produce one complete Markdown report body.
   - Embed the generated PNG charts in the Markdown using image syntax (for example: `![Channel Sales Comparison](channel_sales_comparison.png)`).
   - Reference chart takeaways directly inside the channel analysis narrative instead of listing images without explanation.
   - Prefer returning Markdown text to the caller so wrapper commands can save the file in the final destination.
5. If the user wants a terminal-friendly entry point, use `./scripts/marketing_report.sh`.

## Data And Metric Rules

- Use Shopify-derived data only. Do not invent sample data.
- Treat `estimated_wholesale_revenue` as the wholesale revenue figure when `net_sales` is zero.
- Use the available Shopify metrics to compute:
  - average order value (`AOV = net sales or estimated revenue / total orders`)
  - discount burden (`abs(discounts) / gross_sales`)
  - return burden (`abs(returns) / gross_sales`)
  - product concentration (`top 1`, `top 3`, and `top 5` share where possible)
  - product-type mix
- If a metric is distorted by channel mechanics, explain that plainly instead of forcing a false comparison.
- Do not include customer PII.
- Explain jargon in plain English.

## Benchmark Lens

Use retail and ecommerce heuristics, not just raw totals:

- High discount dependency suggests pricing or demand friction.
- High return burden can indicate fit, quality, expectation gaps, or partner mismatch.
- Strong revenue with weak efficiency suggests poor-quality demand.
- High concentration in one or two products can be a strength and a risk.
- Compare each channel by role:
  - online store: demand capture and conversion
  - POS: in-person validation, fit, and customer confidence
  - wholesale: assortment strength and partner fit
  - dropship/partners: channel economics and assortment discipline

Use heuristic language when needed, and say when something is a rule of thumb rather than a hard benchmark.

## Report Structure

Use this structure in the final Markdown report:

1. Executive Summary
2. Methodology and Data Window
3. Channel Summary Table
4. Online Store Analysis
5. POS Analysis
6. Wholesale Analysis
7. Dropship / Partner Analysis
8. Cross-Channel Aggregate Analysis
9. Strategic Recommendations by Team
10. Risks, Watchouts, and Next Tests

## How Each Channel Section Should Read

Each channel section should include:

- Snapshot: sales, orders, AOV, items sold, gross/net, efficiency, discount/return burden
- What is working: hero products, product types, or assortment patterns
- What is not working: weak sell-through, concentration risk, high discounting, or returns
- What it means: why the numbers matter for Eddy
- Actions: 2 to 4 concrete next steps for the right team

If a channel has no data in the period, say so and explain what that means.

## Cross-Channel Analysis

At the end, explain:

- which products win across multiple channels
- which channels reinforce each other and which conflict
- where the brand is healthy versus over-dependent on a few styles or partners
- whether revenue quality is improving or simply growing through discounting or wholesale volume

## Recommendation Style

Write recommendations so a non-expert can understand them:

- Start with the observation
- Explain why it matters
- Give a specific action
- Call out which team owns the next step

## Expected Outcome

- One comprehensive Markdown report
- Separate sections for each channel
- One aggregate conclusion at the end
- Clear, useful recommendations for marketing, design, merchandising, and brand leadership
- Charts generated in `~/Desktop/eddy_marketing_insights_X/` and embedded in `MARKETING_REPORT.md`

## Notes

- Use `generate_graphs_only.py` only as a standalone chart-testing helper, not as part of the main pipeline.
- The Codex app command `report/marketing_report` and the terminal wrapper `./scripts/marketing_report.sh` should both trigger this flow.
