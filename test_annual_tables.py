import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parent / "scripts" / "ensure_annual_tables.py"
SPEC = importlib.util.spec_from_file_location("ensure_annual_tables", MODULE_PATH)
ensure_annual_tables = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ensure_annual_tables)


class TestEnsureAnnualTables(unittest.TestCase):
    def test_tables_move_after_executive_summary_and_strip_old_images(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markdown_path = temp_path / "ANNUAL_REPORT_2025.md"
            annual_json_path = temp_path / "annual_report_2025.json"

            markdown_path.write_text(
                "\n".join(
                    [
                        "# Executive Summary",
                        "",
                        "Summary paragraph.",
                        "",
                        "![Dress](report_assets/product_images/annual_top_2025/dress.jpg)",
                        "",
                        "# Methodology And Data Window",
                        "",
                        "Methodology paragraph.",
                        "",
                        "# Query Result Tables",
                        "",
                        "| Product | Net Sales |",
                        "| --- | --- |",
                        "| Old row | $1.00 |",
                    ]
                ),
                encoding="utf-8",
            )

            annual_json_path.write_text(
                json.dumps(
                    {
                        "top_performers": {
                            "rows": [
                                {
                                    "product_title": "Ariana Dress",
                                    "product_variant_price": 378,
                                    "net_sales": 8278.2,
                                    "net_items_sold": 77,
                                    "gross_sales": 35154,
                                    "average_order_value": 233.415,
                                    "returned_quantity_rate": 0.17204301075268819,
                                    "product_image": {
                                        "local_path": "report_assets/product_images/annual_top_2025/ariana.jpg",
                                    },
                                }
                            ]
                        },
                        "underperformers": {
                            "rows": [
                                {
                                    "product_title": "Lane Mini Dress",
                                    "product_variant_price": 368,
                                    "net_sales": -736,
                                    "net_items_sold": -2,
                                    "gross_sales": 0,
                                    "average_order_value": None,
                                    "returned_quantity_rate": None,
                                    "product_image": {
                                        "local_path": "report_assets/product_images/annual_under_2025/lane.jpg",
                                    },
                                }
                            ]
                        },
                        "dress_variant_families": {
                            "top_rows": [
                                {
                                    "product_title": "Daisy Dress",
                                    "product_image": {
                                        "local_path": "report_assets/product_images/annual_dress_variant_top_2025/daisy.jpg",
                                    },
                                    "product_variant_family": "Soft Butter Yellow",
                                    "net_sales": 13313.7,
                                    "net_items_sold": 47,
                                    "gross_sales": 26309.8,
                                    "average_order_value": 340.72,
                                    "returns": -5510.0,
                                }
                            ],
                            "bottom_rows": [
                                {
                                    "product_title": "Daisy Dress",
                                    "product_image": {
                                        "local_path": "report_assets/product_images/annual_dress_variant_bottom_2025/daisy.jpg",
                                    },
                                    "product_variant_family": "Black Rose Floral",
                                    "net_sales": -218.9,
                                    "net_items_sold": 3,
                                    "gross_sales": 1771.1,
                                    "average_order_value": 35.82,
                                    "returns": -398.0,
                                }
                            ],
                        },
                    }
                ),
                encoding="utf-8",
            )

            ensure_annual_tables.ensure_tables(markdown_path, annual_json_path)
            output = markdown_path.read_text(encoding="utf-8")

            executive_index = output.index("# Executive Summary")
            tables_index = output.index("# Query Result Tables")
            methodology_index = output.index("# Methodology And Data Window")

            self.assertLess(executive_index, tables_index)
            self.assertLess(tables_index, methodology_index)
            self.assertEqual(output.count("# Query Result Tables"), 1)
            self.assertNotIn("| Old row | $1.00 |", output)
            self.assertNotIn("![Dress](report_assets/product_images/annual_top_2025/dress.jpg)", output)
            self.assertIn("![Ariana Dress](report_assets/product_images/annual_top_2025/ariana.jpg)", output)
            self.assertIn("![Lane Mini Dress](report_assets/product_images/annual_under_2025/lane.jpg)", output)
            self.assertIn("## Top 20 Dress Variant Families", output)
            self.assertIn("## Bottom 20 Dress Variant Families", output)
            self.assertIn("![Daisy Dress](report_assets/product_images/annual_dress_variant_top_2025/daisy.jpg)", output)
            self.assertIn("![Daisy Dress](report_assets/product_images/annual_dress_variant_bottom_2025/daisy.jpg)", output)
            self.assertIn("| ![Daisy Dress](report_assets/product_images/annual_dress_variant_top_2025/daisy.jpg) | 1 | Daisy Dress | Soft Butter Yellow | $13,313.70 | 47 | $26,309.80 | $340.72 | $-5,510.00 |", output)


if __name__ == "__main__":
    unittest.main()
