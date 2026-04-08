import unittest

from src.product_reports import (
    build_annual_categories_query,
    build_annual_products_query,
    select_ranked_rows,
)


class TestAnnualReports(unittest.TestCase):
    def test_build_annual_products_query_desc(self):
        query = build_annual_products_query(year=2025, limit=20, descending=True)

        self.assertIn("FROM sales", query)
        self.assertIn("SHOW net_sales, net_items_sold, gross_sales, average_order_value", query)
        self.assertIn("returned_quantity_rate", query)
        self.assertIn("WHERE product_title IS NOT NULL", query)
        self.assertIn("GROUP BY product_title, product_variant_price WITH TOTALS", query)
        self.assertIn("SINCE 2025-01-01 UNTIL 2025-12-31", query)
        self.assertIn("ORDER BY net_sales DESC", query)
        self.assertIn("LIMIT 20", query)

    def test_build_annual_products_query_asc(self):
        query = build_annual_products_query(year=2025, descending=False)
        self.assertIn("ORDER BY net_sales ASC", query)
        self.assertNotIn("product_id", query)

    def test_build_annual_categories_query(self):
        query = build_annual_categories_query(year=2025, limit=20)
        self.assertIn("GROUP BY product_type WITH TOTALS", query)
        self.assertIn("SHOW net_sales, net_items_sold", query)
        self.assertIn("ORDER BY net_sales DESC", query)

    def test_select_ranked_rows(self):
        rows = [
            {
                "product_title": "Ariana Dress",
                "product_image": {"local_path": None, "remote_url": None},
            },
            {"product_title": "Linen Top", "product_type": "Top"},
            {
                "product_title": "Summer Dress",
                "product_image": {"local_path": "assets/product_images/x.jpg", "remote_url": "https://cdn.example/x.jpg"},
            },
            {
                "product_title": "Nina Dress",
                "product_image": {"local_path": None, "remote_url": "https://cdn.example/y.jpg"},
            },
            {"product_title": "Skirt", "product_type": "Skirt"},
        ]
        selected = select_ranked_rows(rows, limit=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["product_title"], "Ariana Dress")
        self.assertEqual(selected[1]["product_title"], "Linen Top")


if __name__ == "__main__":
    unittest.main()
