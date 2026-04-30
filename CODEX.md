# CODEX.md

This is a short pointer for Codex.

The canonical repository instructions live in [AGENTS.md](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/AGENTS.md).
The repo-local Codex helpers live in [`.codex/commands`](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/.codex/commands) and [`.agents/skills`](/Users/mrinalsood/Developer/Creatnet/csl/sales-insight-agent/.agents/skills).

For seasonal analysis, run `./scripts/season_analysis.sh <brand> <season> [comparison_season]`.
Override `MODEL` and `REASONING_EFFORT` before running the script if you want to change the Codex model or reasoning level.

Keep this file minimal so it does not drift from `AGENTS.md`.
