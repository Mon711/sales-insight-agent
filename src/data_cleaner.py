"""
Data Cleaner module for processing Shopify order data.

This module contains functions to clean and transform the raw data
from Shopify exports into a format we can analyze.
"""

import pandas as pd


def extract_product_family(lineitem_name: str) -> str:
    """
    Extract the base product name (product family) from a line item name.

    Shopify product names often contain variant information separated by " - ".
    This function extracts just the base product name for grouping.

    Examples:
        "Daisy Dress - Medium / Caramel Victorian Floral" → "Daisy Dress"
        "Glasses Case" → "Glasses Case"
        "Katherine Dress - X-Small / Caramel Victorian Floral" → "Katherine Dress"

    Args:
        lineitem_name: The full product name from the CSV

    Returns:
        The base product name (everything before the first " - ")
        or the full name if no " - " exists
    """
    # Check if the string contains " - " (space, dash, space)
    if " - " in lineitem_name:
        # Split by " - " and take the first part (index 0)
        # split() returns a list, so we take [0]
        return lineitem_name.split(" - ")[0]
    else:
        # No " - " found, return the full name as-is
        return lineitem_name


def add_product_family(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add a product_family column to the dataframe.

    Creates a new column "product_family" by applying the extract_product_family
    function to every row in the "Lineitem name" column.

    Args:
        df: pandas DataFrame with "Lineitem name" column

    Returns:
        New DataFrame with added "product_family" column
    """
    # Create a copy so we don't modify the original
    df_clean = df.copy()

    # Apply the extract_product_family function to each row
    # The apply() method runs the function on every value in the column
    # and creates a new column with the results
    df_clean['product_family'] = df_clean['Lineitem name'].apply(extract_product_family)

    return df_clean


def calculate_store_metrics(df: pd.DataFrame) -> dict:
    """
    Calculate store-level summary metrics.

    This function calculates:
    1. Total store revenue (from the Total column)
    2. Total units sold across all products
    3. Number of unique product families

    Args:
        df: pandas DataFrame with columns:
            - 'Total' (order total)
            - 'Lineitem quantity' (units per line item)
            - 'product_family'

    Returns:
        Dictionary with keys:
            - total_store_revenue: Sum of all order totals
            - total_units_sold: Sum of all quantities
            - number_of_product_families: Count of unique products
    """
    # Create a copy to avoid modifying the original
    df_metrics = df.copy()

    # Convert Total column to numeric
    # This column has the order total and some NaN values
    # skipna=True (default) means NaN values are ignored when summing
    df_metrics['Total'] = pd.to_numeric(df_metrics['Total'], errors='coerce')

    # Convert Lineitem quantity to numeric
    df_metrics['Lineitem quantity'] = pd.to_numeric(
        df_metrics['Lineitem quantity'],
        errors='coerce'
    )

    # Calculate total store revenue
    # sum() by default ignores NaN values (skipna=True)
    total_store_revenue = df_metrics['Total'].sum()

    # Calculate total units sold
    total_units_sold = df_metrics['Lineitem quantity'].sum()

    # Calculate number of unique product families
    # nunique() counts distinct/unique values
    number_of_product_families = df_metrics['product_family'].nunique()

    # Return results as a dictionary
    return {
        'total_store_revenue': total_store_revenue,
        'total_units_sold': total_units_sold,
        'number_of_product_families': number_of_product_families
    }


def calculate_product_sales(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculate total units sold and revenue per product family.

    This function:
    1. Creates a product_revenue column (quantity × price)
    2. Groups by product_family
    3. Sums units and revenue for each family
    4. Sorts by units sold (descending)

    Args:
        df: pandas DataFrame with columns:
            - 'Lineitem quantity' (converted to numeric)
            - 'Lineitem price' (converted to numeric)
            - 'product_family'

    Returns:
        DataFrame with columns: product_family, total_units_sold, total_revenue
        Sorted by total_units_sold in descending order
    """
    # Create a copy to avoid modifying the original
    df_analysis = df.copy()

    # Convert quantity and price to numeric types
    # errors='coerce' means any values that can't be converted become NaN
    df_analysis['Lineitem quantity'] = pd.to_numeric(
        df_analysis['Lineitem quantity'],
        errors='coerce'
    )
    df_analysis['Lineitem price'] = pd.to_numeric(
        df_analysis['Lineitem price'],
        errors='coerce'
    )

    # Create product_revenue column by multiplying quantity × price
    # This gives us the revenue for each line item
    df_analysis['product_revenue'] = (
        df_analysis['Lineitem quantity'] * df_analysis['Lineitem price']
    )

    # Group by product_family and aggregate
    # groupby() creates groups of rows with the same product_family
    # .agg() (aggregate) applies functions to each group
    sales_by_product = df_analysis.groupby('product_family').agg(
        total_units_sold=('Lineitem quantity', 'sum'),
        total_revenue=('product_revenue', 'sum')
    ).reset_index()

    # Sort by total_units_sold in descending order (highest first)
    # ascending=False means largest values come first
    sales_by_product = sales_by_product.sort_values(
        'total_units_sold',
        ascending=False
    )

    return sales_by_product
