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
                        "top_categories": {
                            "rows": [
                                {
                                    "product_type": "",
                                    "net_sales": 527188.66,
                                    "net_items_sold": 4058,
                                }
                            ]
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
            self.assertIn("| 1 | Uncategorized | $527,188.66 | 4,058 |", output)


if __name__ == "__main__":
    unittest.main()
