#!/usr/bin/env bash
# Stop local Buzz relay (volumes + data kept). Wipe with: docker compose down -v
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KIT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
BUZZ_DIR="${BUZZ_LOCAL_DIR:-$HOME/buzz-local}"
COMPOSE_DIR="$BUZZ_DIR/deploy/compose"
cd "$COMPOSE_DIR"
# Deterministic project name (pinned by buzz-local-up.sh) — never touches other stacks.
docker compose -p buzz-local --env-file .env down
echo "==> local relay stopped (volumes kept). Hard reset: docker compose -p buzz-local --env-file .env down -v"
