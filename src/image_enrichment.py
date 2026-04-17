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
MAX_IMAGE_BYTES = 8 * 1024 * 1024  # Guard against accidentally downloading huge files

# Type alias: a function that downloads a URL to a local path and returns (success, error_message).
ImageDownloader = Callable[[str, Path], Tuple[bool, Optional[str]]]


def _to_float(value: Any) -> float:
    """Safely convert any value to float, returning 0.0 on failure."""
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _money_matches(left: Any, right: Any, tolerance: float = 0.01) -> bool:
    """Check if two money values are equal within a small rounding tolerance."""
    left_value = _to_float(left)
    right_value = _to_float(right)
    return abs(left_value - right_value) <= tolerance


def _active_records(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter to only ACTIVE products (archived/draft products excluded)."""
    return [
        record for record in records
        if (record.get("status") or "").strip().upper() == "ACTIVE"
    ]


def _sales_score(row: Dict[str, Any], channel_key: str) -> float:
    """
    Return the best available net sales value for sorting.

    Tries multiple field names to handle both annual and channel report shapes.
    """
    _ = channel_key
    return _to_float(
        row.get("true_net_sales")
        or row.get("net_sales")
        or row.get("total_sales")
    )


def _slugify(value: str, fallback: str) -> str:
    """Convert a product title to a safe filename-friendly slug."""
    candidate = re.sub(r"[^a-zA-Z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return candidate or fallback


def _image_extension_from_url(url: str) -> str:
    """Extract the file extension from an image URL, defaulting to .jpg."""
    path = urlparse(url).path.lower()
    for ext in [".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"]:
        if path.endswith(ext):
            return ext
    return ".jpg"


def _base_product_image_payload(status: str, message: str) -> Dict[str, Any]:
    """Create a blank image payload dict with the given status and message."""
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
    """
    Download an image from a URL to disk.

    Uses streaming to avoid loading the full file into memory at once.
    Rejects non-image content types and files over MAX_IMAGE_BYTES.
    Cleans up partial files on failure so we never leave corrupt data behind.
    """
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
                # Abort mid-download if the file is too large.
                if total_bytes > MAX_IMAGE_BYTES:
                    if target_path.exists():
                        target_path.unlink()
                    return False, f"Image exceeds max size ({MAX_IMAGE_BYTES} bytes)"
                file_obj.write(chunk)

        return True, None
    except requests.RequestException as e:
        # Remove any partial file written before the error.
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

    Only the top N products by net sales get images (controlled by top_limit).
    Matching happens in two passes:
      1. Match by product_id  (fast, exact, preferred)
      2. Fall back to title search + variant price disambiguation
    Returns a summary dict and a flat list of index entries for every attempted row.
    """
    download = downloader or _download_image_default
    gen_path = Path(generation_dir).resolve()
    # Store downloaded images under a channel-specific subfolder so runs don't collide.
    image_dir = gen_path / "report_assets" / "product_images" / channel_key
    image_dir.mkdir(parents=True, exist_ok=True)

    # Pair each row with its original index so we can update it in-place after sorting.
    indexed_rows = list(enumerate(product_rows))
    ranked_rows = sorted(
        indexed_rows,
        key=lambda item: _sales_score(item[1], channel_key),
        reverse=True,
    )
    # Only enrich the top N rows by sales — downloading images for every product is too slow.
    selected = ranked_rows[: max(0, top_limit)]
    selected_indexes = {idx for idx, _ in selected}

    # Pre-stamp every row with a placeholder so the field always exists downstream.
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
        """Write match metadata and download the product image into the row's payload."""
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

        # Product matched but has no image attached in Shopify.
        if not remote_url:
            image_payload["status"] = "no_image"
            image_payload["message"] = "Matched product has no image media."
            summary["no_image_rows"] += 1
            return

        # Build a stable filename: slug + last 12 chars of GID (avoids collision for similar titles).
        product_slug = _slugify(row.get("product_title", ""), "product")
        gid_suffix = (record.get("id", "").split("/")[-1] or "unknown")[-12:]
        extension = _image_extension_from_url(remote_url)
        filename = f"{product_slug}_{gid_suffix}{extension}"
        target_path = image_dir / filename

        downloaded, error = download(remote_url, target_path)
        if downloaded:
            # Store a path relative to generation_dir so reports remain portable.
            rel_path = os.path.relpath(target_path, gen_path)
            image_payload["status"] = "enriched"
            image_payload["message"] = "Image downloaded successfully."
            image_payload["local_path"] = rel_path
            summary["enriched_rows"] += 1
        else:
            # URL is known but download failed — still useful for debugging.
            image_payload["status"] = "metadata_only"
            image_payload["message"] = f"Image URL found but download failed: {error}"
            summary["metadata_only_rows"] += 1

    # --- Pass 1: match by product_id (exact, highest confidence) ---
    # Group row indexes by GID so a single batch API call covers all of them.
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

    # --- Pass 2: title-based fallback for rows not resolved by ID ---
    # Cache results per title so we don't make duplicate API calls for the same product name.
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

        # Narrow candidates using variant price to resolve ambiguity when the same
        # product title exists across multiple Shopify products (e.g. re-listed items).
        price_matched_records = [
            record
            for record in matches
            if any(
                _money_matches(variant_price, row.get("product_variant_price"))
                for variant_price in (record.get("variant_prices") or [])
            )
        ]
        active_price_matched_records = _active_records(price_matched_records)
        active_matches = _active_records(matches)

        # Disambiguation priority (most → least confident):
        # 1. Single price match (any status)
        # 2. Single active price match
        # 3. Only one result at all
        # 4. Any active result (first wins)
        # 5. Any result at all (first wins)
        chosen_record = None
        chosen_method = None
        if len(price_matched_records) == 1:
            chosen_record = price_matched_records[0]
            chosen_method = "title_exact_variant_price"
        elif len(active_price_matched_records) == 1:
            chosen_record = active_price_matched_records[0]
            chosen_method = "title_exact_variant_price_active"
        elif len(matches) == 1:
            chosen_record = matches[0]
            chosen_method = "title_exact"
        elif active_matches:
            chosen_record = active_matches[0]
            chosen_method = "title_exact_active_fallback"
        elif matches:
            chosen_record = matches[0]
            chosen_method = "title_exact_fallback"

        if chosen_record is None:
            image_payload["status"] = "not_found"
            image_payload["message"] = "No exact product title match found in Product API."
            image_payload["match_method"] = "title_exact"
            image_payload["match_confidence"] = 0.0
            summary["not_found_rows"] += 1
        else:
            apply_match(
                row_index,
                chosen_record,
                match_method=chosen_method or "title_exact",
                match_confidence=1.0 if "title_exact" in (chosen_method or "") else 0.8,
            )
            summary["matched_by_title_rows"] += 1

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
