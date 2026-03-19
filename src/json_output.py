"""
JSON Output module for creating LLM-ready analysis files.

This module converts analysis data into structured JSON format
that's easy for language models to parse and understand.
"""

import json
import pandas as pd
from pathlib import Path


def generate_analysis_json(
    store_metrics: dict,
    sales_by_product: pd.DataFrame,
    output_path: str = "analysis_summary.json"
) -> str:
    """
    Generate a structured JSON file with sales analysis.

    Creates a JSON file with:
    - Store summary metrics
    - Top 10 products
    - All products with revenue and units

    Args:
        store_metrics: Dictionary with keys:
            - total_store_revenue
            - total_units_sold
            - number_of_product_families
        sales_by_product: DataFrame with columns:
            - product_family
            - total_units_sold
            - total_revenue
        output_path: Path to save the JSON file (default: analysis_summary.json)

    Returns:
        JSON string of the analysis data
    """

    # Calculate average revenue per unit
    total_revenue = store_metrics['total_store_revenue']
    total_units = store_metrics['total_units_sold']
    avg_revenue_per_unit = total_revenue / total_units if total_units > 0 else 0

    # Build the store summary section
    # This is high-level data about the entire store
    store_summary = {
        "total_store_revenue": round(total_revenue, 2),
        "total_units_sold": int(total_units),
        "unique_products_sold": store_metrics['number_of_product_families'],
        "average_revenue_per_unit": round(avg_revenue_per_unit, 2)
    }

    # Build the top 10 products section
    # Get the first 10 rows (already sorted by units sold)
    top_10 = sales_by_product.head(10)

    top_10_products = []
    for _, row in top_10.iterrows():
        product_entry = {
            "product_family": row['product_family'],
            "units_sold": int(row['total_units_sold']),
            "total_revenue": round(row['total_revenue'], 2)
        }
        top_10_products.append(product_entry)

    # Build the all products section
    # This includes every product with both metrics
    # Sorted by units sold descending (same as sales_by_product)
    all_products = []
    for _, row in sales_by_product.iterrows():
        product_entry = {
            "product_family": row['product_family'],
            "units_sold": int(row['total_units_sold']),
            "total_revenue": round(row['total_revenue'], 2)
        }
        all_products.append(product_entry)

    # Assemble the complete analysis object
    # This is the root structure that contains all analysis data
    analysis_data = {
        "metadata": {
            "report_type": "sales_analysis",
            "version": "1.0",
            "note": "Structured JSON output for LLM analysis"
        },
        "store_summary": store_summary,
        "top_10_products": top_10_products,
        "all_products": all_products
    }

    # Convert to JSON string with nice formatting
    # indent=2 makes it human-readable (LLMs also prefer formatted JSON)
    # sort_keys=False keeps our intended order
    json_string = json.dumps(analysis_data, indent=2)

    # Create output directory if needed
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Write JSON to file
    with open(output_path_obj, 'w') as f:
        f.write(json_string)

    return json_string
