---
name: pdf-stylist
description: Prepare markdown reports for polished executive PDFs with structured sections, concise bullets, controlled page breaks, dashboard-style tables, and local images. Use when generating or polishing a PDF, packaging a markdown report into PDF, or turning raw report analysis into an executive-level business report.
---

# PDF Stylist

Use this skill to turn analysis into PDF-ready markdown that reads like a consulting report and renders cleanly through `scripts/package_marketing_report.py`.

## Core Rule

Do not just reword the draft. Rebuild it into a structured layout system that is compact enough to survive ReportLab rendering without overflowing pages or forcing awkward table splits.

## Workflow

1. Start from the analysis output and identify the major story.
2. Rewrite into a title, then ordered H2 sections, then tight H3 subpoints.
3. Convert long paragraphs into bullets and short sentences.
4. Keep each paragraph to 2-3 lines when possible.
5. Place tables and images in their own blocks.
6. Remove repetition, filler, and any data dump behavior.
7. End with concrete actions and owner-oriented next steps.
8. Keep the first page executive-summary focused, with no giant intro block before the report’s actual findings.

## Layout System

- Use one clear title at the top.
- Use `##` for major sections and `###` for mini-insights or subtopics.
- Group content into:
  - Insight
  - Why it matters
  - Action
- Keep the report insight-first, not chronology-first.
- Prefer scannable bullets over dense prose.
- Keep the final tone concise, executive, and practical.
- Use flat bullet lists only. Avoid nested bullets and avoid elaborate indentation patterns that turn into visual clutter in PDF.

## Typography And Spacing

- Write short paragraphs.
- Use bold only for emphasis, not decoration.
- Leave a small gap within a section and a larger gap between sections.
- Avoid huge whitespace blocks and avoid cramped stacks of text.
- Keep section transitions tight. The PDF should feel compact, not airy.

## Tables

- Use simple markdown tables only.
- Keep tables close to the section that explains them.
- Let numeric columns stay numeric and avoid wrapping them in extra prose.
- Prefer dashboard-style tables with clear headers and compact rows.
- Do not bury a table inside a paragraph or bullet.
- Keep performer tables faithful to the source query output. Do not add columns that were not returned by ShopifyQL.
- If a table is wide, shorten surrounding prose rather than expanding the table with extra helper columns.

## Images

- Use local image paths only.
- Keep images large enough to read clearly.
- Place images near the relevant insight.
- Center the visual narrative by keeping images isolated from dense text.
- Never use remote CDN image links in the PDF-ready draft.
- Avoid stacking too many images back-to-back without nearby interpretation.

## Page Break Discipline

- Break only after a full section ends.
- Break before large tables or a new major topic.
- Never break between a heading and its content.
- Never break inside a paragraph or inside a table.

## Integration

When the workflow is producing a PDF:

1. Use `$marketing-analyst` for the analytical draft.
2. Use `$pdf-stylist` for the final markdown rewrite.
3. Then let `scripts/package_marketing_report.py` render the PDF.

## Quality Check

Before finalizing, confirm:

- the report has a clear hierarchy
- every section has a purpose
- paragraphs are short
- tables are clean
- images are local and purposeful
- the result feels like an executive business report, not a raw export
- the first page reads like a polished executive summary, not a pasted data dump
