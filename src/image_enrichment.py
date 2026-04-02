"""
Product image enrichment helpers for sales report rows.

This module augments product report rows with:
- product matching metadata
- remote Shopify image URL metadata
- local downloaded image file paths for AI consumption
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import requests


TOP_PRODUCTS_IMAGE_LIMIT = 20
IMAGE_DOWNLOAD_TIMEOUT_SECONDS = 20
MAX_IMAGE_BYTES = 8 * 1024 * 1024

ImageDownloader = Callable[[str, Path], Tuple[bool, Optional[str]]]


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sales_score(row: Dict[str, Any], channel_key: str) -> float:
    if channel_key == "wholesale":
        return _to_float(
            row.get("estimated_net_sales")
            or row.get("gross_sales")
            or row.get("total_sales")
        )

    return _to_float(
        row.get("true_net_sales")
        or row.get("net_sales")
        or row.get("total_sales")
    )


def _slugify(value: str, fallback: str) -> str:
    candidate = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return candidate or fallback


def _image_extension_from_url(url: str) -> str:
    path = urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"]:
        if path.endswith(ext):
            return ext
    return ".jpg"


def _base_product_image_payload(status: str, message: str) -> Dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "match_method": None,
        "match_confidence": 0.0,
        "product_gid": None,
        "product_handle": None,
        "remote_url": None,
        "local_path": None,
        "width": None,
        "height": None,
        "alt_text": None,
    }


def _download_image_default(image_url: str, target_path: Path) -> Tuple[bool, Optional[str]]:
    response = None
    try:
        response = requests.get(image_url, stream=True, timeout=IMAGE_DOWNLOAD_TIMEOUT_SECONDS)
        response.raise_for_status()

        content_type = (response.headers.get("Content-Type") or "").lower()
        if content_type and not content_type.startswith("image/"):
            return False, f"Unexpected content type: {content_type}"

        total_bytes = 0
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as file_obj:
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                total_bytes += len(chunk)
                if total_bytes > MAX_IMAGE_BYTES:
                    if target_path.exists():
                        target_path.unlink()
                    return False, f"Image exceeds max size ({MAX_IMAGE_BYTES} bytes)"
                file_obj.write(chunk)

        return True, None
    except requests.RequestException as e:
        if target_path.exists():
            target_path.unlink()
        return False, str(e)
    finally:
        if response is not None:
            response.close()


def mark_channel_image_enrichment_skipped(
    product_rows: List[Dict[str, Any]],
    reason: str,
    top_limit: int = TOP_PRODUCTS_IMAGE_LIMIT,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Attach a skipped image payload to all rows in a channel and return summary/index.
    """
    index_entries: List[Dict[str, Any]] = []
    for row in product_rows:
        row["product_image"] = _base_product_image_payload(
            status="skipped",
            message=reason,
        )

    summary = {
        "enabled": False,
        "top_limit": top_limit,
        "total_rows": len(product_rows),
        "attempted_rows": 0,
        "enriched_rows": 0,
        "metadata_only_rows": 0,
        "not_found_rows": 0,
        "ambiguous_rows": 0,
        "no_image_rows": 0,
        "skipped_rows": len(product_rows),
        "matched_by_id_rows": 0,
        "matched_by_title_rows": 0,
        "reason": reason,
    }
    return summary, index_entries


