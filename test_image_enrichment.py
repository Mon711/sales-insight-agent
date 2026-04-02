#!/usr/bin/env python3
"""
Unit tests for product image enrichment helpers.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from src.image_enrichment import enrich_channel_product_rows


class FakeClient:
    def __init__(self, records_by_id: Dict[str, Dict[str, Any]], records_by_title: Dict[str, List[Dict[str, Any]]]):
        self.records_by_id = records_by_id
        self.records_by_title = records_by_title

    def to_product_gid(self, raw_product_id: Any):
        if raw_product_id is None:
            return None
        value = str(raw_product_id).strip()
        if not value:
            return None
        if value.startswith("gid://shopify/Product/"):
            return value
        if value.isdigit():
            return f"gid://shopify/Product/{value}"
        return None

    def fetch_product_image_records_by_ids(self, product_gids):
        return {gid: self.records_by_id[gid] for gid in product_gids if gid in self.records_by_id}

    def find_product_image_records_by_exact_title(self, title: str):
        return self.records_by_title.get(title, [])


def successful_downloader(url: str, target_path: Path):
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(b"fake-image-bytes")
    return True, None


def failing_downloader(url: str, target_path: Path):
    return False, "network timeout"


class TestImageEnrichment(unittest.TestCase):
    def test_matches_by_product_id_and_downloads_image(self):
        rows = [
            {
                "product_title": "Ariana Dress",
                "product_type": "Dress",
                "product_id": "101",
                "true_net_sales": 1200.0,
            }
        ]
        gid = "gid://shopify/Product/101"
        client = FakeClient(
            records_by_id={
                gid: {
                    "id": gid,
                    "title": "Ariana Dress",
                    "handle": "ariana-dress",
                    "primary_image": {
                        "url": "https://cdn.example.com/ariana.jpg",
                        "width": 900,
                        "height": 1200,
                        "alt_text": "Ariana Dress photo",
                    },
                }
            },
            records_by_title={},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, index_rows = enrich_channel_product_rows(
                client=client,
                channel_key="online_store",
                product_rows=rows,
                generation_dir=temp_dir,
                top_limit=100,
                downloader=successful_downloader,
            )

            self.assertEqual(summary["matched_by_id_rows"], 1)
            self.assertEqual(summary["enriched_rows"], 1)
            self.assertEqual(index_rows[0]["status"], "enriched")
            image_meta = rows[0]["product_image"]
            self.assertEqual(image_meta["status"], "enriched")
            self.assertEqual(image_meta["match_method"], "product_id")
            self.assertTrue(image_meta["local_path"])
            self.assertTrue(Path(temp_dir, image_meta["local_path"]).exists())

    def test_marks_ambiguous_when_title_has_multiple_matches(self):
        rows = [
            {"product_title": "Nina Pant", "product_type": "Pant", "true_net_sales": 500.0}
        ]
        client = FakeClient(
            records_by_id={},
            records_by_title={
                "Nina Pant": [
                    {"id": "gid://shopify/Product/1", "title": "Nina Pant", "handle": "nina-pant", "primary_image": None},
                    {"id": "gid://shopify/Product/2", "title": "Nina Pant", "handle": "nina-pant-alt", "primary_image": None},
                ]
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, _ = enrich_channel_product_rows(
                client=client,
                channel_key="online_store",
                product_rows=rows,
                generation_dir=temp_dir,
                top_limit=100,
                downloader=successful_downloader,
            )

            self.assertEqual(summary["ambiguous_rows"], 1)
            self.assertEqual(rows[0]["product_image"]["status"], "ambiguous")

    def test_applies_top_limit_and_skips_lower_ranked_rows(self):
        rows = [
            {"product_title": "Top Product", "true_net_sales": 1000.0},
            {"product_title": "Lower Product", "true_net_sales": 100.0},
        ]
        client = FakeClient(
            records_by_id={},
            records_by_title={
                "Top Product": [
                    {
                        "id": "gid://shopify/Product/7",
                        "title": "Top Product",
                        "handle": "top-product",
                        "primary_image": {"url": "https://cdn.example.com/top.jpg"},
                    }
                ]
            },
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, _ = enrich_channel_product_rows(
                client=client,
                channel_key="online_store",
                product_rows=rows,
                generation_dir=temp_dir,
                top_limit=1,
                downloader=successful_downloader,
            )

            self.assertEqual(summary["attempted_rows"], 1)
            self.assertEqual(summary["skipped_rows"], 1)
            self.assertEqual(rows[0]["product_image"]["status"], "enriched")
            self.assertEqual(rows[1]["product_image"]["status"], "skipped_limit")

    def test_keeps_metadata_when_download_fails(self):
        rows = [
            {"product_title": "Eliza Dress", "product_id": "303", "true_net_sales": 300.0}
        ]
        gid = "gid://shopify/Product/303"
        client = FakeClient(
            records_by_id={
                gid: {
                    "id": gid,
                    "title": "Eliza Dress",
                    "handle": "eliza-dress",
                    "primary_image": {"url": "https://cdn.example.com/eliza.jpg"},
                }
            },
            records_by_title={},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            summary, _ = enrich_channel_product_rows(
                client=client,
                channel_key="online_store",
                product_rows=rows,
                generation_dir=temp_dir,
                top_limit=100,
                downloader=failing_downloader,
            )

            self.assertEqual(summary["metadata_only_rows"], 1)
            self.assertEqual(rows[0]["product_image"]["status"], "metadata_only")
            self.assertIsNone(rows[0]["product_image"]["local_path"])


if __name__ == "__main__":
    unittest.main()
