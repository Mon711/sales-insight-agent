"""
Main entry point for Sales Insight Agent.

This script demonstrates how to load and clean Shopify order data.
Currently working on the data cleaning step (extract product families).
"""

import sys
from data_loader import ShopifyDataLoader
from data_cleaner import add_product_family, calculate_product_sales, calculate_store_metrics
from report_generator import generate_sales_report


def main(csv_path=None):
    """
    Load and display basic information about order data.

    Args:
        csv_path: Path to the Shopify CSV export file.
                 If not provided, defaults to data/raw/orders.csv
    """
    if csv_path is None:
        csv_path = "data/raw/orders.csv"

    try:
        # Initialize the data loader
        print(f"Loading data from {csv_path}...\n")
        loader = ShopifyDataLoader(csv_path)

        # Load the raw data
        df = loader.load()

        # Apply data cleaning: extract product families
        print("Extracting product families...")
        df_clean = add_product_family(df)

        # Calculate store-level metrics
        print("Calculating store metrics...")
        store_metrics = calculate_store_metrics(df_clean)

        # Calculate product-level sales metrics
        print("Calculating product sales...\n")
        sales_summary = calculate_product_sales(df_clean)

        # Display store summary
        print("=" * 50)
        print("Store Summary")
        print("=" * 50)
        print(f"Total Store Revenue: ${store_metrics['total_store_revenue']:,.2f}")
        print(f"Total Units Sold: {int(store_metrics['total_units_sold'])}")
        print(f"Unique Products Sold: {store_metrics['number_of_product_families']}")
        print()

        # Display top 10 products by units sold
        print("=" * 50)
        print("Top 10 Products by Units Sold")
        print("=" * 50)
        top_10 = sales_summary.head(10)
        # Format for better readability
        print(top_10.to_string(index=False))
        print()

        # Generate and save the markdown report
        print("=" * 50)
        print("Generating Sales Insight Report...")
        print("=" * 50)
        report_content = generate_sales_report(store_metrics, sales_summary)
        print(f"\nReport saved to: reports/sales_insight_report.md")
        print("\nReport Preview:")
        print("-" * 50)
        print(report_content)

    except FileNotFoundError as e:
        print(f"Error: {e}")
        print(f"Please place your Shopify CSV export at: {csv_path}")
    except ValueError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    # Allow passing CSV path as command-line argument
    csv_path = sys.argv[1] if len(sys.argv) > 1 else None
    main(csv_path)
