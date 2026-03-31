"""
Shopify Data Visualizer Engine for Marketing Reports.
Generates charts from ShopifyQL JSON reports for AI analysis.
"""

import os
import json
import re
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import argparse
from typing import List, Dict, Any
from pathlib import Path

def load_reports(directory: str) -> List[Dict[str, Any]]:
    """Loads all report_*.json files from the directory."""
    reports = []
    for filename in os.listdir(directory):
        if filename.startswith("report_") and filename.endswith(".json"):
            file_path = os.path.join(directory, filename)
            with open(file_path, 'r') as f:
                reports.append(json.load(f))
    return reports

def get_marketing_output_dir(source_directory: str) -> str:
    """
    Map reports/files_generation_<n> to ~/Desktop/eddy_marketing_insights_<n>.

    If the source directory does not match that pattern, fall back to a sibling
    marketing folder so the function still behaves predictably.
    """
    source_path = Path(source_directory).resolve()
    match = re.search(r"files_generation_(\d+)$", source_path.name)
    if match:
        output_name = f"eddy_marketing_insights_{match.group(1)}"
    else:
        output_name = f"eddy_marketing_insights_{source_path.name}"

    return os.path.expanduser(os.path.join("~/Desktop", output_name))


def generate_visualizations(source_directory: str, output_directory: str | None = None):
    """Aggregates report data from the source folder and generates charts."""
    reports = load_reports(source_directory)
    if not reports:
        print(f"No reports found in {source_directory}")
        return

    if output_directory is None:
        output_directory = get_marketing_output_dir(source_directory)
    os.makedirs(output_directory, exist_ok=True)

    # Data Aggregation
    channel_data = []
    all_product_data = []
    channel_product_totals: Dict[str, Dict[str, float]] = {}

    for report in reports:
        channel_name = report.get("channel_name", "Unknown")
        summary = report.get("channel_summary", {})
        products = report.get("product_sales_performance", [])

        is_wholesale = channel_name == "wholesale"
        wholesale_revenue = summary.get("estimated_wholesale_revenue")
        gross_sales = float(summary.get("total_gross_sales", 0) or 0)
        display_net_sales = float(
            wholesale_revenue
            if is_wholesale and wholesale_revenue is not None
            else summary.get("total_net_sales", 0)
        )
        display_total_sales = float(
            wholesale_revenue
            if is_wholesale and wholesale_revenue is not None
            else summary.get("total_sales", 0)
        )
        orders = float(summary.get("total_orders", 0) or 0)
        discount_total = 0.0
        return_total = 0.0

        for p in products:
            discount_total += abs(float(p.get("discounts", 0) or 0))
            return_total += abs(float(p.get("returns", 0) or 0))

        aov = display_net_sales / orders if orders else 0.0
        discount_burden = discount_total / gross_sales if gross_sales else 0.0
        return_burden = return_total / gross_sales if gross_sales else 0.0

        channel_data.append({
            "Channel": channel_name,
            "Gross Sales": gross_sales,
            "Net Sales": display_net_sales,
            "Total Sales": display_total_sales,
            "Orders": orders,
            "Items Sold": float(summary.get("total_items_sold", 0) or 0),
            "AOV": aov,
            "Discount Burden": discount_burden * 100,
            "Return Burden": return_burden * 100,
            "Discounts": discount_total,
            "Returns": return_total,
        })

        channel_product_totals.setdefault(channel_name, {})
        for p in products:
            product_title = p.get("product_title", "Unknown")
            product_net_sales = float(
                p.get("estimated_net_sales")
                if is_wholesale and p.get("estimated_net_sales") is not None
                else p.get("true_net_sales", 0)
            )
            channel_product_totals[channel_name][product_title] = (
                channel_product_totals[channel_name].get(product_title, 0.0) + product_net_sales
            )
            all_product_data.append({
                "Product": product_title,
                "Channel": channel_name,
                "Net Sales": product_net_sales
            })

    df_channels = pd.DataFrame(channel_data)
    df_products = pd.DataFrame(all_product_data)
    concentration_rows = []
    for row in channel_data:
        channel_name = row["Channel"]
        net_sales = float(row.get("Net Sales", 0) or 0)
        product_totals = sorted(channel_product_totals.get(channel_name, {}).values(), reverse=True)
        concentration_rows.append({
            "Channel": channel_name,
            "Top 1 Share": ((sum(product_totals[:1]) / net_sales) * 100) if net_sales else 0,
            "Top 3 Share": ((sum(product_totals[:3]) / net_sales) * 100) if net_sales else 0,
            "Top 5 Share": ((sum(product_totals[:5]) / net_sales) * 100) if net_sales else 0,
        })
    df_concentration = pd.DataFrame(concentration_rows)

    # Set Style
    sns.set_theme(style="whitegrid", palette="muted")
    plt.rcParams['figure.dpi'] = 300

    # 1. Total Sales by Channel (Bar Chart)
    if not df_channels.empty:
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_channels, x="Channel", y="Total Sales", palette="viridis")
        plt.title("Total Sales by Sales Channel", fontsize=16, fontweight='bold')
        plt.ylabel("Sales ($)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "channel_sales_comparison.png"))
        plt.close()

    # 2. Top 10 Products by Net Sales (Overall)
    if not df_products.empty:
        top_products = df_products.groupby("Product")["Net Sales"].sum().sort_values(ascending=False).head(10).reset_index()
        plt.figure(figsize=(12, 8))
        sns.barplot(data=top_products, x="Net Sales", y="Product", palette="rocket")
        plt.title("Top 10 Products by Total Net Sales", fontsize=16, fontweight='bold')
        plt.xlabel("Net Sales ($)")
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "top_products_performance.png"))
        plt.close()

    # 3. Efficiency: Gross vs Net Sales by Channel
    if not df_channels.empty:
        df_melted = df_channels.melt(id_vars="Channel", value_vars=["Gross Sales", "Net Sales"], var_name="Type", value_name="Amount")
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_melted, x="Channel", y="Amount", hue="Type", palette="coolwarm")
        plt.title("Gross vs Net Sales (Sales Efficiency)", fontsize=16, fontweight='bold')
        plt.ylabel("Amount ($)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "sales_efficiency.png"))
        plt.close()

    # 4. Average Order Value by Channel
    if not df_channels.empty and "AOV" in df_channels:
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_channels, x="Channel", y="AOV", palette="crest")
        plt.title("Average Order Value by Channel", fontsize=16, fontweight='bold')
        plt.ylabel("AOV ($)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "average_order_value_by_channel.png"))
        plt.close()

    # 5. Product Concentration by Channel
    if not df_concentration.empty:
        df_concentration_melted = df_concentration.melt(
            id_vars="Channel",
            value_vars=["Top 1 Share", "Top 3 Share", "Top 5 Share"],
            var_name="Concentration",
            value_name="Share",
        )
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_concentration_melted, x="Channel", y="Share", hue="Concentration", palette="mako")
        plt.title("Product Concentration by Channel", fontsize=16, fontweight='bold')
        plt.ylabel("Share of Channel Net Sales (%)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "product_concentration_by_channel.png"))
        plt.close()

    # 6. Return Burden by Channel
    if not df_channels.empty and "Return Burden" in df_channels:
        plt.figure(figsize=(10, 6))
        sns.barplot(data=df_channels, x="Channel", y="Return Burden", palette="flare")
        plt.title("Return Burden by Channel", fontsize=16, fontweight='bold')
        plt.ylabel("Returns / Gross Sales (%)")
        plt.xticks(rotation=45)
        plt.tight_layout()
        plt.savefig(os.path.join(output_directory, "return_burden_by_channel.png"))
        plt.close()

    print(f"Visualizations generated successfully in {output_directory}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate marketing charts from Shopify reports.")
    parser.add_argument("source_directory", help="Directory containing report_*.json files")
    parser.add_argument(
        "--output-directory",
        help="Optional directory for generated charts. Defaults to ~/Desktop/eddy_marketing_insights_<n>.",
    )
    args = parser.parse_args()
    
    generate_visualizations(args.source_directory, args.output_directory)
