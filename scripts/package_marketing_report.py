#!/usr/bin/env python3
"""
Bundle report assets and export a PDF version of the marketing report.

This script solves report portability issues by:
1. Copying the whole reports/assets tree into the Desktop output folder.
2. Rewriting markdown image links to local relative paths under report_assets/.
3. Converting plain product-image path mentions into real markdown image embeds.
4. Rendering a cleaner PDF with section-based page breaks and table support.
"""

from __future__ import annotations

import argparse
import html
import re
import shutil
import sys
from pathlib import Path
from typing import List, Tuple


IMAGE_LINK_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
UNORDERED_BULLET_PATTERN = re.compile(r"^\s*[-*]\s+(.+)$")
ORDERED_BULLET_PATTERN = re.compile(r"^\s*\d+\.\s+(.+)$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
PRODUCT_IMAGE_PATH_PATTERN = re.compile(
    r"(assets/product_images/[a-zA-Z0-9_\-./]+\.(?:jpg|jpeg|png|webp|gif|bmp|tif|tiff|avif))"
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


def _inject_product_image_embeds_for_plain_paths(markdown_text: str) -> Tuple[str, int]:
    """
    Convert plain `assets/product_images/...` mentions into markdown image embeds.
    """
    lines = markdown_text.splitlines()
    out_lines: List[str] = []
    inserted = 0

    for line in lines:
        out_lines.append(line)
        if "![" in line:
            continue

        matches = PRODUCT_IMAGE_PATH_PATTERN.findall(line)
        if not matches:
            continue

        unique_paths = []
        seen = set()
        for path in matches:
            if path in seen:
                continue
            seen.add(path)
            unique_paths.append(path)

        for path in unique_paths:
            filename = Path(path).stem.replace("_", " ").strip() or "Product Image"
            out_lines.append(f"![{filename}]({path})")
            inserted += 1

    return "\n".join(out_lines), inserted


def bundle_markdown_assets(markdown_path: Path, reports_dir: Path, output_dir: Path) -> Tuple[int, int, int]:
    text = markdown_path.read_text(encoding="utf-8")
    text, inserted_embeds = _inject_product_image_embeds_for_plain_paths(text)
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
    escaped = html.escape(text.strip())
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", escaped)
    return escaped


def export_pdf(markdown_path: Path, pdf_path: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import Image as RLImage
        from reportlab.platypus import PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:
        raise RuntimeError(
            "Missing PDF dependency. Install with: python3 -m pip install reportlab"
        ) from exc

    markdown_text = markdown_path.read_text(encoding="utf-8")
    lines = markdown_text.splitlines()

    styles = getSampleStyleSheet()
    body_style = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=10.5,
        leading=14,
        spaceAfter=6,
    )
    heading_styles = {
        1: ParagraphStyle("H1", parent=styles["Heading1"], fontSize=20, leading=24, spaceBefore=12, spaceAfter=8),
        2: ParagraphStyle("H2", parent=styles["Heading2"], fontSize=16, leading=20, spaceBefore=10, spaceAfter=6),
        3: ParagraphStyle("H3", parent=styles["Heading3"], fontSize=13, leading=17, spaceBefore=8, spaceAfter=4),
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

    flowables = []
    in_code_block = False
    code_lines: List[str] = []
    seen_h2 = False
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

        if stripped.startswith("|") and i + 1 < len(lines) and TABLE_SEPARATOR_PATTERN.match(lines[i + 1].strip()):
            header_cells = _split_markdown_table_row(lines[i])
            table_rows: List[List[str]] = [header_cells]
            i += 2
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_rows.append(_split_markdown_table_row(lines[i]))
                i += 1

            col_count = len(header_cells)
            normalized_rows = []
            for row in table_rows:
                if len(row) < col_count:
                    row = row + [""] * (col_count - len(row))
                elif len(row) > col_count:
                    row = row[:col_count]
                normalized_rows.append(
                    [Paragraph(_inline_markdown_to_paragraph_html(cell), body_style) for cell in row]
                )

            table = Table(normalized_rows, repeatRows=1, hAlign="LEFT")
            table.setStyle(
                TableStyle(
                    [
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f4f6f8")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 6),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            flowables.append(table)
            flowables.append(Spacer(1, 0.10 * inch))
            continue

        if not stripped:
            flowables.append(Spacer(1, 0.08 * inch))
            i += 1
            continue

        image_match = IMAGE_LINK_PATTERN.fullmatch(stripped)
        if image_match:
            image_target = _extract_target(image_match.group(2))
            image_path = (markdown_path.parent / image_target).resolve()
            if image_path.exists():
                rl_image = RLImage(str(image_path))
                normalized_target = image_target.replace("\\", "/").lower()
                max_width = 7.0 * inch
                # Keep product photos compact in PDF sections to avoid oversized pages.
                if "product_images/" in normalized_target:
                    max_width = 2.4 * inch
                if rl_image.drawWidth > max_width:
                    ratio = max_width / rl_image.drawWidth
                    rl_image.drawWidth = max_width
                    rl_image.drawHeight = rl_image.drawHeight * ratio
                flowables.append(rl_image)
                flowables.append(Spacer(1, 0.10 * inch))
            else:
                note = _inline_markdown_to_paragraph_html(f"[Missing image: {image_target}]")
                flowables.append(Paragraph(note, body_style))
            i += 1
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 3)
            content = _inline_markdown_to_paragraph_html(heading_match.group(2))
            if level == 2:
                if seen_h2 and flowables:
                    flowables.append(PageBreak())
                seen_h2 = True
            flowables.append(Paragraph(content, heading_styles[level]))
            i += 1
            continue

        unordered_match = UNORDERED_BULLET_PATTERN.match(line)
        if unordered_match:
            content = _inline_markdown_to_paragraph_html(unordered_match.group(1))
            flowables.append(Paragraph(f"- {content}", body_style))
            i += 1
            continue

        ordered_match = ORDERED_BULLET_PATTERN.match(line)
        if ordered_match:
            content = _inline_markdown_to_paragraph_html(ordered_match.group(1))
            flowables.append(Paragraph(content, body_style))
            i += 1
            continue

        flowables.append(Paragraph(_inline_markdown_to_paragraph_html(line), body_style))
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
    parser.add_argument("--reports-dir", required=True, help="Path to reports/files_generation_N")
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
