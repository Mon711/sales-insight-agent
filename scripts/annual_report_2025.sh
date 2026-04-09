#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

next_output_number() {
  local max_num=0
  while IFS= read -r dir; do
    local base num
    base="$(basename "$dir")"
    num="${base##*_}"
    if [[ "$num" =~ ^[0-9]+$ ]] && (( num > max_num )); then
      max_num="$num"
    fi
  done < <(find "$HOME/Desktop" -maxdepth 1 -type d -name "eddy_annual_insights_*" 2>/dev/null || true)

  echo $((max_num + 1))
}

report_number="$(next_output_number)"
output_dir="$HOME/Desktop/eddy_annual_insights_${report_number}"
reports_base_dir="$output_dir/report_source"
report_assets_dir="$output_dir/report_assets"

mkdir -p "$output_dir"
mkdir -p "$reports_base_dir"
mkdir -p "$report_assets_dir"

run_reports_log="$output_dir/run_reports.log"
codex_log="$output_dir/codex_generation.log"
package_log="$output_dir/report_packaging.log"

echo "[1/3] Fetching latest Shopify annual report data..."
if ! REPORTS_BASE_DIR="$reports_base_dir" REPORT_OUTPUT_DIR="$output_dir" python run_reports.py >"$run_reports_log" 2>&1; then
  echo "Report fetch failed. See log: $run_reports_log" >&2
  exit 1
fi

annual_json="$reports_base_dir/annual_report_2025.json"
if [[ ! -f "$annual_json" ]]; then
  echo "Expected annual report not found: $annual_json" >&2
  echo "See log: $run_reports_log" >&2
  exit 1
fi

echo "[2/3] Asking Codex to write the annual 2025 Markdown report..."
codex exec --cd "$repo_root" --full-auto --color never \
  -m gpt-5.4 \
  -c 'model_reasoning_effort="medium"' \
  --add-dir "$reports_base_dir" \
  --output-last-message "$output_dir/ANNUAL_REPORT_2025.md" \
  "Activate the marketing-analyst skill. Read annual_report_2025.json from $reports_base_dir. Write a concise executive report with these sections: Executive Summary, Methodology And Data Window, Top Performer Insights, Underperformer Insights, Category Insights, and Recommendations And Next Actions. Add deeper interpretation of dress/category performance, include visual fabric/style inference where appropriate (label as inference), and include stronger marketing recommendations tied to the report numbers and practical industry standards. Do not output raw query tables. Do not embed any product images anywhere in the narrative. The pipeline will inject the canonical query tables with thumbnail images separately. You may still use product_image_focus.top_5_products, product_image_focus.bottom_5_products, top_performers.rows, and underperformers.rows as evidence for your analysis. Return only markdown with no preamble or process notes." >"$codex_log" 2>&1 &
codex_pid=$!
start_ts=$(date +%s)
while kill -0 "$codex_pid" 2>/dev/null; do
  now_ts=$(date +%s)
  elapsed=$((now_ts - start_ts))
  printf "\r[2/3] Generating report... %ss elapsed" "$elapsed"
  sleep 10
done
printf "\r[2/3] Generating report... done.            \n"

if ! wait "$codex_pid"; then
  echo "Codex report generation failed. See log: $codex_log" >&2
  exit 1
fi

if [[ ! -s "$output_dir/ANNUAL_REPORT_2025.md" ]]; then
  echo "Codex finished, but ANNUAL_REPORT_2025.md was not created or is empty." >&2
  exit 1
fi

echo "[2.5/3] Ensuring query result tables are included..."
if ! python scripts/ensure_annual_tables.py \
  --markdown "$output_dir/ANNUAL_REPORT_2025.md" \
  --annual-json "$annual_json"; then
  echo "Failed to inject annual query tables into markdown." >&2
  exit 1
fi

echo "[3/3] Bundling assets and exporting PDF..."
if python scripts/package_marketing_report.py \
  --markdown "$output_dir/ANNUAL_REPORT_2025.md" \
  --reports-dir "$reports_base_dir" \
  --output-dir "$output_dir" \
  --pdf-name "ANNUAL_REPORT_2025.pdf" >"$package_log" 2>&1; then
  if [[ -s "$output_dir/ANNUAL_REPORT_2025.pdf" ]]; then
    echo "Done. Report saved to $output_dir/ANNUAL_REPORT_2025.md and $output_dir/ANNUAL_REPORT_2025.pdf"
  else
    echo "Done. Report saved to $output_dir/ANNUAL_REPORT_2025.md (PDF was skipped; see $package_log)"
  fi
else
  echo "Report markdown created, but packaging/PDF export had issues. See log: $package_log" >&2
  echo "Report saved to $output_dir/ANNUAL_REPORT_2025.md"
fi

echo "Logs: $run_reports_log, $codex_log, $package_log"
