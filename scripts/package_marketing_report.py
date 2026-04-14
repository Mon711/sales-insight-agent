#!/usr/bin/env python3
"""
Bundle report assets and export a PDF version of the marketing report.

This script solves report portability issues by:
1. Copying the whole reports/assets tree into the Desktop output folder.
2. Rewriting markdown image links to local relative paths under report_assets/.
3. Rendering a cleaner PDF with compact markdown, table support, and local images.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
import unicodedata
from pathlib import Path
from typing import List, Tuple


IMAGE_LINK_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
UNORDERED_BULLET_PATTERN = re.compile(r"^(\s*)[-*]\s+(.+)$")
ORDERED_BULLET_PATTERN = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
HTML_COMMENT_PATTERN = re.compile(r"^<!--.*-->$")

UNICODE_PUNCTUATION_REPLACEMENTS = {
    "\u00a0": " ",
    "\u2007": " ",
    "\u202f": " ",
    "\u200b": "",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\u2015": "-",
    "\u2212": "-",
    "\u2026": "...",
    "\u2018": "'",
    "\u2019": "'",
    "\u201a": ",",
    "\u201b": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u201e": '"',
}


def _sanitize_pdf_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for source, replacement in UNICODE_PUNCTUATION_REPLACEMENTS.items():
        normalized = normalized.replace(source, replacement)
    return "".join(
        ch for ch in normalized
        if ch in "\n\t" or unicodedata.category(ch)[0] != "C"
    )


def _extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    if " \"" in target and target.endswith('"'):
        maybe_path, _ = target.rsplit(" \"", 1)
        target = maybe_path.strip()

    return target


def _is_remote_target(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("data:")


def _split_markdown_table_row(line: str) -> List[str]:
    body = line.strip().strip("|")
    return [cell.strip() for cell in body.split("|")]


def _copy_reports_assets_tree(reports_dir: Path, output_dir: Path) -> int:
    source_assets = (reports_dir / "assets").resolve()
    destination_assets = (output_dir / "report_assets").resolve()
    if not source_assets.exists():
        return 0

    destination_assets.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_assets, destination_assets, dirs_exist_ok=True)
    return sum(1 for p in destination_assets.rglob("*") if p.is_file())


def _find_image_source(
    *,
    target: str,
    markdown_path: Path,
    reports_dir: Path,
    output_dir: Path,
) -> Path | None:
    if _is_remote_target(target):
        return None

    # Prefer already-packaged desktop assets for direct portability.
    if target.startswith("assets/"):
        packaged = (output_dir / "report_assets" / target[len("assets/"):]).resolve()
        if packaged.exists() and packaged.is_file():
            return packaged

    path_obj = Path(target)
    candidates: List[Path] = []

    if path_obj.is_absolute():
        candidates.append(path_obj)
    else:
        candidates.append((markdown_path.parent / path_obj).resolve())
        candidates.append((output_dir / path_obj).resolve())
        candidates.append((reports_dir / path_obj).resolve())
        if target.startswith("assets/"):
            candidates.append((reports_dir / target).resolve())

    seen = set()
    for candidate in candidates:
        normalized = str(candidate)
        if normalized in seen:
            continue
        seen.add(normalized)
        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def _copy_asset_to_output(
    *,
    source: Path,
    reports_dir: Path,
    output_dir: Path,
) -> Path:
    reports_assets_dir = (reports_dir / "assets").resolve()
    output_assets_dir = (output_dir / "report_assets").resolve()

    try:
        relative_from_assets = source.resolve().relative_to(reports_assets_dir)
        destination = output_assets_dir / relative_from_assets
    except ValueError:
        try:
            already_packaged = source.resolve().relative_to(output_assets_dir.resolve())
            return output_assets_dir / already_packaged
        except ValueError:
            destination = output_assets_dir / "external" / source.name

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def bundle_markdown_assets(markdown_path: Path, reports_dir: Path, output_dir: Path) -> Tuple[int, int, int]:
    text = markdown_path.read_text(encoding="utf-8")
    inserted_embeds = 0
    # Enforce local-only image embeds; strip remote CDN links if present.
    text = IMAGE_LINK_PATTERN.sub(
        lambda m: m.group(0) if not _is_remote_target(_extract_target(m.group(2))) else f"[Image not embedded locally: {m.group(1) or 'Product'}]",
        text,
    )
    copied_count = 0
    rewritten_count = 0

    def replace(match: re.Match[str]) -> str:
        nonlocal copied_count, rewritten_count
        alt_text = match.group(1)
        raw_target = match.group(2)
        target = _extract_target(raw_target)

        source = _find_image_source(
            target=target,
            markdown_path=markdown_path,
            reports_dir=reports_dir,
            output_dir=output_dir,
        )
        if source is None:
            return match.group(0)

        destination = _copy_asset_to_output(
            source=source,
            reports_dir=reports_dir,
            output_dir=output_dir,
        )
        copied_count += 1
        relative_target = destination.relative_to(markdown_path.parent.resolve()).as_posix()
        rewritten_count += 1
        return f"![{alt_text}]({relative_target})"

    updated = IMAGE_LINK_PATTERN.sub(replace, text)
    markdown_path.write_text(updated, encoding="utf-8")
    return copied_count, rewritten_count, inserted_embeds


def _inline_markdown_to_paragraph_html(text: str) -> str:
    escaped = html.escape(_sanitize_pdf_text(text.strip()))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", escaped)
    return escaped


def _build_table_image_cell(image_target: str, markdown_path: Path, max_size: float):
    from reportlab.platypus import Image as RLImage

    image_path = (markdown_path.parent / image_target).resolve()
    if not image_path.exists():
        return None

    rl_image = RLImage(str(image_path))
    width_ratio = max_size / rl_image.drawWidth if rl_image.drawWidth else 1
    height_ratio = max_size / rl_image.drawHeight if rl_image.drawHeight else 1
    scale_ratio = min(width_ratio, height_ratio, 1)
    rl_image.drawWidth *= scale_ratio
    rl_image.drawHeight *= scale_ratio
    return rl_image


def _build_table_cell(cell_text: str, paragraph_style, markdown_path: Path, image_max_size: float):
    from reportlab.platypus import Paragraph

    stripped = cell_text.strip()
    image_match = IMAGE_LINK_PATTERN.fullmatch(stripped)
    if image_match:
        image_target = _extract_target(image_match.group(2))
        image_cell = _build_table_image_cell(image_target, markdown_path, image_max_size)
        if image_cell is not None:
            return image_cell
    return Paragraph(_inline_markdown_to_paragraph_html(cell_text), paragraph_style)


def _table_col_widths(headers: List[str], inch_value: float):
    normalized = [header.strip().lower() for header in headers]
    if normalized == [
        "image",
        "rank",
        "product title",
        "net sales",
        "net items sold",
        "gross sales",
        "average order value",
        "returned quantity rate",
    ]:
        return [
            0.50 * inch_value,
            0.35 * inch_value,
            1.95 * inch_value,
            0.86 * inch_value,
            0.75 * inch_value,
            0.86 * inch_value,
            0.86 * inch_value,
            0.85 * inch_value,
        ]
    if normalized == [
        "image",
        "rank",
        "product title",
        "variant family",
        "net sales",
        "net items sold",
        "gross sales",
        "returns",
    ]:
        return [
            0.50 * inch_value,
            0.35 * inch_value,
            1.40 * inch_value,
            1.30 * inch_value,
            0.72 * inch_value,
            0.72 * inch_value,
            0.80 * inch_value,
            0.71 * inch_value,
        ]
    return None


def _table_alignment_styles(headers: List[str]):
    normalized = [header.strip().lower() for header in headers]
    if normalized == [
        "image",
        "rank",
        "product title",
        "net sales",
        "net items sold",
        "gross sales",
        "average order value",
        "returned quantity rate",
    ]:
        return [
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("ALIGN", (3, 1), (-1, -1), "RIGHT"),
        ]
    if normalized == [
        "image",
        "rank",
        "product title",
        "variant family",
        "net sales",
        "net items sold",
        "gross sales",
        "returns",
    ]:
        return [
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "RIGHT"),
            ("ALIGN", (4, 1), (-1, -1), "RIGHT"),
        ]
    return []


def export_pdf(markdown_path: Path, pdf_path: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Image as RLImage
        from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError(
            "Missing PDF dependency. Install with: python3 -m pip install reportlab"
        ) from exc

    markdown_text = _sanitize_pdf_text(markdown_path.read_text(encoding="utf-8"))
    lines = markdown_text.splitlines()

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.8,
        leading=12.4,
        spaceAfter=3,
    )
    heading_styles = {
        1: ParagraphStyle("H1", parent=styles["Heading1"], fontSize=19, leading=22, spaceBefore=8, spaceAfter=6),
        2: ParagraphStyle("H2", parent=styles["Heading2"], fontSize=15, leading=18, spaceBefore=8, spaceAfter=4),
        3: ParagraphStyle("H3", parent=styles["Heading3"], fontSize=12.5, leading=15, spaceBefore=6, spaceAfter=3),
    }
    code_style = ParagraphStyle(
        "Code",
        parent=body_style,
        fontName="Courier",
        fontSize=9,
        leading=12,
        backColor=colors.whitesmoke,
        leftIndent=8,
        rightIndent=8,
        borderPadding=6,
    )
    bullet_style = ParagraphStyle(
        "Bullet",
        parent=body_style,
        leftIndent=14,
        firstLineIndent=0,
        bulletIndent=0,
        spaceBefore=0,
        spaceAfter=2,
    )
    table_body_style = ParagraphStyle(
        "TableBody",
        parent=body_style,
        fontSize=6.9,
        leading=7.8,
        spaceAfter=0,
    )
    table_header_style = ParagraphStyle(
        "TableHeader",
        parent=table_body_style,
        fontName="Helvetica-Bold",
    )

    flowables = []
    in_code_block = False
    code_lines: List[str] = []
    last_was_spacer = False
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                flowables.append(Preformatted("\n".join(code_lines), code_style))
                flowables.append(Spacer(1, 0.12 * inch))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            i += 1
            continue

        if in_code_block:
            code_lines.append(line.rstrip())
            i += 1
            continue

        if HTML_COMMENT_PATTERN.match(stripped):
            i += 1
            continue

        if stripped.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR_PATTERN.match(lines[i + 1].strip()):
            header_cells = _split_markdown_table_row(lines[i])
            table_rows: List[List[str]] = [header_cells]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_rows.append(_split_markdown_table_row(lines[i]))
                i += 1

            col_count = len(header_cells)
            normalized_rows = []
            for row_index, row in enumerate(table_rows):
                if len(row) < col_count:
                    row = row + [""] * (col_count - len(row))
                elif len(row) > col_count:
                    row = row[:col_count]
                paragraph_style = table_header_style if row_index == 0 else table_body_style
                normalized_rows.append(
                    [
                        _build_table_cell(
                            cell,
                            paragraph_style,
                            markdown_path,
                            image_max_size=0.52 * inch,
                        )
                        for cell in row
                    ]
                )

            table = Table(
                normalized_rows,
                colWidths=_table_col_widths(header_cells, inch),
                repeatRows=1,
                hAlign="LEFT",
            )
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f6f8")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                    + _table_alignment_styles(header_cells)
                )
            )
            if header_cells and header_cells[0].strip().lower() == "image":
                table.setStyle(
                    TableStyle(
                        [
                            ("ALIGN", (0, 1), (0, -1), "CENTER"),
                            ("VALIGN", (0, 1), (0, -1), "MIDDLE"),
                        ]
                    )
                )
            flowables.append(table)
            flowables.append(Spacer(1, 0.06 * inch))
            last_was_spacer = True
            continue

        if not stripped:
            if not last_was_spacer:
                flowables.append(Spacer(1, 0.04 * inch))
                last_was_spacer = True
            i += 1
            continue

        image_match = IMAGE_LINK_PATTERN.fullmatch(stripped)
        if image_match:
            image_target = _extract_target(image_match.group(2))
            image_path = (markdown_path.parent / image_target).resolve()
            if image_path.exists():
                rl_image = RLImage(str(image_path))
                normalized_target = image_target.replace("\\", "/").lower()
                if "product_images/" in normalized_target:
                    i += 1
                    continue
                max_width = 7.0 * inch
                if rl_image.drawWidth > max_width:
                    ratio = max_width / rl_image.drawWidth
                    rl_image.drawWidth = max_width
                    rl_image.drawHeight = rl_image.drawHeight * ratio
                flowables.append(rl_image)
                flowables.append(Spacer(1, 0.06 * inch))
                last_was_spacer = True
            else:
                note = _inline_markdown_to_paragraph_html(f"[Missing image: {image_target}]")
                flowables.append(Paragraph(note, body_style))
            i += 1
            last_was_spacer = False
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 3)
            content = _inline_markdown_to_paragraph_html(heading_match.group(2))
            flowables.append(Paragraph(content, heading_styles[level]))
            last_was_spacer = False
            i += 1
            continue

        unordered_match = UNORDERED_BULLET_PATTERN.match(line)
        if unordered_match:
            indent_spaces = len(unordered_match.group(1))
            content = _inline_markdown_to_paragraph_html(unordered_match.group(2))
            bullet_indent = 14 + (indent_spaces // 2) * 12
            bullet_paragraph_style = ParagraphStyle(
                "BulletIndented",
                parent=bullet_style,
                leftIndent=bullet_indent,
            )
            flowables.append(Paragraph(content, bullet_paragraph_style, bulletText="•"))
            last_was_spacer = False
            i += 1
            continue

        ordered_match = ORDERED_BULLET_PATTERN.match(line)
        if ordered_match:
            indent_spaces = len(ordered_match.group(1))
            number = ordered_match.group(2)
            content = _inline_markdown_to_paragraph_html(ordered_match.group(3))
            bullet_indent = 14 + (indent_spaces // 2) * 12
            ordered_paragraph_style = ParagraphStyle(
                "OrderedIndented",
                parent=bullet_style,
                leftIndent=bullet_indent,
            )
            flowables.append(Paragraph(content, ordered_paragraph_style, bulletText=f"{number}."))
            last_was_spacer = False
            i += 1
            continue

        flowables.append(Paragraph(_inline_markdown_to_paragraph_html(line), body_style))
        last_was_spacer = False
        i += 1

    if in_code_block and code_lines:
        flowables.append(Preformatted("\n".join(code_lines), code_style))

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=LETTER,
        leftMargin=0.7 * inch,
        rightMargin=0.7 * inch,
        topMargin=0.7 * inch,
        bottomMargin=0.7 * inch,
        title=markdown_path.stem,
        author="Sales Insight Agent",
    )
    doc.build(flowables)


def main() -> int:
    parser = argparse.ArgumentParser(description="Bundle markdown assets and export a PDF report.")
    parser.add_argument("--markdown", required=True, help="Path to MARKETING_REPORT.md")
    parser.add_argument("--reports-dir", required=True, help="Path to report_source")
    parser.add_argument("--output-dir", required=True, help="Path to Desktop output folder")
    parser.add_argument("--pdf-name", default="MARKETING_REPORT.pdf", help="Output PDF filename")
    args = parser.parse_args()

    markdown_path = Path(args.markdown).expanduser().resolve()
    reports_dir = Path(args.reports_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    pdf_path = output_dir / args.pdf_name

    if not markdown_path.exists():
        print(f"ERROR: Markdown file not found: {markdown_path}", file=sys.stderr)
        return 1
    if not reports_dir.exists():
        print(f"ERROR: Reports directory not found: {reports_dir}", file=sys.stderr)
        return 1
    if not output_dir.exists():
        print(f"ERROR: Output directory not found: {output_dir}", file=sys.stderr)
        return 1

    copied_assets_total = _copy_reports_assets_tree(reports_dir, output_dir)
    copied_count, rewritten_count, inserted_embeds = bundle_markdown_assets(markdown_path, reports_dir, output_dir)
    print(
        "Packaged assets files available: "
        f"{copied_assets_total}; markdown links rewritten: {rewritten_count}; "
        f"new product embeds inserted: {inserted_embeds}; direct copies in rewrite pass: {copied_count}"
    )

    try:
        export_pdf(markdown_path, pdf_path)
        print(f"PDF exported: {pdf_path}")
    except Exception as e:
        print(f"WARNING: PDF export skipped: {e}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