def enrich_channel_product_rows(
    *,
    client: Any,
    channel_key: str,
    product_rows: List[Dict[str, Any]],
    generation_dir: str,
    top_limit: int = TOP_PRODUCTS_IMAGE_LIMIT,
    downloader: Optional[ImageDownloader] = None,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Enrich product rows with image metadata and one local image per selected product.
    """
    download = downloader or _download_image_default
    gen_path = Path(generation_dir).resolve()
    image_dir = gen_path / "assets" / "product_images" / channel_key
    image_dir.mkdir(parents=True, exist_ok=True)

    indexed_rows = list(enumerate(product_rows))
    ranked_rows = sorted(
        indexed_rows,
        key=lambda item: _sales_score(item[1], channel_key),
        reverse=True,
    )
    selected = ranked_rows[: max(0, top_limit)]
    selected_indexes = {idx for idx, _ in selected}

    for idx, row in indexed_rows:
        if idx in selected_indexes:
            row["product_image"] = _base_product_image_payload(
                status="pending",
                message="Image enrichment pending.",
            )
        else:
            row["product_image"] = _base_product_image_payload(
                status="skipped_limit",
                message=f"Outside top {top_limit} products for image enrichment.",
            )

    summary = {
        "enabled": True,
        "top_limit": top_limit,
        "total_rows": len(product_rows),
        "attempted_rows": len(selected),
        "enriched_rows": 0,
        "metadata_only_rows": 0,
        "not_found_rows": 0,
        "ambiguous_rows": 0,
        "no_image_rows": 0,
        "skipped_rows": max(0, len(product_rows) - len(selected)),
        "matched_by_id_rows": 0,
        "matched_by_title_rows": 0,
        "reason": None,
    }
    index_entries: List[Dict[str, Any]] = []

    def apply_match(
        row_index: int,
        record: Dict[str, Any],
        *,
        match_method: str,
        match_confidence: float,
    ) -> None:
        row = product_rows[row_index]
        image_payload = row["product_image"]

        image_payload["match_method"] = match_method
        image_payload["match_confidence"] = round(match_confidence, 2)
        image_payload["product_gid"] = record.get("id")
        image_payload["product_handle"] = record.get("handle")

        primary_image = record.get("primary_image") or {}
        remote_url = primary_image.get("url")
        image_payload["remote_url"] = remote_url
        image_payload["width"] = primary_image.get("width")
        image_payload["height"] = primary_image.get("height")
        image_payload["alt_text"] = primary_image.get("alt_text")

        if not remote_url:
            image_payload["status"] = "no_image"
            image_payload["message"] = "Matched product has no image media."
            summary["no_image_rows"] += 1
            return

        product_slug = _slugify(row.get("product_title", ""), "product")
        gid_suffix = (record.get("id", "").split("/")[-1] or "unknown")[-12:]
        extension = _image_extension_from_url(remote_url)
        filename = f"{product_slug}_{gid_suffix}{extension}"
        target_path = image_dir / filename

        downloaded, error = download(remote_url, target_path)
        if downloaded:
            rel_path = os.path.relpath(target_path, gen_path)
            image_payload["status"] = "enriched"
            image_payload["message"] = "Image downloaded successfully."
            image_payload["local_path"] = rel_path
            summary["enriched_rows"] += 1
        else:
            image_payload["status"] = "metadata_only"
            image_payload["message"] = f"Image URL found but download failed: {error}"
            summary["metadata_only_rows"] += 1

    # First pass: match by product_id when present.
    gid_to_indexes: Dict[str, List[int]] = {}
    for row_index, row in selected:
        product_gid = client.to_product_gid(row.get("product_id"))
        if product_gid:
            gid_to_indexes.setdefault(product_gid, []).append(row_index)

    id_records: Dict[str, Dict[str, Any]] = {}
    if gid_to_indexes:
        try:
            id_records = client.fetch_product_image_records_by_ids(list(gid_to_indexes.keys()))
        except Exception as e:
            reason = f"Image enrichment disabled due product API error: {e}"
            return mark_channel_image_enrichment_skipped(product_rows, reason=reason, top_limit=top_limit)

    resolved_indexes = set()
    for gid, row_indexes in gid_to_indexes.items():
        record = id_records.get(gid)
        if not record:
            continue
        for row_index in row_indexes:
            apply_match(row_index, record, match_method="product_id", match_confidence=1.0)
            summary["matched_by_id_rows"] += 1
            resolved_indexes.add(row_index)

    # Second pass: title fallback for unresolved rows.
    title_cache: Dict[str, List[Dict[str, Any]]] = {}
    for row_index, row in selected:
        if row_index in resolved_indexes:
            continue

        title = (row.get("product_title") or "").strip()
        image_payload = row["product_image"]

        if not title:
            image_payload["status"] = "not_found"
            image_payload["message"] = "No product title available for fallback match."
            summary["not_found_rows"] += 1
            continue

        if title not in title_cache:
            try:
                title_cache[title] = client.find_product_image_records_by_exact_title(title)
            except Exception as e:
                reason = f"Image enrichment disabled due product API error: {e}"
                return mark_channel_image_enrichment_skipped(product_rows, reason=reason, top_limit=top_limit)

        matches = title_cache[title]
        if len(matches) == 1:
            apply_match(
                row_index,
                matches[0],
                match_method="title_exact",
                match_confidence=0.8,
            )
            summary["matched_by_title_rows"] += 1
        elif len(matches) > 1:
            image_payload["status"] = "ambiguous"
            image_payload["message"] = "Multiple products matched this title."
            image_payload["match_method"] = "title_exact"
            image_payload["match_confidence"] = 0.0
            image_payload["candidate_product_gids"] = [item.get("id") for item in matches]
            summary["ambiguous_rows"] += 1
        else:
            image_payload["status"] = "not_found"
            image_payload["message"] = "No exact product title match found in Product API."
            image_payload["match_method"] = "title_exact"
            image_payload["match_confidence"] = 0.0
            summary["not_found_rows"] += 1

    for row_index, row in selected:
        image_payload = row.get("product_image", {})
        index_entries.append(
            {
                "channel_name": channel_key,
                "product_title": row.get("product_title"),
                "product_type": row.get("product_type"),
                "status": image_payload.get("status"),
                "match_method": image_payload.get("match_method"),
                "match_confidence": image_payload.get("match_confidence"),
                "product_gid": image_payload.get("product_gid"),
                "product_handle": image_payload.get("product_handle"),
                "remote_url": image_payload.get("remote_url"),
                "local_path": image_payload.get("local_path"),
                "message": image_payload.get("message"),
            }
        )

    return summary, index_entries
