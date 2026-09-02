#!/usr/bin/env bash
# ============================================================================
# graphify_refresh.sh - staleness-aware graphify graph refresh (git-bash/WSL/VPS)
# Compares app/graphify-out/GRAPH_REPORT.md "Built from commit" vs git HEAD.
# Stale (or report missing) -> `graphify update app` (FREE, AST-only, incremental).
# Fresh -> no-op. Prereq: `uv tool install graphifyy` (graphify on PATH).
# Usage:  scripts/graphify_refresh.sh           # rebuild only if stale
#         scripts/graphify_refresh.sh --force   # always rebuild
# ============================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
REPORT="app/graphify-out/GRAPH_REPORT.md"

HEAD_FULL="$(git rev-parse HEAD 2>/dev/null || true)"
if [ -z "$HEAD_FULL" ]; then
  echo "[graphify-refresh] ERROR: no git HEAD (is git on PATH?)"; exit 1
fi
HEAD8="${HEAD_FULL:0:8}"

BUILT=""
if [ -f "$REPORT" ]; then
  BUILT="$(grep -m1 -i 'Built from commit' "$REPORT" | grep -oiE '[0-9a-f]{7,40}' | head -1 || true)"
fi
BUILT8="${BUILT:0:8}"

echo "[graphify-refresh] HEAD=$HEAD8  graph_built_from=${BUILT8:-none}"

force="${1:-}"
if [ "$force" != "--force" ] && [ -n "$BUILT8" ] && [ "$HEAD8" = "$BUILT8" ]; then
  echo "[graphify-refresh] graph FRESH - no rebuild needed."
  exit 0
fi

echo "[graphify-refresh] STALE/forced -> running: graphify update app"
graphify update app
echo "[graphify-refresh] done. (optional labels: graphify label app --backend=ollama --model=qwen2.5:3b-instruct)"
