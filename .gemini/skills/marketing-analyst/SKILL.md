---
name: marketing-analyst
description: Expert AI Marketing Analyst specializing in Shopify data analysis and channel-aware product insights. Use when you need to identify which product types and collections are performing best across specific sales channels (Online, POS, Wholesale, Dropship) to inform future design and collection planning.
---

# Shopify Marketing & Design Insights Workflow

This skill transforms raw Shopify analytics (ShopifyQL) into actionable insights that bridge the gap between sales performance and collection design.

## Core Capabilities

- **Automated Data Discovery:** Identifies the most recent `reports/files_generation_X/` folder.
- **Visual Intelligence:** Uses `src/visualizer.py` to generate professional charts in `~/Desktop/eddy_marketing_insights_X/`.
- **Channel-Aware Design Insights:** Analyzes which product types (e.g., "Dresses" vs "Blazers") are trending in specific channels (e.g., "Online Store" vs "Wholesale") to guide the design team.
- **Collection Planning Support:** Replaces "random" design choices with data-backed recommendations for future collections.

## Procedural Workflow

### 1. Data Discovery
Identify the folder with the highest `X` in `reports/files_generation_X`.
- Use `list_directory` on `reports/` to find all `files_generation_*` folders.
- Sort them numerically to find the latest.

### 2. Visualization Generation
Execute the visualizer script on the identified folder.
- Run: `python src/visualizer.py reports/files_generation_X/`
- This generates:
    - `channel_sales_comparison.png`
    - `top_products_performance.png`
    - `sales_efficiency.png`
 - The images are saved in `~/Desktop/eddy_marketing_insights_X/`, where `X` matches the source folder number.

### 3. Report Synthesis
Create `MARKETING_REPORT.md` inside `~/Desktop/eddy_marketing_insights_X/`.

#### Report Structure Template:

```markdown
# 📈 Channel Performance & Design Insight Report
*Generated on: [Current Date]*
*Data Period: [Report Start] to [Report End]*

## 🚀 Executive Summary
[High-level performance summary. Focus on which channel is currently leading and what it means for the brand.]

## 📊 Channel Sales & Efficiency
![Channel Sales Comparison](./channel_sales_comparison.png)

| Channel | Net Sales | Items Sold | Sales Efficiency |
|---------|-----------|------------|------------------|
| [Channel Name] | $[Amount] | [Qty] | [Ratio]% |

## 👗 Design Team Insights: What's Working Where?
![Top Products Performance](./top_products_performance.png)

### Channel-Specific Trends:
- **Online Store:** [Identify top product types. e.g., "Dresses are driving 60% of volume."]
- **Wholesale:** [Identify what bulk buyers are choosing. e.g., "Higher demand for basics/staples."]
- **POS:** [Identify in-person favorites.]

### Collection Recommendations:
- **High-Growth Categories:** [Which categories should the design team double down on?]
- **Underperforming Categories:** [Which styles are not moving and may need a design pivot?]

## 💡 Sales Efficiency & Operations
![Sales Efficiency](./sales_efficiency.png)
[Analyze returns/discounts. High returns in specific categories may indicate sizing or fit issues that the design team needs to address.]

## 🛠 Strategic Recommendations for Next Collection
- **Design Directive 1:** [Specific product type recommendation based on data]
- **Design Directive 2:** [Channel-specific collection suggestion]
```

## Guardrails
- **Data Privacy:** Never include PII (customer names/emails) in the report.
- **Accuracy:** Ensure "Wholesale" revenue is estimated as `gross_sales ÷ 2` if `net_sales` is 0 (Shopify baseline).
- **Paths:** Always use relative paths from the report folder to the images for correct rendering.
