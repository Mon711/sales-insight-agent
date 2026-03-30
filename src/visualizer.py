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

    for report in reports:
        channel_name = report.get("channel_name", "Unknown")
        summary = report.get("channel_summary", {})
        is_wholesale = channel_name == "wholesale"
        wholesale_revenue = summary.get("estimated_wholesale_revenue")
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
        display_returns = abs(float(summary.get("total_gross_sales", 0) or 0) - display_net_sales)
        
        channel_data.append({
            "Channel": channel_name,
            "Gross Sales": summary.get("total_gross_sales", 0),
            "Net Sales": display_net_sales,
            "Total Sales": display_total_sales,
            "Items Sold": summary.get("total_items_sold", 0),
            "Returns": display_returns # Approximation
        })

        products = report.get("product_sales_performance", [])
        for p in products:
            product_net_sales = float(
                p.get("estimated_net_sales")
                if is_wholesale and p.get("estimated_net_sales") is not None
                else p.get("true_net_sales", 0)
            )
            all_product_data.append({
                "Product": p.get("product_title", "Unknown"),
                "Channel": channel_name,
                "Net Sales": product_net_sales
            })

    df_channels = pd.DataFrame(channel_data)
    df_products = pd.DataFrame(all_product_data)

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
