import unittest

from src.product_reports import (
    build_annual_categories_query,
    build_annual_products_query,
    select_dress_rows,
)


class TestAnnualReports(unittest.TestCase):
    def test_build_annual_products_query_desc(self):
        query = build_annual_products_query(
            year=2025,
            limit=20,
            descending=True,
            include_product_id=True,
        )

        self.assertIn("FROM sales", query)
        self.assertIn("SHOW product_title, product_variant_price, product_id", query)
        self.assertIn("returned_quantity_rate", query)
        self.assertIn("GROUP BY product_title, product_variant_price, product_id WITH TOTALS", query)
        self.assertIn("SINCE 2025-01-01 UNTIL 2025-12-31", query)
        self.assertIn("ORDER BY net_sales DESC", query)
        self.assertIn("LIMIT 20", query)

    def test_build_annual_products_query_asc(self):
        query = build_annual_products_query(
            year=2025,
            descending=False,
            include_product_id=False,
        )
        self.assertIn("ORDER BY net_sales ASC", query)
        self.assertNotIn("product_id", query.split("GROUP BY")[0])

    def test_build_annual_products_query_without_variant_price(self):
        query = build_annual_products_query(
            year=2025,
            include_product_variant_price=False,
            return_metric="returns",
        )
        self.assertIn("SHOW product_title, net_sales", query)
        self.assertNotIn("product_variant_price", query.split("GROUP BY")[0])
        self.assertIn("returns", query)

    def test_build_annual_categories_query(self):
        query = build_annual_categories_query(year=2025, limit=20)
        self.assertIn("GROUP BY product_type WITH TOTALS", query)
        self.assertIn("SHOW net_sales, net_items_sold", query)
        self.assertIn("ORDER BY net_sales DESC", query)

    def test_select_dress_rows(self):
        rows = [
            {"product_title": "Ariana Dress", "product_type": None},
            {"product_title": "Linen Top", "product_type": "Top"},
            {"product_title": "Nina Pant", "product_type": "Dress"},
            {"product_title": "Skirt", "product_type": "Skirt"},
            {"product_title": "Summer Dress", "product_type": "Dress"},
        ]
        selected = select_dress_rows(rows, limit=2)
        self.assertEqual(len(selected), 2)
        self.assertEqual(selected[0]["product_title"], "Ariana Dress")
        self.assertEqual(selected[1]["product_title"], "Nina Pant")


if __name__ == "__main__":
    unittest.main()
