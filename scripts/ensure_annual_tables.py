#!/usr/bin/env python3
"""
Ensure annual report markdown includes canonical query-result tables.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List

START_MARKER = "<!-- AUTO_ANNUAL_QUERY_TABLES_START -->"
END_MARKER = "<!-- AUTO_ANNUAL_QUERY_TABLES_END -->"
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
MARKDOWN_IMAGE_LINE_PATTERN = re.compile(r"^!\[[^\]]*\]\(([^)]+)\)$")
OBSIDIAN_IMAGE_LINE_PATTERN = re.compile(r"^!\[\[([^\]]+)\]\]$")


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _as_float(value: Any) -> float | None:
    if _is_blank(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt_currency(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return ""
    return f"${amount:,.2f}"


def _fmt_number(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return ""
    if amount.is_integer():
        return f"{int(amount):,}"
    return f"{amount:,.2f}"


def _fmt_percent(value: Any) -> str:
    amount = _as_float(value)
    if amount is None:
        return ""
    return f"{amount * 100:.1f}%"


def _product_image_cell(row: Dict[str, Any]) -> str:
    payload = row.get("product_image") or {}
    local_path = payload.get("local_path")
    if not local_path:
        return ""

    alt_text = row.get("product_title") or "Product image"
    return f"![{alt_text}]({local_path})"


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _table(headers: List[str], rows: List[List[Any]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(_fmt(cell) for cell in row) + " |" for row in rows]
    return "\n".join([head, sep] + body)


def _top_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[List[Any]]:
    output: List[List[Any]] = []
    for idx, row in enumerate(rows[:limit], start=1):
        output.append(
            [
                _product_image_cell(row),
                idx,
                row.get("product_title"),
                _fmt_currency(row.get("product_variant_price")),
                _fmt_currency(row.get("net_sales")),
                _fmt_number(row.get("net_items_sold")),
                _fmt_currency(row.get("gross_sales")),
                _fmt_currency(row.get("average_order_value")),
                _fmt_percent(row.get("returned_quantity_rate")),
            ]
        )
    return output


def _category_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[List[Any]]:
    output: List[List[Any]] = []
    for idx, row in enumerate(rows[:limit], start=1):
        output.append(
            [
                idx,
                row.get("product_type") or "Uncategorized",
                _fmt_currency(row.get("net_sales")),
                _fmt_number(row.get("net_items_sold")),
            ]
        )
    return output


def _render_tables_block(data: Dict[str, Any]) -> str:
    top = (data.get("top_performers") or {}).get("rows") or []
    under = (data.get("underperformers") or {}).get("rows") or []
    categories = (data.get("top_categories") or {}).get("rows") or []

    top_table = _table(
        ["Image", "Rank", "Product title", "Variant price", "Net sales", "Net items sold", "Gross sales", "Average order value", "Returned quantity rate"],
        _top_rows(top, limit=20),
    )
    under_table = _table(
        ["Image", "Rank", "Product title", "Variant price", "Net sales", "Net items sold", "Gross sales", "Average order value", "Returned quantity rate"],
        _top_rows(under, limit=20),
    )
    category_table = _table(
        ["Rank", "Category", "Net sales", "Net items sold"],
        _category_rows(categories, limit=20),
    )

    return (
        f"{START_MARKER}\n"
        "# Query Result Tables\n\n"
        "## Top 20 Performers\n\n"
        f"{top_table}\n\n"
        "## Top 20 Underperformers\n\n"
        f"{under_table}\n\n"
        "## Top 20 Categories\n\n"
        f"{category_table}\n"
        f"{END_MARKER}\n"
    )


def _strip_auto_tables_block(markdown: str) -> str:
    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER) + r"\n?",
        flags=re.DOTALL,
    )
    return re.sub(pattern, "", markdown)


def _remove_heading_section(markdown: str, target_heading: str) -> str:
    lines = markdown.splitlines()
    output: List[str] = []
    target = target_heading.strip().lower()
    i = 0

    while i < len(lines):
        heading_match = HEADING_PATTERN.match(lines[i].strip())
        if not heading_match or heading_match.group(2).strip().lower() != target:
            output.append(lines[i])
            i += 1
            continue

        current_level = len(heading_match.group(1))
        i += 1
        while i < len(lines):
            next_heading = HEADING_PATTERN.match(lines[i].strip())
            if next_heading and len(next_heading.group(1)) <= current_level:
                break
            i += 1

        while output and not output[-1].strip():
            output.pop()

    return "\n".join(output).strip() + "\n"


def _line_is_product_image(line: str) -> bool:
    stripped = line.strip()
    markdown_match = MARKDOWN_IMAGE_LINE_PATTERN.match(stripped)
    if markdown_match:
        return "product_images/" in markdown_match.group(1).replace("\\", "/").lower()

    obsidian_match = OBSIDIAN_IMAGE_LINE_PATTERN.match(stripped)
    if obsidian_match:
        target = obsidian_match.group(1).split("|", 1)[0]
        return "product_images/" in target.replace("\\", "/").lower()

    return False


def _strip_standalone_product_images(markdown: str) -> str:
    filtered_lines = [line for line in markdown.splitlines() if not _line_is_product_image(line)]
    compacted = "\n".join(filtered_lines)
    compacted = re.sub(r"\n{3,}", "\n\n", compacted)
    return compacted.strip() + "\n"


def _insert_tables_after_executive_summary(markdown: str, block: str) -> str:
    lines = markdown.strip().splitlines()
    insert_at = None

    for idx, line in enumerate(lines):
        heading_match = HEADING_PATTERN.match(line.strip())
        if not heading_match:
            continue
        if heading_match.group(2).strip().lower() != "executive summary":
            continue

        current_level = len(heading_match.group(1))
        insert_at = idx + 1
        while insert_at < len(lines):
            next_heading = HEADING_PATTERN.match(lines[insert_at].strip())
            if next_heading and len(next_heading.group(1)) <= current_level:
                break
            insert_at += 1
        break

    if insert_at is None:
        return block.strip() + "\n\n" + markdown.strip() + "\n"

    before = "\n".join(lines[:insert_at]).strip()
    after = "\n".join(lines[insert_at:]).strip()

    sections = [section for section in [before, block.strip(), after] if section]
    return "\n\n".join(sections) + "\n"


def ensure_tables(markdown_path: Path, annual_json_path: Path) -> None:
    markdown = markdown_path.read_text(encoding="utf-8")
    data = json.loads(annual_json_path.read_text(encoding="utf-8"))
    block = _render_tables_block(data)
    cleaned = _strip_auto_tables_block(markdown)
    cleaned = _remove_heading_section(cleaned, "Query Result Tables")
    cleaned = _strip_standalone_product_images(cleaned)
    updated = _insert_tables_after_executive_summary(cleaned, block)
    markdown_path.write_text(updated, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Inject annual query-result tables into markdown.")
    parser.add_argument("--markdown", required=True)
    parser.add_argument("--annual-json", required=True)
    args = parser.parse_args()

    markdown_path = Path(args.markdown).expanduser().resolve()
    annual_json_path = Path(args.annual_json).expanduser().resolve()
    ensure_tables(markdown_path, annual_json_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
