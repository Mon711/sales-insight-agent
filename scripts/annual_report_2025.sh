#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

tmp_log_dir="$(mktemp -d "${TMPDIR:-/tmp}/annual_report_logs.XXXXXX")"
run_reports_log="$tmp_log_dir/run_reports.log"

echo "[1/3] Fetching latest Shopify reports (including annual 2025 report)..."
if ! python run_reports.py >"$run_reports_log" 2>&1; then
  echo "Report fetch failed. See log: $run_reports_log" >&2
  exit 1
fi

latest_report_dir="$(ls -td reports/files_generation_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${latest_report_dir:-}" ]]; then
  echo "No reports/files_generation_* folder found." >&2
  exit 1
fi

annual_json="$latest_report_dir/annual_report_2025.json"
if [[ ! -f "$annual_json" ]]; then
  echo "Expected annual report not found: $annual_json" >&2
  echo "See log: $run_reports_log" >&2
  exit 1
fi

report_folder_name="$(basename "$latest_report_dir")"
report_number="${report_folder_name#files_generation_}"
output_dir="$HOME/Desktop/eddy_annual_insights_${report_number}"
codex_log="$output_dir/codex_generation.log"
package_log="$output_dir/report_packaging.log"

mkdir -p "$output_dir"

echo "[2/3] Asking Codex to write the annual 2025 Markdown report..."
codex exec --cd "$repo_root" --full-auto --color never \
  -m gpt-5.4 \
  -c 'model_reasoning_effort="medium"' \
  --add-dir "$latest_report_dir" \
  --output-last-message "$output_dir/ANNUAL_REPORT_2025.md" \
  "Read annual_report_2025.json from $latest_report_dir and generate a concise executive report for 2025. Include sections for Top 20 Performers, Top 20 Underperformers, and Top 20 Categories. Analyze the numbers with practical implications and clear actions. Use whichever return metric fields are available in the rows (for example returned_quantity_rate or returns). Add a dedicated section with product images for top 5 dresses and bottom 5 dresses using dress_image_focus.top_5_dresses and dress_image_focus.bottom_5_dresses. Embed actual markdown images from product_image.local_path and keep the visual section compact and clean. Do not include category images. Return only markdown with no preamble or process notes." >"$codex_log" 2>&1 &
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

echo "[3/3] Bundling assets and exporting PDF..."
if python scripts/package_marketing_report.py \
  --markdown "$output_dir/ANNUAL_REPORT_2025.md" \
  --reports-dir "$latest_report_dir" \
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
