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
                idx,
                row.get("product_title"),
                row.get("product_variant_price"),
                row.get("net_sales"),
                row.get("net_items_sold"),
                row.get("gross_sales"),
                row.get("average_order_value"),
                row.get("returned_quantity_rate"),
            ]
        )
    return output


def _category_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[List[Any]]:
    output: List[List[Any]] = []
    for idx, row in enumerate(rows[:limit], start=1):
        output.append(
            [
                idx,
                row.get("product_type"),
                row.get("net_sales"),
                row.get("net_items_sold"),
            ]
        )
    return output


def _render_tables_block(data: Dict[str, Any]) -> str:
    top = (data.get("top_performers") or {}).get("rows") or []
    under = (data.get("underperformers") or {}).get("rows") or []
    categories = (data.get("top_categories") or {}).get("rows") or []

    top_table = _table(
        ["Rank", "Product title", "Variant price", "Net sales", "Net items sold", "Gross sales", "Average order value", "Returned quantity rate"],
        _top_rows(top, limit=20),
    )
    under_table = _table(
        ["Rank", "Product title", "Variant price", "Net sales", "Net items sold", "Gross sales", "Average order value", "Returned quantity rate"],
        _top_rows(under, limit=20),
    )
    category_table = _table(
        ["Rank", "Category", "Net sales", "Net items sold"],
        _category_rows(categories, limit=20),
    )

    return (
        f"{START_MARKER}\n"
        "## Query Result Tables\n\n"
        "### Top 20 Performers\n\n"
        f"{top_table}\n\n"
        "### Top 20 Underperformers\n\n"
        f"{under_table}\n\n"
        "### Top 20 Categories\n\n"
        f"{category_table}\n"
        f"{END_MARKER}\n"
    )


def ensure_tables(markdown_path: Path, annual_json_path: Path) -> None:
    markdown = markdown_path.read_text(encoding="utf-8")
    data = json.loads(annual_json_path.read_text(encoding="utf-8"))
    block = _render_tables_block(data)

    pattern = re.compile(
        re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER) + r"\n?",
        flags=re.DOTALL,
    )
    cleaned = re.sub(pattern, "", markdown).rstrip() + "\n\n"
    markdown_path.write_text(cleaned + block, encoding="utf-8")


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
