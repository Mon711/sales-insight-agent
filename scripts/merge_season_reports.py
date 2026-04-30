#!/usr/bin/env python3
"""
Merge two season report JSON files into one comparison source document.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def _to_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sum_rows(rows: Iterable[Dict[str, Any]], key: str) -> float:
    return sum(_to_float(row.get(key)) for row in rows)


def _first_non_empty(values: Iterable[Any], fallback: str = "") -> str:
    for value in values:
        if not _is_blank(value):
            return str(value)
    return fallback


def _season_summary(season_payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = (season_payload.get("season_product_performance") or {}).get("rows") or []
    if not rows:
        return {
            "product_count": 0,
            "net_sales_total": 0.0,
            "gross_sales_total": 0.0,
            "returns_total": 0.0,
            "net_items_sold_total": 0.0,
            "top_product": None,
            "bottom_product": None,
        }

    return {
        "product_count": len(rows),
        "net_sales_total": round(_sum_rows(rows, "net_sales"), 2),
        "gross_sales_total": round(_sum_rows(rows, "gross_sales"), 2),
        "returns_total": round(_sum_rows(rows, "returns"), 2),
        "net_items_sold_total": round(_sum_rows(rows, "net_items_sold"), 2),
        "top_product": {
            "product_title": _first_non_empty([rows[0].get("product_title")]),
            "net_sales": _to_float(rows[0].get("net_sales")),
            "net_items_sold": _to_float(rows[0].get("net_items_sold")),
            "returned_quantity_rate": rows[0].get("returned_quantity_rate"),
        },
        "bottom_product": {
            "product_title": _first_non_empty([rows[-1].get("product_title")]),
            "net_sales": _to_float(rows[-1].get("net_sales")),
            "net_items_sold": _to_float(rows[-1].get("net_items_sold")),
            "returned_quantity_rate": rows[-1].get("returned_quantity_rate"),
        },
    }


def _delta(left: Dict[str, Any], right: Dict[str, Any], key: str) -> float:
    return round(_to_float(right.get(key)) - _to_float(left.get(key)), 2)


def build_comparison_payload(
    *,
    brand_slug: str,
    brand_display_name: str,
    family_slug: str,
    family_display_name: str,
    season_a: Dict[str, Any],
    season_b: Dict[str, Any],
) -> Dict[str, Any]:
    season_a_slug = season_a.get("season", {}).get("slug") or "season_a"
    season_b_slug = season_b.get("season", {}).get("slug") or "season_b"
    summaries = {
        season_a_slug: _season_summary(season_a),
        season_b_slug: _season_summary(season_b),
    }

    comparison_summary = {
        season_a_slug: summaries[season_a_slug],
        season_b_slug: summaries[season_b_slug],
        "delta": {
            "net_sales_total": _delta(summaries[season_a_slug], summaries[season_b_slug], "net_sales_total"),
            "gross_sales_total": _delta(summaries[season_a_slug], summaries[season_b_slug], "gross_sales_total"),
            "returns_total": _delta(summaries[season_a_slug], summaries[season_b_slug], "returns_total"),
            "net_items_sold_total": _delta(summaries[season_a_slug], summaries[season_b_slug], "net_items_sold_total"),
            "product_count": int(summaries[season_b_slug]["product_count"]) - int(summaries[season_a_slug]["product_count"]),
        },
    }

    period_a = season_a.get("report_period") or {}
    period_b = season_b.get("report_period") or {}
    shared_period = {
        "since": _first_non_empty([period_a.get("since"), period_b.get("since")]),
        "until": _first_non_empty([period_a.get("until"), period_b.get("until")]),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "report_type": "season_family_comparison",
        "brand": {
            "slug": brand_slug,
            "display_name": brand_display_name,
        },
        "comparison": {
            "family_slug": family_slug,
            "family_display_name": family_display_name,
            "season_slugs": [season_a_slug, season_b_slug],
            "season_display_names": [
                season_a.get("season", {}).get("display_name"),
                season_b.get("season", {}).get("display_name"),
            ],
            "report_period": shared_period,
        },
        "comparison_summary": comparison_summary,
        "seasons": {
            season_a_slug: season_a,
            season_b_slug: season_b,
        },
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Merge two season report JSON files into one comparison payload.")
    parser.add_argument("--brand-slug", required=True)
    parser.add_argument("--brand-display-name", required=True)
    parser.add_argument("--family-slug", required=True)
    parser.add_argument("--family-display-name", required=True)
    parser.add_argument("--season-a-json", required=True)
    parser.add_argument("--season-b-json", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    season_a_path = Path(args.season_a_json).expanduser().resolve()
    season_b_path = Path(args.season_b_json).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    season_a = json.loads(season_a_path.read_text(encoding="utf-8"))
    season_b = json.loads(season_b_path.read_text(encoding="utf-8"))

    payload = build_comparison_payload(
        brand_slug=args.brand_slug,
        brand_display_name=args.brand_display_name,
        family_slug=args.family_slug,
        family_display_name=args.family_display_name,
        season_a=season_a,
        season_b=season_b,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"Comparison payload written to: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
