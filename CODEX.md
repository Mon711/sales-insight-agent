# CODEX.md

This is a short pointer for Codex.

The canonical repository instructions live in [AGENTS.md](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/AGENTS.md).
The repo-local Codex helpers live in [`.codex/commands`](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/.codex/commands) and [`.agents/skills`](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/.agents/skills).

For a brand-aware annual 2025 report flow, run `./scripts/brand_analysis.sh <brand>`.
`./scripts/annual_report_2025.sh` remains as a compatibility wrapper for Eddy.
For faster testing, override `ANNUAL_REPORT_MODEL` and `ANNUAL_REPORT_REASONING_EFFORT` before running the script.

Keep this file minimal so it does not drift from `AGENTS.md`.
