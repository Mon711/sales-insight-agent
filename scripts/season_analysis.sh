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

season_family_slug() {
  local value="${1:-}"
  value="${value#/}"
  value="$(printf '%s' "$value" | tr '[:upper:]' '[:lower:]')"
  value="${value//\'/}"
  value="$(printf '%s' "$value" | sed -E 's#[^a-z0-9]+##g; s/[0-9]+$//')"
  printf '%s\n' "$value"
}

season_family_display_name() {
  local value="${1:-}"
  value="$(season_family_slug "$value")"
  if [[ -z "$value" ]]; then
    echo "Season"
  else
    printf '%s\n' "$value" | awk '{print toupper(substr($0,1,1)) substr($0,2)}'
  fi
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
brand_slug="$(normalize_brand_slug "$brand_slug_input")"
brand_name="${REPORT_BRAND_DISPLAY_NAME:-$(brand_display_name "$brand_slug")}"

if [[ $# -gt 0 ]]; then
  shift || true
fi

season_slugs=("$@")
if [[ ${#season_slugs[@]} -eq 0 ]]; then
  season_slugs=("${REPORT_SEASON_SLUG:-winter25}")
fi
if [[ ${#season_slugs[@]} -gt 2 ]]; then
  echo "Usage: ./scripts/season_analysis.sh <brand> <season> [comparison_season]" >&2
  exit 1
fi

normalized_seasons=()
for season in "${season_slugs[@]}"; do
  normalized_seasons+=("$(normalize_season_slug "$season")")
done

if [[ -z "${normalized_seasons[0]}" ]]; then
  echo "Season slug is required." >&2
  exit 1
fi

comparison_mode=false
if [[ ${#normalized_seasons[@]} -eq 2 ]]; then
  comparison_mode=true
  family_a="$(season_family_slug "${normalized_seasons[0]}")"
  family_b="$(season_family_slug "${normalized_seasons[1]}")"
  if [[ -z "$family_a" || "$family_a" != "$family_b" ]]; then
    echo "Comparison mode requires two seasons from the same family, such as winter25 and winter26." >&2
    exit 1
  fi
fi

season_primary_slug="${normalized_seasons[0]}"
season_primary_name="${REPORT_SEASON_DISPLAY_NAME:-$(season_display_name "$season_primary_slug")}"
season_secondary_slug="${normalized_seasons[1]:-}"
season_secondary_name="${season_secondary_slug:+$(season_display_name "$season_secondary_slug")}"

if [[ "$comparison_mode" == true ]]; then
  output_slug="${season_primary_slug}_${season_secondary_slug}"
  report_title_family="$(season_family_display_name "$season_primary_slug")"
else
  output_slug="$season_primary_slug"
  report_title_family="$(season_display_name "$season_primary_slug")"
fi

report_number="$(next_output_number "$brand_slug" "$output_slug")"
mkdir -p "$output_root"
output_dir="$output_root/${brand_slug}_${output_slug}_insights_${report_number}"
reports_base_dir="$output_dir/report_source"
report_assets_dir="$output_dir/report_assets"

mkdir -p "$output_dir"
mkdir -p "$reports_base_dir"
mkdir -p "$report_assets_dir"

run_reports_log="$output_dir/run_season_reports.log"
codex_log="$output_dir/codex_generation.log"
package_log="$output_dir/report_packaging.log"
codex_model="${MODEL:-gpt-5.4}"
codex_reasoning_effort="${REASONING_EFFORT:-medium}"

fetch_season_report() {
  local season_slug="$1"
  local season_name="$2"
  local reports_dir="$3"

  mkdir -p "$reports_dir"
  if ! REPORT_BRAND_SLUG="$brand_slug" \
    REPORT_BRAND_DISPLAY_NAME="$brand_name" \
    REPORT_SEASON_SLUG="$season_slug" \
    REPORT_SEASON_DISPLAY_NAME="$season_name" \
    REPORTS_BASE_DIR="$reports_dir" \
    REPORT_OUTPUT_DIR="$output_dir" \
    python run_season_reports.py >>"$run_reports_log" 2>&1; then
    return 1
  fi
  return 0
}

build_single_prompt() {
  local season_json="$1"
  local season_slug="$2"
  cat <<EOF
Activate the season-product-analyst skill for the analysis. Read ${season_json} and inspect the local product images under report_assets/product_images/${brand_slug}_${season_slug}/. Write one visual-first Markdown report for designers, merchandisers, Varun, and the creative director.

Use exactly these sections: Executive visual summary, Methodology and data confidence note, Season performance snapshot, Product performance cards, Hero product grid, Underperformer/risk product grid, Silhouette grid, Colour board, Print board, Fabric/material evidence table, Use-case map, Returns-as-design-feedback table, Core repeatable ideas, Product gaps, Recommendations for next collection.

Evidence rules:
- ShopifyQL sales, returns, discounts, and units are the commercial source of truth.
- Admin GraphQL product descriptions, tags, selected options, and metafields are official product-detail sources.
- Local product images are visual evidence and should be used as a separate visual/design interpretation layer, not only as a backup.
- Analyze the full season dataset, not only top/bottom helper slices.
- Helper slices can support visual summaries, but conclusions must come from all rows.
- Use product_detail.official_product_attributes where available for official material, colour, fit, neckline, sleeve, product features, product size, origin, and collection evidence.
- Exact fabric composition and fibre percentages must only be shown if found in official product data. If exact composition is missing, write: Official composition: Unknown.
- If image-based fabric interpretation is used, label it: Visual inference.
- Never invent fabric composition, fibre percentages, care instructions, customer return reasons, or unsupported qualitative claims.
- Return-related design causes are hypotheses unless directly supported by customer return reasons.

Visual-first Markdown rules:
- Use compact tables, product cards, grids, and figure blocks.
- Include more product images near the relevant insight using product_image.local_path only.
- Keep product images small to medium; use concise captions.
- If image is missing, say image unavailable. If image is unclear, say image unclear.
- Do not mention absolute local filesystem paths.
- Do not use CDN image links.
- Avoid long text-only sections and generic AI-style deck language.

Product cards should include, where available: product image, product title, net sales, units sold, return rate, discount rate, official material/fabric, visual design read, and verdict. Allowed verdicts include Protect, Repeat, Refine, Redesign, Reduce, Avoid, Watch, Design-led but commercially weak, Strong sales but high returns, Good idea, weak execution, Commercially strong, fit-risk, and Visual hero, margin-risk.

Return only Markdown with no preamble, no process notes, and no tool logs.
EOF
}

build_comparison_prompt() {
  local comparison_json="$1"
  local season_a_slug="$2"
  local season_b_slug="$3"
  local season_a_name="$4"
  local season_b_name="$5"
  cat <<EOF
Activate the season-product-analyst skill for the analysis. Read ${comparison_json} and inspect the local product images under report_assets/product_images/${brand_slug}_${season_a_slug}/ and report_assets/product_images/${brand_slug}_${season_b_slug}/. Write one visual-first Markdown report for designers, merchandisers, Varun, and the creative director. This is a same-family cross-year comparison for ${season_a_name} versus ${season_b_name}; compare the same season across years rather than analyzing one season in isolation.

Use exactly these sections: Side-by-side season summary cards, Methodology and data confidence note, Category mix comparison, Hero product comparison grid, Repeated-style case studies if repeated styles exist, Silhouette comparison grid, Colour arc comparison, Print engine comparison, Fabric/material evidence comparison, Use-case comparison, Returns comparison, Diagnostic matrix, Next collection playbook.

Evidence rules:
- ShopifyQL sales, returns, discounts, and units are the commercial source of truth.
- Admin GraphQL product descriptions, tags, selected options, and metafields are official product-detail sources.
- Local product images are visual evidence and should be used as a separate visual/design interpretation layer, not only as a backup.
- Analyze every product row in both seasons, not only top/bottom helper slices.
- Helper slices can support visual summaries, but conclusions must come from all rows.
- Use product_detail.official_product_attributes where available for official material, colour, fit, neckline, sleeve, product features, product size, origin, and collection evidence.
- Exact fabric composition and fibre percentages must only be shown if found in official product data. If exact composition is missing, write: Official composition: Unknown.
- If image-based fabric interpretation is used, label it: Visual inference.
- Never invent fabric composition, fibre percentages, care instructions, customer return reasons, or unsupported qualitative claims.
- Return-related design causes are hypotheses unless directly supported by customer return reasons.

Visual-first Markdown rules:
- Use compact tables, product cards, grids, figure blocks, side-by-side cards, and concise captions.
- Include product images near the relevant insight using product_image.local_path only.
- Keep product images small to medium.
- If image is missing, say image unavailable. If image is unclear, say image unclear.
- Do not mention absolute local filesystem paths.
- Do not use CDN image links.
- Avoid long text-only sections and generic AI-style deck language.

Product cards should include, where available: product image, product title, net sales, units sold, return rate, discount rate, official material/fabric, visual design read, and verdict. Allowed verdicts include Protect, Repeat, Refine, Redesign, Reduce, Avoid, Watch, Design-led but commercially weak, Strong sales but high returns, Good idea, weak execution, Commercially strong, fit-risk, and Visual hero, margin-risk.

Return only Markdown with no preamble, no process notes, and no tool logs.
EOF
}

markdown_output="$output_dir/${brand_slug}_${output_slug}_report.md"
pdf_output="$output_dir/${brand_slug}_${output_slug}_report.pdf"

echo "[1/3] Fetching season report data for $brand_name..."
if [[ "$comparison_mode" == true ]]; then
  season_a_reports_dir="$reports_base_dir/$season_primary_slug"
  season_b_reports_dir="$reports_base_dir/$season_secondary_slug"
  if ! fetch_season_report "$season_primary_slug" "$season_primary_name" "$season_a_reports_dir"; then
    echo "Season report fetch failed for $season_primary_slug. See log: $run_reports_log" >&2
    exit 1
  fi
  if ! fetch_season_report "$season_secondary_slug" "$season_secondary_name" "$season_b_reports_dir"; then
    echo "Season report fetch failed for $season_secondary_slug. See log: $run_reports_log" >&2
    exit 1
  fi

  season_a_json="$season_a_reports_dir/${brand_slug}_${season_primary_slug}_report.json"
  season_b_json="$season_b_reports_dir/${brand_slug}_${season_secondary_slug}_report.json"
  comparison_json="$reports_base_dir/${brand_slug}_${output_slug}_comparison_report.json"
  if [[ ! -f "$season_a_json" || ! -f "$season_b_json" ]]; then
    echo "Expected season reports were not created." >&2
    exit 1
  fi
  echo "[2/3] Combining season reports for comparison..."
  if ! python scripts/merge_season_reports.py \
    --brand-slug "$brand_slug" \
    --brand-display-name "$brand_name" \
    --family-slug "$(season_family_slug "$season_primary_slug")" \
    --family-display-name "$report_title_family" \
    --season-a-json "$season_a_json" \
    --season-b-json "$season_b_json" \
    --output "$comparison_json" >>"$run_reports_log" 2>&1; then
    echo "Comparison payload generation failed. See log: $run_reports_log" >&2
    exit 1
  fi

  echo "[2/3] Asking Codex to write the comparative report for $brand_name ($season_primary_name vs $season_secondary_name)..."
  echo "Using Codex model: $codex_model (reasoning effort: $codex_reasoning_effort)"
  prompt="$(build_comparison_prompt "$comparison_json" "$season_primary_slug" "$season_secondary_slug" "$season_primary_name" "$season_secondary_name")"
else
  if ! fetch_season_report "$season_primary_slug" "$season_primary_name" "$reports_base_dir"; then
    echo "Season report fetch failed. See log: $run_reports_log" >&2
    exit 1
  fi
  season_json="$reports_base_dir/${brand_slug}_${season_primary_slug}_report.json"
  if [[ ! -f "$season_json" ]]; then
    echo "Expected season report not found: $season_json" >&2
    echo "See log: $run_reports_log" >&2
    exit 1
  fi

  echo "[2/3] Asking Codex to write the season report for $brand_name ($season_primary_name)..."
  echo "Using Codex model: $codex_model (reasoning effort: $codex_reasoning_effort)"
  prompt="$(build_single_prompt "$season_json" "$season_primary_slug")"
fi

codex exec --cd "$repo_root" --full-auto --color never \
  -m "$codex_model" \
  -c "model_reasoning_effort=\"$codex_reasoning_effort\"" \
  --add-dir "$output_dir" \
  --output-last-message "$markdown_output" \
  "$prompt" >"$codex_log" 2>&1 &
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
