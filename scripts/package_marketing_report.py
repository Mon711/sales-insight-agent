#!/usr/bin/env python3
"""
Bundle report assets and export a PDF version of the marketing report.

This script solves report portability issues by:
1. Copying the whole reports/assets tree into the local output folder.
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


# Regex patterns for parsing Markdown and HTML elements during PDF rendering.
IMAGE_LINK_PATTERN = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")
HTML_IMAGE_TAG_PATTERN = re.compile(r"<img\b[^>]*>", re.IGNORECASE)
HTML_SRC_ATTR_PATTERN = re.compile(r'(\bsrc\s*=\s*)(["\'])(.*?)\2', re.IGNORECASE)
HTML_FIGURE_START_PATTERN = re.compile(r"^\s*<figure\b[^>]*>\s*$", re.IGNORECASE)
HTML_FIGURE_END_PATTERN = re.compile(r"^\s*</figure>\s*$", re.IGNORECASE)
HTML_FIGCAPTION_PATTERN = re.compile(r"<figcaption\b[^>]*>(.*?)</figcaption>", re.IGNORECASE | re.DOTALL)
HTML_IMAGE_ALT_PATTERN = re.compile(r'\balt\s*=\s*(["\'])(.*?)\1', re.IGNORECASE)
HTML_IMAGE_WIDTH_PATTERN = re.compile(r'\bwidth\s*=\s*(["\']?)(\d+)\1', re.IGNORECASE)
HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.*)$")
UNORDERED_BULLET_PATTERN = re.compile(r"^(\s*)[-*]\s+(.+)$")
ORDERED_BULLET_PATTERN = re.compile(r"^(\s*)(\d+)\.\s+(.+)$")
TABLE_SEPARATOR_PATTERN = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")
HTML_COMMENT_PATTERN = re.compile(r"^<!--.*-->$")

# Normalize fancy/Unicode punctuation to plain ASCII so PDF rendering doesn't choke.
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
    """
    Normalize Unicode and strip control characters before handing text to ReportLab.

    NFKC normalization resolves ligatures and compatibility characters.
    Control characters (category 'C') cause rendering errors in PDF fonts.
    """
    normalized = unicodedata.normalize("NFKC", text)
    for source, replacement in UNICODE_PUNCTUATION_REPLACEMENTS.items():
        normalized = normalized.replace(source, replacement)
    return "".join(
        ch for ch in normalized
        if ch in "\n\t" or unicodedata.category(ch)[0] != "C"
    )


def _extract_target(raw_target: str) -> str:
    """
    Parse a raw Markdown link target into a clean file path or URL.

    Handles angle-bracket syntax (<path>) and optional title strings ("title").
    """
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    # Strip an optional inline title: ![alt](path "title") → path
    if " \"" in target and target.endswith('"'):
        maybe_path, _ = target.rsplit(" \"", 1)
        target = maybe_path.strip()

    return target


def _is_remote_target(target: str) -> bool:
    """Return True if the target is a remote URL (http/https/data URI)."""
    lowered = target.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("data:")


def _parse_html_img_src(tag: str) -> tuple[str | None, str | None, str | None]:
    src_match = HTML_SRC_ATTR_PATTERN.search(tag)
    if not src_match:
        return None, None, None

    alt_match = HTML_IMAGE_ALT_PATTERN.search(tag)
    width_match = HTML_IMAGE_WIDTH_PATTERN.search(tag)
    return src_match.group(3), alt_match.group(2) if alt_match else None, width_match.group(2) if width_match else None


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


def _rewrite_html_img_tags(
    text: str,
    *,
    markdown_path: Path,
    reports_dir: Path,
    output_dir: Path,
) -> tuple[str, int, int]:
    copied_count = 0
    rewritten_count = 0

    def replace(tag_match: re.Match[str]) -> str:
        nonlocal copied_count, rewritten_count
        tag = tag_match.group(0)
        raw_src, _, _ = _parse_html_img_src(tag)
        if not raw_src:
            return tag
        target = _extract_target(raw_src)
        source = _find_image_source(
            target=target,
            markdown_path=markdown_path,
            reports_dir=reports_dir,
            output_dir=output_dir,
        )
        if source is None:
            return tag
        destination = _copy_asset_to_output(
            source=source,
            reports_dir=reports_dir,
            output_dir=output_dir,
        )
        copied_count += 1
        rewritten_count += 1
        relative_target = destination.relative_to(markdown_path.parent.resolve()).as_posix()
        return tag.replace(raw_src, relative_target)

    updated = HTML_IMAGE_TAG_PATTERN.sub(replace, text)
    return updated, copied_count, rewritten_count


def _find_image_source(
    *,
    target: str,
    markdown_path: Path,
    reports_dir: Path,
    output_dir: Path,
) -> Path | None:
    """
    Resolve a Markdown image target to an actual file on disk.

    Checks multiple candidate locations in priority order so the script works
    whether assets are referenced from the markdown file, the reports dir, or
    the already-packaged output folder. Returns None for remote URLs.
    """
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
        # Try relative to the markdown file first, then the output and reports directories.
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
    """
    Copy all local images referenced in the markdown into the output folder
    and rewrite their links to relative paths so the PDF renders correctly.

    Remote image links are replaced with a placeholder text so the PDF doesn't
    contain broken embed attempts.
    """
    text = markdown_path.read_text(encoding="utf-8")
    inserted_embeds = 0
    # Enforce local-only image embeds; strip remote CDN links if present.
    text = IMAGE_LINK_PATTERN.sub(
        lambda m: m.group(0) if not _is_remote_target(_extract_target(m.group(2))) else f"[Image not embedded locally: {m.group(1) or 'Product'}]",
        text,
    )
    text, html_copied_count, html_rewritten_count = _rewrite_html_img_tags(
        text,
        markdown_path=markdown_path,
        reports_dir=reports_dir,
        output_dir=output_dir,
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
        # Use a path relative to the markdown file so links are self-contained.
        relative_target = destination.relative_to(markdown_path.parent.resolve()).as_posix()
        rewritten_count += 1
        return f"![{alt_text}]({relative_target})"

    updated = IMAGE_LINK_PATTERN.sub(replace, text)
    markdown_path.write_text(updated, encoding="utf-8")
    return copied_count + html_copied_count, rewritten_count + html_rewritten_count, inserted_embeds


def _inline_markdown_to_paragraph_html(text: str) -> str:
    """
    Convert inline Markdown to the small subset of HTML that ReportLab's Paragraph accepts.

    Handles bold (**text**), italic (*text*), inline code (`text`), and links ([label](url)).
    HTML-escapes special characters first to prevent injection into the XML-like tag stream.
    """
    escaped = html.escape(_sanitize_pdf_text(text.strip()))
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<i>\1</i>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    # PDFs can't make links clickable in plain ReportLab, so collapse to "label (url)".
    escaped = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", escaped)
    return escaped


def _build_table_image_cell(image_target: str, markdown_path: Path, max_size: float):
    """
    Build a scaled ReportLab Image for use inside a table cell.

    Scales the image proportionally so neither dimension exceeds max_size.
    Returns None if the file doesn't exist.
    """
    from reportlab.platypus import Image as RLImage

    image_path = (markdown_path.parent / image_target).resolve()
    if not image_path.exists():
        return None

    rl_image = RLImage(str(image_path))
    # Scale to fit within a square of max_size without distorting aspect ratio.
    width_ratio = max_size / rl_image.drawWidth if rl_image.drawWidth else 1
    height_ratio = max_size / rl_image.drawHeight if rl_image.drawHeight else 1
    scale_ratio = min(width_ratio, height_ratio, 1)
    rl_image.drawWidth *= scale_ratio
    rl_image.drawHeight *= scale_ratio
    return rl_image


def _build_scaled_image(image_path: Path, max_width: float):
    from reportlab.platypus import Image as RLImage

    if not image_path.exists():
        return None

    rl_image = RLImage(str(image_path))
    width_ratio = max_width / rl_image.drawWidth if rl_image.drawWidth else 1
    scale_ratio = min(width_ratio, 1)
    rl_image.drawWidth *= scale_ratio
    rl_image.drawHeight *= scale_ratio
    rl_image.hAlign = "CENTER"
    return rl_image


def _extract_html_figure_block(lines: List[str], start_index: int) -> tuple[str, int]:
    block_lines: List[str] = []
    i = start_index
    while i < len(lines):
        block_lines.append(lines[i])
        if HTML_FIGURE_END_PATTERN.match(lines[i].strip()):
            break
        i += 1
    return "\n".join(block_lines), min(i + 1, len(lines))


def _build_html_figure_flowables(block: str, markdown_path: Path, image_max_width: float):
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, Spacer

    image_tag = HTML_IMAGE_TAG_PATTERN.search(block)
    if not image_tag:
        return []

    src, alt_text, width_text = _parse_html_img_src(image_tag.group(0))
    if not src:
        return []

    image_target = _extract_target(src)
    image_path = (markdown_path.parent / image_target).resolve()
    if not image_path.exists():
        missing_style = ParagraphStyle(
            "FigureMissing",
            parent=getSampleStyleSheet()["BodyText"],
            fontSize=8,
            textColor=colors.grey,
        )
        return [Paragraph(_inline_markdown_to_paragraph_html(f"[Missing image: {image_target}]"), missing_style)]

    try:
        width_hint = float(width_text) if width_text else None
    except ValueError:
        width_hint = None

    if width_hint:
        image_max_width = min(image_max_width, width_hint / 96.0 * inch)

    rl_image = _build_scaled_image(image_path, image_max_width)
    if rl_image is None:
        return []

    caption_match = HTML_FIGCAPTION_PATTERN.search(block)
    caption = caption_match.group(1).strip() if caption_match else ""
    if not caption:
        caption = alt_text or image_path.stem.replace("_", " ")

    caption_style = ParagraphStyle(
        "FigureCaption",
        parent=getSampleStyleSheet()["BodyText"],
        fontName="Helvetica-Oblique",
        fontSize=7.8,
        leading=9.2,
        textColor=colors.grey,
        alignment=1,
        spaceBefore=2,
        spaceAfter=4,
    )
    return [rl_image, Paragraph(_inline_markdown_to_paragraph_html(caption), caption_style), Spacer(1, 0.02 * inch)]


def _build_table_cell(cell_text: str, paragraph_style, markdown_path: Path, image_max_size: float):
    """
    Build a ReportLab flowable for a single table cell.

    If the entire cell is an image link, return a scaled image; otherwise render as a Paragraph.
    """
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
    """
    Return fixed column widths for known table shapes, or None to let ReportLab auto-size.

    Hand-tuned to fit both table layouts on a US Letter page with 0.7" margins.
    """
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
    """Return column alignment overrides for known table shapes (numbers right-aligned)."""
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
    """
    Render a Markdown file to a PDF using ReportLab.

    Parses the markdown line-by-line and converts each element (headings,
    paragraphs, bullets, tables, images, code blocks) to the appropriate
    ReportLab flowable, then builds the document.
    """
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
    in_html_figure_block = False
    figure_lines: List[str] = []
    code_lines: List[str] = []
    # Tracks whether the last added flowable was a Spacer, to avoid double-spacing blank lines.
    last_was_spacer = False
    i = 0

    # Single-pass line processor: each element type is detected and handled in priority order.
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Toggle code block mode on ``` fences; flush accumulated lines when closing.
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

        if in_html_figure_block:
            figure_lines.append(line.rstrip())
            if HTML_FIGURE_END_PATTERN.match(stripped):
                block = "\n".join(figure_lines)
                flowables.extend(_build_html_figure_flowables(block, markdown_path, image_max_width=3.0 * inch))
                in_html_figure_block = False
                figure_lines = []
            i += 1
            continue

        # Skip HTML comment lines (e.g. the AUTO_ANNUAL_QUERY_TABLES markers).
        if HTML_COMMENT_PATTERN.match(stripped):
            i += 1
            continue

        if HTML_FIGURE_START_PATTERN.match(stripped):
            if HTML_FIGURE_END_PATTERN.match(stripped):
                flowables.extend(_build_html_figure_flowables(line.rstrip(), markdown_path, image_max_width=3.0 * inch))
                last_was_spacer = True
            else:
                in_html_figure_block = True
                figure_lines = [line.rstrip()]
            i += 1
            continue

        if HTML_IMAGE_TAG_PATTERN.fullmatch(stripped):
            flowables.extend(_build_html_figure_flowables(f"<figure>{line.rstrip()}</figure>", markdown_path, image_max_width=3.0 * inch))
            last_was_spacer = True
            i += 1
            continue

        # Detect a Markdown table: header row followed immediately by a separator row.
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
                repeatRows=1,  # Repeat the header row on each new page
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
            # Product image columns need CENTER/MIDDLE alignment — applied as an override.
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
                normalized_target = image_target.replace("\\", "/").lower()
                max_width = 3.0 * inch if "product_images/" in normalized_target else 6.7 * inch
                rl_image = _build_scaled_image(image_path, max_width)
                if rl_image is None:
                    i += 1
                    continue
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
    parser.add_argument("--output-dir", required=True, help="Path to the local output folder")
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
