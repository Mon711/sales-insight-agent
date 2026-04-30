import unittest

from src.season_profiles import normalize_season_slug, resolve_season_profile
from src.season_reports import build_season_products_query, run_season_report


class FakeSeasonClient:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def probe_shopifyql_product_id_support(self, since, until):
        self.probe_args = (since, until)
        return True

    def run_shopifyql_report(self, query):
        self.queries.append(query)
        return {
            "parseErrors": [],
            "tableData": {
                "rows": [dict(row) for row in self.rows],
            },
        }

    def check_read_products_access(self):
        return True, None


class TestSeasonReports(unittest.TestCase):
    def test_normalize_season_slug(self):
        self.assertEqual(normalize_season_slug("Winter'25"), "winter25")
        self.assertEqual(normalize_season_slug("Winter 25"), "winter25")
        self.assertEqual(normalize_season_slug("/Resort'24"), "resort24")

    def test_resolve_season_profile(self):
        profile = resolve_season_profile("Winter'25")
        self.assertEqual(profile.slug, "winter25")
        self.assertEqual(profile.display_name, "Winter'25")
        self.assertEqual(profile.shopify_tag, "Winter25")

    def test_build_season_products_query(self):
        profile = resolve_season_profile("Winter'25")
        query = build_season_products_query(season_profile=profile)

        self.assertIn("FROM sales", query)
        self.assertIn("SHOW net_sales, gross_sales, net_items_sold, returns", query)
        self.assertIn("returned_quantity_rate", query)
        self.assertIn("discounts", query)
        self.assertIn("product_title", query)
        self.assertIn("product_variant_sku", query)
        self.assertIn("product_type", query)
        self.assertIn("product_id", query)
        self.assertIn("WHERE product_tags CONTAINS 'Winter25'", query)
        self.assertIn("GROUP BY product_title, product_variant_sku, product_type, product_id WITH TOTALS", query)
        self.assertIn("SINCE 2024-12-01 UNTIL 2026-04-30", query)
        self.assertIn("ORDER BY net_sales DESC", query)

    def test_run_season_report_uses_all_rows_and_image_enrichment(self):
        rows = [
            {
                "product_title": "Arden Dress",
                "product_variant_sku": "ARD-WIN-001",
                "product_type": "Dress",
                "product_id": "101",
                "net_sales": 2000.0,
                "gross_sales": 3200.0,
                "net_items_sold": 10,
                "returns": -100.0,
                "returned_quantity_rate": 0.1,
                "discounts": 50.0,
            },
            {
                "product_title": "Mila Shirt",
                "product_variant_sku": "MIL-WIN-002",
                "product_type": "Top",
                "product_id": "102",
                "net_sales": 1000.0,
                "gross_sales": 1500.0,
                "net_items_sold": 5,
                "returns": -25.0,
                "returned_quantity_rate": 0.05,
                "discounts": 10.0,
            },
        ]
        client = FakeSeasonClient(rows)

        def fake_image_enrichment_fn(*, client, channel_key, product_rows, generation_dir, top_limit):
            self.assertEqual(channel_key, "steele_winter25")
            self.assertEqual(top_limit, 2)
            for row in product_rows:
                row["product_image"] = {
                    "status": "enriched",
                    "local_path": f"report_assets/product_images/{channel_key}/{row['product_title'].lower().replace(' ', '_')}.jpg",
                }
            return (
                {
                    "enabled": True,
                    "attempted_rows": len(product_rows),
                    "enriched_rows": len(product_rows),
                    "metadata_only_rows": 0,
                    "not_found_rows": 0,
                    "ambiguous_rows": 0,
                    "no_image_rows": 0,
                    "skipped_rows": 0,
                    "matched_by_id_rows": len(product_rows),
                    "matched_by_title_rows": 0,
                    "reason": None,
                },
                [
                    {
                        "channel_name": channel_key,
                        "product_title": row["product_title"],
                        "local_path": row["product_image"]["local_path"],
                    }
                    for row in product_rows
                ],
            )

        result = run_season_report(
            client=client,
            brand_slug="steele",
            season_profile=resolve_season_profile("Winter'25"),
            report_output_dir="/tmp/steele_winter25_test_output",
            image_enrichment_fn=fake_image_enrichment_fn,
            image_skip_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("skip fn should not be used")),
        )

        self.assertEqual(result["product_count"], 2)
        self.assertEqual(result["season"]["slug"], "winter25")
        self.assertEqual(result["queries"]["season_products"].count("product_tags CONTAINS 'Winter25'"), 1)
        self.assertEqual(result["season_product_performance"]["rows"][0]["product_title"], "Arden Dress")
        self.assertEqual(result["season_product_performance"]["top_20_rows"][0]["product_title"], "Arden Dress")
        self.assertEqual(result["season_product_performance"]["bottom_20_rows"][0]["product_title"], "Mila Shirt")
        self.assertEqual(len(result["product_image_index"]), 2)
        self.assertEqual(result["product_image_focus"]["top_10_products"][0]["product_title"], "Arden Dress")


if __name__ == "__main__":
    unittest.main()
