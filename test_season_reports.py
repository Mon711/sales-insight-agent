import unittest

from src.season_profiles import normalize_season_slug, resolve_season_profile
from src.season_reports import build_season_products_query, run_season_report
from src.shopify_client import ShopifyGraphQLClient, shopify_rich_text_to_plain_text


class FakeSeasonClient:
    def __init__(self, rows, product_detail_records=None, product_detail_error=None):
        self.rows = rows
        self.queries = []
        self.product_detail_records = product_detail_records or {}
        self.product_detail_error = product_detail_error

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

    def to_product_gid(self, raw_product_id):
        return ShopifyGraphQLClient.to_product_gid(raw_product_id)

    def fetch_product_detail_records_by_ids(self, product_gids, batch_size=25):
        self.product_detail_args = (list(product_gids), batch_size)
        if self.product_detail_error:
            raise self.product_detail_error
        return {
            gid: self.product_detail_records[gid]
            for gid in product_gids
            if gid in self.product_detail_records
        }


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
        self.assertIn("product_detail_enrichment_summary", result)

    def test_product_detail_normalization_parses_official_fields(self):
        rich_text = (
            '{"type":"root","children":[{"type":"paragraph","children":['
            '{"type":"text","value":"Shell: 55% Linen, 45% Cotton"}]}]}'
        )
        node = {
            "__typename": "Product",
            "id": "gid://shopify/Product/101",
            "title": "Arden Dress",
            "descriptionHtml": "<p>Care: Dry clean only.</p>",
            "handle": "arden-dress",
            "productType": "Dress",
            "vendor": "Steele",
            "tags": ["Winter25"],
            "status": "ACTIVE",
            "options": [
                {"id": "opt1", "name": "Color", "position": 1, "values": ["Ivory"]},
                {"id": "opt2", "name": "Size", "position": 2, "values": ["S"]},
            ],
            "collections": {"edges": [{"node": {"id": "col1", "title": "Winter"}}]},
            "media": {"edges": [{"node": {"id": "m1", "image": {"url": "https://cdn.example/a.jpg", "altText": "A", "width": 1000, "height": 1200}}}]},
            "fabric": {
                "value": "[gid://shopify/Metaobject/1]",
                "references": {
                    "nodes": [
                        {
                            "displayName": "Linen Cotton",
                            "fields": [{"key": "name", "value": "Linen Cotton"}],
                        }
                    ]
                },
            },
            "colorPattern": {
                "value": "[gid://shopify/Metaobject/2]",
                "references": {"nodes": [{"displayName": "Ivory", "fields": []}]},
            },
            "fit": {
                "value": "[gid://shopify/Metaobject/3]",
                "references": {"nodes": [{"displayName": "Relaxed", "fields": []}]},
            },
            "neckline": None,
            "sleeveLengthType": None,
            "clothingFeatures": None,
            "materials": {"value": rich_text, "type": "rich_text_field"},
            "productSize": {"value": '{"type":"root","children":[{"type":"paragraph","children":[{"type":"text","value":"Midi length"}]}]}', "type": "rich_text_field"},
            "productFeatures": {"value": '{"type":"root","children":[{"type":"paragraph","children":[{"type":"text","value":"Button front"}]}]}', "type": "rich_text_field"},
            "originCountry": {"value": "India"},
            "siblings": None,
            "siblingColor": None,
            "collectionName": {"value": "gid://shopify/Metaobject/4", "reference": {"displayName": "Winter Capsule", "fields": []}},
            "variants": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/ProductVariant/201",
                            "title": "Ivory / S",
                            "sku": "ARD-IV-S",
                            "price": "298.00",
                            "compareAtPrice": None,
                            "barcode": "123",
                            "availableForSale": True,
                            "inventoryQuantity": 3,
                            "selectedOptions": [
                                {"name": "Color", "value": "Ivory"},
                                {"name": "Size", "value": "S"},
                            ],
                            "image": {"url": "https://cdn.example/v.jpg", "altText": "Variant"},
                        }
                    }
                ]
            },
        }

        record = ShopifyGraphQLClient._normalize_product_detail_record(node)

        self.assertEqual(record["description_text"], "Care: Dry clean only.")
        self.assertEqual(record["metafields_normalized"]["materials"]["text"], "Shell: 55% Linen, 45% Cotton")
        attrs = record["official_product_attributes"]
        self.assertEqual(attrs["official_fabric_composition"], "Shell: 55% Linen, 45% Cotton")
        self.assertEqual(attrs["official_fabric_source"], "custom.materials")
        self.assertEqual(attrs["official_colour"], "Ivory")
        self.assertEqual(attrs["official_fit"], "Relaxed")
        self.assertEqual(attrs["official_collection_name"], "Winter Capsule")
        self.assertEqual(record["variants"][0]["colour"], "Ivory")
        self.assertEqual(record["variants"][0]["size"], "S")

    def test_missing_fabric_composition_is_not_invented(self):
        node = {
            "__typename": "Product",
            "id": "gid://shopify/Product/101",
            "title": "Arden Dress",
            "descriptionHtml": "<p>Soft cotton handfeel.</p>",
            "variants": {"edges": []},
            "materials": {
                "value": '{"type":"root","children":[{"type":"paragraph","children":[{"type":"text","value":"Cotton blend"}]}]}',
                "type": "rich_text_field",
            },
            "fabric": {"value": "gid://shopify/Metaobject/1", "references": {"nodes": [{"displayName": "Cotton", "fields": []}]}},
        }

        record = ShopifyGraphQLClient._normalize_product_detail_record(node)
        attrs = record["official_product_attributes"]

        self.assertEqual(attrs["official_fabric_composition"], "Unknown")
        self.assertEqual(attrs["official_fabric_confidence"], "none")
        self.assertIn("cotton", attrs["official_fabric_family"])
        self.assertEqual(attrs["official_material_text"], "Cotton blend")

    def test_rich_text_plain_text_parser_handles_shopify_json(self):
        value = (
            '{"type":"root","children":[{"type":"paragraph","children":['
            '{"type":"text","value":"Line one"}]},{"type":"paragraph","children":['
            '{"type":"text","value":"Line two"}]}]}'
        )

        self.assertEqual(shopify_rich_text_to_plain_text(value), "Line one Line two")

    def test_run_season_report_attaches_product_detail_and_variant_options(self):
        rows = [
            {
                "product_title": "Arden Dress",
                "product_variant_sku": "ARD-IV-S",
                "product_type": "Dress",
                "product_id": "101",
                "net_sales": 2000.0,
                "gross_sales": 3200.0,
                "net_items_sold": 10,
                "returns": -100.0,
                "returned_quantity_rate": 0.1,
                "discounts": 50.0,
            }
        ]
        gid = "gid://shopify/Product/101"
        product_detail = {
            "id": gid,
            "title": "Arden Dress",
            "handle": "arden-dress",
            "description_text": "Official description",
            "tags": ["Winter25"],
            "product_type": "Dress",
            "vendor": "Steele",
            "options": [],
            "collections": [],
            "variants": [
                {
                    "id": "gid://shopify/ProductVariant/201",
                    "sku": "ARD-IV-S",
                    "selected_options": {"Color": "Ivory", "Size": "S"},
                }
            ],
            "selected_option_values": {"Color": ["Ivory"], "Size": ["S"]},
            "metafields_normalized": {},
            "official_product_attributes": {
                "official_fabric_composition": "100% Cotton",
                "official_material_text": "100% Cotton",
                "official_colour": "Ivory",
                "official_fit": "Relaxed",
            },
        }
        client = FakeSeasonClient(rows, product_detail_records={gid: product_detail})

        result = run_season_report(
            client=client,
            brand_slug="steele",
            season_profile=resolve_season_profile("Winter'25"),
            report_output_dir="/tmp/steele_winter25_test_output",
            image_enrichment_fn=lambda **kwargs: ({"enabled": True}, []),
            image_skip_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("skip fn should not be used")),
        )

        detail = result["season_product_performance"]["rows"][0]["product_detail"]
        self.assertEqual(detail["official_product_attributes"]["official_fabric_composition"], "100% Cotton")
        self.assertEqual(detail["selected_option_values"], {"Color": "Ivory", "Size": "S"})
        summary = result["product_detail_enrichment_summary"]
        self.assertEqual(summary["product_ids_seen"], 1)
        self.assertEqual(summary["product_details_found"], 1)
        self.assertEqual(summary["official_fabric_compositions_found"], 1)

    def test_rows_without_product_ids_do_not_crash_product_detail_enrichment(self):
        rows = [
            {
                "product_title": "Mystery Dress",
                "product_variant_sku": "MYS-S",
                "product_type": "Dress",
                "net_sales": 100.0,
            }
        ]
        client = FakeSeasonClient(rows)

        result = run_season_report(
            client=client,
            brand_slug="steele",
            season_profile=resolve_season_profile("Winter'25"),
            report_output_dir="/tmp/steele_winter25_test_output",
            image_enrichment_fn=lambda **kwargs: ({"enabled": True}, []),
            image_skip_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("skip fn should not be used")),
        )

        self.assertIsNone(result["season_product_performance"]["rows"][0]["product_detail"])
        self.assertEqual(result["product_detail_enrichment_summary"]["product_ids_seen"], 0)

    def test_product_detail_enrichment_failure_does_not_break_report(self):
        rows = [
            {
                "product_title": "Arden Dress",
                "product_variant_sku": "ARD-IV-S",
                "product_type": "Dress",
                "product_id": "101",
                "net_sales": 2000.0,
            }
        ]
        client = FakeSeasonClient(rows, product_detail_error=RuntimeError("metafield field unavailable"))

        result = run_season_report(
            client=client,
            brand_slug="steele",
            season_profile=resolve_season_profile("Winter'25"),
            report_output_dir="/tmp/steele_winter25_test_output",
            image_enrichment_fn=lambda **kwargs: ({"enabled": True}, []),
            image_skip_fn=lambda **kwargs: (_ for _ in ()).throw(AssertionError("skip fn should not be used")),
        )

        self.assertEqual(result["product_count"], 1)
        self.assertIsNone(result["season_product_performance"]["rows"][0]["product_detail"])
        self.assertFalse(result["product_detail_enrichment_summary"]["metafield_access_ok"])
        self.assertIn("Product detail enrichment failed", result["product_detail_enrichment_summary"]["errors"][0])


if __name__ == "__main__":
    unittest.main()
