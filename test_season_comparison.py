import base64
import importlib.util
import tempfile
import unittest
from pathlib import Path

from pypdf import PdfReader


MERGE_MODULE_PATH = Path(__file__).resolve().parent / "scripts" / "merge_season_reports.py"
MERGE_SPEC = importlib.util.spec_from_file_location("merge_season_reports", MERGE_MODULE_PATH)
merge_season_reports = importlib.util.module_from_spec(MERGE_SPEC)
assert MERGE_SPEC.loader is not None
MERGE_SPEC.loader.exec_module(merge_season_reports)

PACKAGE_MODULE_PATH = Path(__file__).resolve().parent / "scripts" / "package_marketing_report.py"
PACKAGE_SPEC = importlib.util.spec_from_file_location("package_marketing_report", PACKAGE_MODULE_PATH)
package_marketing_report = importlib.util.module_from_spec(PACKAGE_SPEC)
assert PACKAGE_SPEC.loader is not None
PACKAGE_SPEC.loader.exec_module(package_marketing_report)


SMALL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO3+e9kAAAAASUVORK5CYII="
)


class TestSeasonComparison(unittest.TestCase):
    def test_merge_season_reports_builds_combined_payload(self):
        season_a = {
            "season": {
                "slug": "winter25",
                "display_name": "Winter'25",
                "shopify_tag": "Winter25",
            },
            "report_period": {"since": "2024-12-01", "until": "2026-04-30"},
            "season_product_performance": {
                "rows": [
                    {
                        "product_title": "Ariana Dress",
                        "net_sales": 100.0,
                        "gross_sales": 150.0,
                        "returns": -10.0,
                        "net_items_sold": 4,
                        "returned_quantity_rate": 0.1,
                    },
                    {
                        "product_title": "Bea Top",
                        "net_sales": 50.0,
                        "gross_sales": 80.0,
                        "returns": -5.0,
                        "net_items_sold": 2,
                        "returned_quantity_rate": 0.05,
                    },
                ]
            },
        }
        season_b = {
            "season": {
                "slug": "winter26",
                "display_name": "Winter'26",
                "shopify_tag": "Winter26",
            },
            "report_period": {"since": "2024-12-01", "until": "2026-04-30"},
            "season_product_performance": {
                "rows": [
                    {
                        "product_title": "Ariana Dress",
                        "net_sales": 130.0,
                        "gross_sales": 180.0,
                        "returns": -8.0,
                        "net_items_sold": 5,
                        "returned_quantity_rate": 0.08,
                    },
                    {
                        "product_title": "Bea Top",
                        "net_sales": 40.0,
                        "gross_sales": 70.0,
                        "returns": -4.0,
                        "net_items_sold": 1,
                        "returned_quantity_rate": 0.04,
                    },
                ]
            },
        }

        payload = merge_season_reports.build_comparison_payload(
            brand_slug="steele",
            brand_display_name="Steele",
            family_slug="winter",
            family_display_name="Winter",
            season_a=season_a,
            season_b=season_b,
        )

        self.assertEqual(payload["report_type"], "season_family_comparison")
        self.assertEqual(payload["comparison"]["season_slugs"], ["winter25", "winter26"])
        self.assertEqual(payload["comparison"]["family_slug"], "winter")
        self.assertIn("winter25", payload["seasons"])
        self.assertIn("winter26", payload["seasons"])
        self.assertEqual(payload["comparison_summary"]["winter25"]["product_count"], 2)
        self.assertEqual(payload["comparison_summary"]["winter26"]["net_sales_total"], 170.0)
        self.assertEqual(payload["comparison_summary"]["delta"]["net_sales_total"], 20.0)
        self.assertEqual(payload["comparison_summary"]["delta"]["product_count"], 0)

    def test_package_marketing_report_renders_html_figures(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            markdown_path = temp_path / "report.md"
            reports_dir = temp_path / "report_source"
            output_dir = temp_path / "output"
            asset_path = reports_dir / "assets" / "product_images" / "steele_winter25" / "ariana.png"
            asset_path.parent.mkdir(parents=True, exist_ok=True)
            asset_path.write_bytes(SMALL_PNG)
            output_dir.mkdir(parents=True, exist_ok=True)

            markdown_path.write_text(
                "\n".join(
                    [
                        "# Executive Summary",
                        "",
                        "<figure class=\"product-figure\">",
                        f"<img src=\"report_assets/product_images/steele_winter25/ariana.png\" alt=\"Ariana Dress\" width=\"240\" />",
                        "<figcaption>Ariana Dress is the clearest hero of the winter edit.</figcaption>",
                        "</figure>",
                        "",
                        "Closing note.",
                    ]
                ),
                encoding="utf-8",
            )

            package_marketing_report._copy_reports_assets_tree(reports_dir, output_dir)
            copied_count, rewritten_count, _ = package_marketing_report.bundle_markdown_assets(
                markdown_path,
                reports_dir,
                output_dir,
            )
            self.assertGreaterEqual(copied_count, 1)
            self.assertGreaterEqual(rewritten_count, 1)

            updated_markdown = markdown_path.read_text(encoding="utf-8")
            self.assertIn("report_assets/product_images/steele_winter25/ariana.png", updated_markdown)

            pdf_path = output_dir / "report.pdf"
            package_marketing_report.export_pdf(markdown_path, pdf_path)

            reader = PdfReader(str(pdf_path))
            self.assertGreaterEqual(len(reader.pages), 1)
            self.assertTrue(any(len(page.images) > 0 for page in reader.pages))
            extracted_text = "\n".join(page.extract_text() or "" for page in reader.pages)
            self.assertIn("Ariana Dress is the clearest hero of the winter edit.", extracted_text)


if __name__ == "__main__":
    unittest.main()
