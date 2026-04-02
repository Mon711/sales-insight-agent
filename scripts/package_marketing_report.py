#!/usr/bin/env python3
"""
Bundle report assets and export a PDF version of the marketing report.

This script solves the "broken image links after export" issue by:
1. Copying referenced image assets into the Desktop report folder.
2. Rewriting Markdown image paths to local relative paths.
3. Rendering a PDF from the updated Markdown (when reportlab is installed).
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


def _extract_target(raw_target: str) -> str:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1].strip()

    # Handle optional markdown image title suffix: (path "title")
    if " \"" in target and target.endswith('"'):
        maybe_path, _ = target.rsplit(" \"", 1)
        target = maybe_path.strip()

    return target


def _is_remote_target(target: str) -> bool:
    lowered = target.lower()
    return lowered.startswith("http://") or lowered.startswith("https://") or lowered.startswith("data:")


def _find_image_source(
    *,
    target: str,
    markdown_path: Path,
    reports_dir: Path,
    output_dir: Path,
) -> Path | None:
    if _is_remote_target(target):
        return None

    path_obj = Path(target)
    candidates: List[Path] = []

    if path_obj.is_absolute():
        candidates.append(path_obj)
    else:
        candidates.append((markdown_path.parent / path_obj).resolve())
        candidates.append((output_dir / path_obj).resolve())
        candidates.append((reports_dir / path_obj).resolve())

    # Explicit support for report assets that commonly use assets/... paths.
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
        # For non-standard sources, keep them grouped but still portable.
        destination = output_assets_dir / "external" / source.name

    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        shutil.copy2(source, destination)
    return destination


def bundle_markdown_assets(markdown_path: Path, reports_dir: Path, output_dir: Path) -> Tuple[int, int]:
    text = markdown_path.read_text(encoding="utf-8")
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

        # Keep local output images unchanged (for example chart PNGs already in output_dir).
        try:
            source.resolve().relative_to(output_dir.resolve())
            return match.group(0)
        except ValueError:
            pass

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
    return copied_count, rewritten_count


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
        from reportlab.platypus import Paragraph, Preformatted, SimpleDocTemplate, Spacer
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

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("```"):
            if in_code_block:
                flowables.append(Preformatted("\n".join(code_lines), code_style))
                flowables.append(Spacer(1, 0.12 * inch))
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line.rstrip())
            continue

        if not stripped:
            flowables.append(Spacer(1, 0.08 * inch))
            continue

        image_match = IMAGE_LINK_PATTERN.fullmatch(stripped)
        if image_match:
            image_target = _extract_target(image_match.group(2))
            image_path = (markdown_path.parent / image_target).resolve()
            if image_path.exists():
                rl_image = RLImage(str(image_path))
                max_width = 7.0 * inch
                if rl_image.drawWidth > max_width:
                    ratio = max_width / rl_image.drawWidth
                    rl_image.drawWidth = max_width
                    rl_image.drawHeight = rl_image.drawHeight * ratio
                flowables.append(rl_image)
                flowables.append(Spacer(1, 0.10 * inch))
            else:
                note = _inline_markdown_to_paragraph_html(f"[Missing image: {image_target}]")
                flowables.append(Paragraph(note, body_style))
            continue

        heading_match = HEADING_PATTERN.match(stripped)
        if heading_match:
            level = min(len(heading_match.group(1)), 3)
            content = _inline_markdown_to_paragraph_html(heading_match.group(2))
            flowables.append(Paragraph(content, heading_styles[level]))
            continue

        unordered_match = UNORDERED_BULLET_PATTERN.match(line)
        if unordered_match:
            content = _inline_markdown_to_paragraph_html(unordered_match.group(1))
            flowables.append(Paragraph(f"• {content}", body_style))
            continue

        ordered_match = ORDERED_BULLET_PATTERN.match(line)
        if ordered_match:
            content = _inline_markdown_to_paragraph_html(ordered_match.group(1))
            flowables.append(Paragraph(content, body_style))
            continue

        flowables.append(Paragraph(_inline_markdown_to_paragraph_html(line), body_style))

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

    copied_count, rewritten_count = bundle_markdown_assets(markdown_path, reports_dir, output_dir)
    print(f"Bundled assets copied: {copied_count}, links rewritten: {rewritten_count}")

    try:
        export_pdf(markdown_path, pdf_path)
        print(f"PDF exported: {pdf_path}")
    except Exception as e:
        print(f"WARNING: PDF export skipped: {e}", file=sys.stderr)
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
