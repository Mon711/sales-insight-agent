import unittest

from src.product_reports import (
    _aggregate_dress_variant_rows,
    _normalize_variant_family_title,
    _rank_variant_rows,
    build_annual_all_products_query,
    build_annual_dress_variant_query,
    build_annual_products_query,
    select_ranked_rows,
)


class TestAnnualReports(unittest.TestCase):
    def test_build_annual_products_query_desc(self):
        query = build_annual_products_query(year=2025, limit=20, descending=True)

        self.assertIn("FROM sales", query)
        self.assertIn("SHOW net_sales, net_items_sold, gross_sales, average_order_value", query)
        self.assertIn("returned_quantity_rate", query)
        self.assertIn("WHERE product_variant_title IS NOT NULL", query)
        self.assertIn("GROUP BY product_title WITH TOTALS", query)
        self.assertIn("SINCE 2025-01-01 UNTIL 2025-12-31", query)
        self.assertIn("ORDER BY net_sales DESC", query)
        self.assertIn("LIMIT 20", query)
        self.assertIn("VISUALIZE net_sales TYPE list", query)

    def test_build_annual_products_query_asc(self):
        query = build_annual_products_query(year=2025, descending=False)
        self.assertIn("ORDER BY net_sales ASC", query)
        self.assertIn("VISUALIZE net_sales TYPE list", query)

    def test_build_annual_all_products_query(self):
        query = build_annual_all_products_query(year=2025)
        self.assertIn("SHOW net_items_sold, net_sales", query)
        self.assertIn("GROUP BY product_title WITH TOTALS", query)
        self.assertIn("ORDER BY net_items_sold DESC", query)
        self.assertIn("VISUALIZE net_items_sold", query)

    def test_build_annual_dress_variant_query(self):
        query = build_annual_dress_variant_query(year=2025)
        self.assertIn("FROM sales", query)
        self.assertIn("product_variant_title_at_time_of_sale IS NOT NULL", query)
        self.assertIn("product_title CONTAINS 'Dress'", query)
        self.assertIn("GROUP BY product_id, product_title, product_variant_title WITH TOTALS", query)
        self.assertIn("SINCE 2025-01-01 UNTIL 2025-12-31", query)
        self.assertIn("ORDER BY net_sales DESC", query)
        self.assertIn("VISUALIZE net_sales", query)
        self.assertNotIn("LIMIT", query)

    def test_normalize_variant_family_title_strips_size_segments(self):
        self.assertEqual(_normalize_variant_family_title("Small / Soft Butter Yellow"), "Soft Butter Yellow")
        self.assertEqual(_normalize_variant_family_title("White with Painted Beads / Small"), "White with Painted Beads")
        self.assertEqual(_normalize_variant_family_title("X-Small / French Blue"), "French Blue")

    def test_select_ranked_rows(self):
        rows = [
            {
                "product_title": "Ariana Dress",
                "product_image": {"local_path": None, "remote_url": None},
            },
            {"product_title": "Linen Top", "product_type": "Top"},
            {
                "product_title": "Summer Dress",
                "product_image": {"local_path": "report_assets/product_images/x.jpg", "remote_url": "https://cdn.example/x.jpg"},
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

    def test_aggregate_dress_variant_rows_combines_sizes(self):
        rows = [
            {
                "product_title": "Daisy Dress",
                "product_id": "gid://shopify/Product/101",
                "product_variant_title": "Small / Soft Butter Yellow",
                "net_sales": 6607.4,
                "net_items_sold": 22,
                "gross_sales": 13123.6,
                "average_order_value": 364.644,
                "returns": -3238,
            },
            {
                "product_title": "Daisy Dress",
                "product_id": "gid://shopify/Product/101",
                "product_variant_title": "X-Small / Soft Butter Yellow",
                "net_sales": 3579.2,
                "net_items_sold": 13,
                "gross_sales": 6306,
                "average_order_value": 296.228,
                "returns": -568,
            },
            {
                "product_title": "Daisy Dress",
                "product_id": "gid://shopify/Product/101",
                "product_variant_title": "Medium / Soft Butter Yellow",
                "net_sales": 3127.1,
                "net_items_sold": 12,
                "gross_sales": 6880.2,
                "average_order_value": 345.078,
                "returns": -1704,
            },
            {
                "product_title": "Daisy Dress",
                "product_id": "gid://shopify/Product/102",
                "product_variant_title": "Small / French Blue",
                "net_sales": 5934.56,
                "net_items_sold": 23,
                "gross_sales": 13022.56,
                "average_order_value": 275.606,
                "returns": -1231.2,
            },
        ]

        grouped = _aggregate_dress_variant_rows(rows)

        self.assertEqual(len(grouped), 2)
        self.assertEqual(grouped[0]["product_variant_family"], "Soft Butter Yellow")
        self.assertEqual(grouped[0]["net_sales"], 13313.7)
        self.assertEqual(grouped[0]["net_items_sold"], 47)
        self.assertEqual(grouped[0]["gross_sales"], 26309.8)
        self.assertEqual(grouped[0]["returns"], -5510.0)
        self.assertAlmostEqual(grouped[0]["average_order_value"], 340.72, places=2)
        self.assertEqual(grouped[0]["product_id"], "gid://shopify/Product/101")
        self.assertEqual(grouped[1]["product_variant_family"], "French Blue")

    def test_rank_variant_rows_returns_top_and_bottom(self):
        rows = [
            {"product_title": "Daisy Dress", "product_variant_family": f"Variant {idx}", "net_sales": float(1000 - idx * 10)}
            for idx in range(30)
        ]

        top_rows, bottom_rows = _rank_variant_rows(rows, limit=20)

        self.assertEqual(len(top_rows), 20)
        self.assertEqual(len(bottom_rows), 20)
        self.assertEqual(top_rows[0]["product_variant_family"], "Variant 0")
        self.assertEqual(bottom_rows[0]["product_variant_family"], "Variant 29")
        self.assertEqual(bottom_rows[-1]["product_variant_family"], "Variant 10")


if __name__ == "__main__":
    unittest.main()
