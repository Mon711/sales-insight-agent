#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

chart_title() {
  local filename="$1"
  local base="${filename%.png}"
  echo "${base//_/ }"
}

append_missing_chart_embeds() {
  local report_file="$1"
  local output_dir="$2"
  local -a chart_files=(
    "channel_sales_comparison.png"
    "top_products_performance.png"
    "sales_efficiency.png"
    "average_order_value_by_channel.png"
    "product_concentration_by_channel.png"
    "return_burden_by_channel.png"
  )
  local -a missing=()

  for chart in "${chart_files[@]}"; do
    [[ -f "$output_dir/$chart" ]] || continue
    if ! rg -Fq "$chart" "$report_file"; then
      missing+=("$chart")
    fi
  done

  if (( ${#missing[@]} == 0 )); then
    return
  fi

  {
    echo
    echo "## Supporting Charts"
    echo
    echo "The following charts were generated for this report:"
    echo
    for chart in "${missing[@]}"; do
      local title
      title="$(chart_title "$chart")"
      echo "### $title"
      echo
      echo "![${title}](${chart})"
      echo
    done
  } >> "$report_file"
}

tmp_log_dir="$(mktemp -d "${TMPDIR:-/tmp}/marketing_report_logs.XXXXXX")"
run_reports_log="$tmp_log_dir/run_reports.log"

echo "[1/3] Fetching the latest Shopify reports..."
if ! python run_reports.py >"$run_reports_log" 2>&1; then
  echo "Report fetch failed. See log: $run_reports_log" >&2
  exit 1
fi

latest_report_dir="$(ls -td reports/files_generation_* 2>/dev/null | head -n 1 || true)"
if [[ -z "${latest_report_dir:-}" ]]; then
  echo "No reports/files_generation_* folder found." >&2
  exit 1
fi

report_folder_name="$(basename "$latest_report_dir")"
report_number="${report_folder_name#files_generation_}"
output_dir="$HOME/Desktop/eddy_marketing_insights_${report_number}"
charts_log="$output_dir/charts_generation.log"
codex_log="$output_dir/codex_generation.log"

echo "[2/3] Generating charts from $latest_report_dir..."
mkdir -p "$output_dir"
if ! python src/visualizer.py "$latest_report_dir" >"$charts_log" 2>&1; then
  echo "Chart generation failed. See log: $charts_log" >&2
  exit 1
fi

echo "[3/3] Asking Codex to write the Markdown report..."
codex exec --cd "$repo_root" --full-auto --color never \
  --add-dir "$output_dir" \
  --output-last-message "$output_dir/MARKETING_REPORT.md" \
  "Activate the marketing-analyst skill. Read the newest reports in $latest_report_dir and the generated charts in $output_dir. Use separate sections for Online Store, POS, Wholesale, and Dropship/Partner channels. Include a snapshot, the best and weakest products or themes, the key risks, and the practical implications for Eddy in each section. End with a cross-channel aggregate analysis and concrete recommendations for marketing, design, merchandising, and brand strategy. Use plain English and note when a metric is a heuristic rather than a hard benchmark. Incorporate the generated charts directly in the markdown with relative image embeds (e.g. ![Chart](channel_sales_comparison.png)) and refer to them in the analysis. Return only the Markdown content for the report, with no preamble, no bullet summary about the process, and no extra commentary." >"$codex_log" 2>&1 &
codex_pid=$!
start_ts=$(date +%s)
while kill -0 "$codex_pid" 2>/dev/null; do
  now_ts=$(date +%s)
  elapsed=$((now_ts - start_ts))
  printf "\r[3/3] Generating report... %ss elapsed" "$elapsed"
  sleep 10
done
printf "\r[3/3] Generating report... done.            \n"

if ! wait "$codex_pid"; then
  echo "Codex report generation failed. See log: $codex_log" >&2
  exit 1
fi

if [[ -s "$output_dir/MARKETING_REPORT.md" ]]; then
  append_missing_chart_embeds "$output_dir/MARKETING_REPORT.md" "$output_dir"
  echo "Done. Report saved to $output_dir/MARKETING_REPORT.md"
  echo "Logs: $run_reports_log, $charts_log, $codex_log"
else
  echo "Codex finished, but MARKETING_REPORT.md was not created or is empty." >&2
  exit 1
fi
