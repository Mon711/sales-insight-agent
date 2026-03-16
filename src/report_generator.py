"""
Report Generator module for creating markdown sales insight reports.

This module takes the aggregated data and metrics and formats them
into a professional markdown report with insights and recommendations.
"""

import pandas as pd
from pathlib import Path


def generate_sales_report(
    store_metrics: dict,
    sales_by_product: pd.DataFrame,
    output_path: str = "reports/sales_insight_report.md"
) -> str:
    """
    Generate a markdown sales insight report.

    Creates a formatted markdown report with:
    - Store summary metrics
    - Top 10 products table
    - Key observations
    - Marketing opportunities

    Args:
        store_metrics: Dictionary with keys:
            - total_store_revenue
            - total_units_sold
            - number_of_product_families
        sales_by_product: DataFrame with columns:
            - product_family
            - total_units_sold
            - total_revenue
        output_path: Path to save the report (default: reports/sales_insight_report.md)

    Returns:
        String containing the markdown report content
    """
    # Start building the markdown report as a string
    report = []

    # === HEADER ===
    report.append("# Sales Insight Report\n")

    # === STORE SUMMARY SECTION ===
    report.append("## Store Summary\n")

    # Extract metrics for easy use
    total_revenue = store_metrics['total_store_revenue']
    total_units = store_metrics['total_units_sold']
    unique_products = store_metrics['number_of_product_families']

    # Calculate average revenue per unit
    avg_revenue_per_unit = total_revenue / total_units if total_units > 0 else 0

    # Add summary metrics to report
    report.append(f"- **Total Store Revenue:** ${total_revenue:,.2f}\n")
    report.append(f"- **Total Units Sold:** {int(total_units)}\n")
    report.append(f"- **Unique Products Sold:** {unique_products}\n")
    report.append(f"- **Average Revenue Per Unit:** ${avg_revenue_per_unit:,.2f}\n")
    report.append("")

    # === TOP 10 PRODUCTS TABLE ===
    report.append("## Top 10 Products by Units Sold\n")

    # Get the top 10 products
    top_10 = sales_by_product.head(10)

    # Create markdown table header
    report.append("| Product Family | Units Sold | Total Revenue |")
    report.append("|---|---:|---:|")

    # Add each product as a row
    for _, row in top_10.iterrows():
        product_name = row['product_family']
        units = int(row['total_units_sold'])
        revenue = row['total_revenue']
        report.append(f"| {product_name} | {units} | ${revenue:,.2f} |")

    report.append("")

    # === KEY OBSERVATIONS ===
    report.append("## Key Observations\n")

    # Get top and highest revenue products
    top_product = top_10.iloc[0]
    highest_revenue_product = sales_by_product.loc[
        sales_by_product['total_revenue'].idxmax()
    ]

    # Check if top unit seller is also top revenue earner
    same_product = (
        top_product['product_family'] == highest_revenue_product['product_family']
    )

    # Add observations
    report.append(
        f"- **Best Seller:** {top_product['product_family']} leads with "
        f"{int(top_product['total_units_sold'])} units sold.\n"
    )

    report.append(
        f"- **Highest Revenue Generator:** {highest_revenue_product['product_family']} "
        f"generated ${highest_revenue_product['total_revenue']:,.2f} in total revenue.\n"
    )

    if not same_product:
        report.append(
            f"- **Product Mix Insight:** The top unit seller ({top_product['product_family']}) "
            f"is different from the highest revenue product ({highest_revenue_product['product_family']}), "
            f"suggesting price variance across product lines. Consider promoting premium products "
            f"to increase average order value.\n"
        )
    else:
        report.append(
            f"- **Strong Performer:** {top_product['product_family']} excels in both volume and revenue, "
            f"making it a consistent customer favorite.\n"
        )

    report.append("")

    # === MARKETING OPPORTUNITIES ===
    report.append("## Marketing Opportunities\n")

    # Generate marketing recommendations
    report.append(
        f"1. **Spotlight Top Seller:** {top_product['product_family']} is your best performer. "
        f"Feature it prominently in email campaigns and homepage banners to capitalize on its popularity.\n"
    )

    report.append(
        f"2. **Premium Product Promotion:** {highest_revenue_product['product_family']} generates "
        f"significant revenue despite lower unit sales. Target high-value customers with this premium offering.\n"
    )

    # Get second and third best sellers for bundle recommendation
    if len(top_10) >= 3:
        second_product = top_10.iloc[1]['product_family']
        third_product = top_10.iloc[2]['product_family']
        report.append(
            f"3. **Bundle Opportunity:** Create bundle offers combining {top_product['product_family']}, "
            f"{second_product}, and {third_product} to increase average order value.\n"
        )

    report.append(
        f"4. **Expand Product Line:** With {unique_products} successful products, consider expanding "
        f"similar styles within the top categories. Use the success of {top_product['product_family']} "
        f"as a template for new designs.\n"
    )

    report.append(
        f"5. **Customer Segmentation:** Segment your audience by purchase preference. Customers who buy "
        f"{top_product['product_family']} may respond differently to campaigns than those purchasing "
        f"{highest_revenue_product['product_family']}. Tailor messaging accordingly.\n"
    )

    report.append("")

    # === METADATA ===
    report.append("---\n")
    report.append("*Report generated by Sales Insight Agent*\n")

    # Join all lines into a single string
    report_content = "\n".join(report)

    # Create reports directory if it doesn't exist
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Write the report to file
    with open(output_path_obj, 'w') as f:
        f.write(report_content)

    # Return the content so it can be displayed
    return report_content
