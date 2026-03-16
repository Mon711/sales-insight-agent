"""
Data Loader module for Shopify order exports.

This module handles loading and basic validation of Shopify CSV exports.
It provides a simple interface to load order data and ensure data quality.
"""

import pandas as pd
from pathlib import Path


class ShopifyDataLoader:
    """
    Loads Shopify order export CSV files.

    This loader simply reads the CSV file and loads it into a pandas DataFrame.
    It does NOT make assumptions about which columns exist - you may have different
    columns depending on your Shopify export format.

    The loader performs:
    1. Basic validation (file exists, readable)
    2. Loading the CSV data as-is
    """

    def __init__(self, file_path: str):
        """
        Initialize the data loader.

        Args:
            file_path: path to the Shopify CSV export file
        """
        self.file_path = Path(file_path)
        self.df = None
        self._validate_file_exists()

    def _validate_file_exists(self) -> None:
        """Check that the CSV file exists and is readable."""
        if not self.file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.file_path}")
        if not self.file_path.is_file():
            raise ValueError(f"Path is not a file: {self.file_path}")

    def load(self) -> pd.DataFrame:
        """
        Load the CSV file as-is.

        Returns:
            pandas DataFrame with the loaded data (all columns as strings)
        """
        # Load the CSV file
        # dtype=str keeps all columns as strings initially
        # This avoids type inference issues and preserves the data exactly as exported
        self.df = pd.read_csv(self.file_path, dtype=str)

        return self.df


    def get_data(self) -> pd.DataFrame:
        """
        Get the loaded dataframe.

        Returns:
            pandas DataFrame with order data
        """
        if self.df is None:
            raise ValueError("Data not loaded. Call load() first.")
        return self.df.copy()

