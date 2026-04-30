#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

output_root="${REPORT_OUTPUT_ROOT:-/Users/mrinalsood/temp}"

normalize_brand_slug() {
  local value="${1:-}"
  value="${value#/}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="$(printf '%s' "$value" | sed -E 's#[^a-z0-9]+#-#g; s/^-+|-+$//g')"
  printf '%s\n' "$value"
}

normalize_season_slug() {
  local value="${1:-}"
  value="${value#/}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="${value//\'/}"
  value="$(printf '%s' "$value" | sed -E 's#[^a-z0-9]+##g')"
  printf '%s\n' "$value"
}

brand_display_name() {
  local slug="${1:-}"
  case "$slug" in
    eddy) echo "Eddy" ;;
    steele) echo "Steele" ;;
    *) printf '%s\n' "$slug" | awk '{print toupper(substr($0,1,1)) substr($0,2)}' ;;
  esac
}

season_display_name() {
  local slug="${1:-}"
  case "$slug" in
    winter25) echo "Winter'25" ;;
    spring25) echo "Spring'25" ;;
    summer25) echo "Summer'25" ;;
    resort25) echo "Resort'25" ;;
    autumn25) echo "Autumn'25" ;;
    winter26) echo "Winter'26" ;;
    essentials25) echo "Essentials'25" ;;
    essentials26) echo "Essentials'26" ;;
    autumn26) echo "Autumn'26" ;;
    resort24) echo "Resort'24" ;;
    *) printf '%s\n' "$slug" | awk '{print toupper(substr($0,1,1)) substr($0,2)}' ;;
  esac
}

next_output_number() {
  local brand_slug="$1"
  local season_slug="$2"
  local max_num=0
  while IFS= read -r dir; do
    local base num
    base="$(basename "$dir")"
    num="${base##*_}"
    if [[ "$num" =~ ^[0-9]+$ ]] && (( num > max_num )); then
      max_num="$num"
    fi
  done < <(find "$output_root" -maxdepth 1 -type d -name "${brand_slug}_${season_slug}_insights_*" 2>/dev/null || true)

  echo $((max_num + 1))
}

brand_slug_input="${1:-${REPORT_BRAND_SLUG:-steele}}"
season_slug_input="${2:-${REPORT_SEASON_SLUG:-winter25}}"
brand_slug="$(normalize_brand_slug "$brand_slug_input")"
season_slug="$(normalize_season_slug "$season_slug_input")"
brand_name="${REPORT_BRAND_DISPLAY_NAME:-$(brand_display_name "$brand_slug")}"
season_name="${REPORT_SEASON_DISPLAY_NAME:-$(season_display_name "$season_slug")}"
report_number="$(next_output_number "$brand_slug" "$season_slug")"
mkdir -p "$output_root"
output_dir="$output_root/${brand_slug}_${season_slug}_insights_${report_number}"
reports_base_dir="$output_dir/report_source"
report_assets_dir="$output_dir/report_assets"

mkdir -p "$output_dir"
mkdir -p "$reports_base_dir"
mkdir -p "$report_assets_dir"

run_reports_log="$output_dir/run_season_reports.log"
codex_log="$output_dir/codex_generation.log"
package_log="$output_dir/report_packaging.log"
codex_model="${SEASON_REPORT_MODEL:-gpt-5.4}"
codex_reasoning_effort="${SEASON_REPORT_REASONING_EFFORT:-medium}"

echo "[1/3] Fetching season report data for $brand_name ($season_name)..."
if ! REPORT_BRAND_SLUG="$brand_slug" \
  REPORT_BRAND_DISPLAY_NAME="$brand_name" \
  REPORT_SEASON_SLUG="$season_slug" \
  REPORT_SEASON_DISPLAY_NAME="$season_name" \
  REPORTS_BASE_DIR="$reports_base_dir" \
  REPORT_OUTPUT_DIR="$output_dir" \
  python run_season_reports.py >"$run_reports_log" 2>&1; then
  echo "Season report fetch failed. See log: $run_reports_log" >&2
  exit 1
fi

season_json="$reports_base_dir/${brand_slug}_${season_slug}_report.json"
if [[ ! -f "$season_json" ]]; then
  echo "Expected season report not found: $season_json" >&2
  echo "See log: $run_reports_log" >&2
  exit 1
fi

markdown_output="$output_dir/${brand_slug}_${season_slug}_report.md"
pdf_output="$output_dir/${brand_slug}_${season_slug}_report.pdf"

echo "[2/3] Asking Codex to write the season report for $brand_name ($season_name)..."
echo "Using Codex model: $codex_model (reasoning effort: $codex_reasoning_effort)"
codex exec --cd "$repo_root" --full-auto --color never \
  -m "$codex_model" \
  -c "model_reasoning_effort=\"$codex_reasoning_effort\"" \
  --add-dir "$output_dir" \
  --output-last-message "$markdown_output" \
  "Activate the marketing-analyst skill for the analysis. Read ${season_json} and inspect the local product images under ${report_assets_dir}/product_images/${brand_slug}_${season_slug}/. Write one Markdown report for designers and creative directors, not a data dump. The report must use these sections: Executive Summary, Methodology and Data Window, Season-wise Performance, Product-level Analysis, Silhouette Analysis, Colour Analysis, Print Analysis, Fabric Analysis, Use Case Analysis, Returns Analysis, Core Silhouettes, Product Gaps, and Recommendations for Next Collection. Analyze every product row in the JSON and every available product image visually. Do not limit the narrative to top sellers, bottom sellers, top 10, bottom 10, or any other sample slice; those slices are only helper views. Include relevant local image embeds near the related discussion using product_image.local_path. If an image is unclear, say so explicitly. If fabric composition is missing, label any visual fabric read as an inference. Compare sales, units, returns, return rate, and discounting when available. Give every product a clear verdict such as worked well, worked moderately, did not work, commercially risky, design-led but weak sales, strong sales but high returns, good candidate to repeat, or avoid / redesign. Keep the tone designer-friendly and concise. Return only markdown with no preamble or process notes." >"$codex_log" 2>&1 &
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
  echo "Codex season report generation failed. See log: $codex_log" >&2
  exit 1
fi

if [[ ! -s "$markdown_output" ]]; then
  echo "Codex finished, but $markdown_output was not created or is empty." >&2
  exit 1
fi

echo "[3/3] Bundling assets and exporting PDF..."
if python scripts/package_marketing_report.py \
  --markdown "$markdown_output" \
  --reports-dir "$reports_base_dir" \
  --output-dir "$output_dir" \
  --pdf-name "$(basename "$pdf_output")" >"$package_log" 2>&1; then
  if [[ -s "$pdf_output" ]]; then
    echo "Done. Report saved to $markdown_output and $pdf_output"
  else
    echo "Done. Report saved to $markdown_output (PDF was skipped; see $package_log)"
  fi
else
  echo "Report markdown created, but packaging/PDF export had issues. See log: $package_log" >&2
  echo "Report saved to $markdown_output"
fi

echo "Logs: $run_reports_log, $codex_log, $package_log"
