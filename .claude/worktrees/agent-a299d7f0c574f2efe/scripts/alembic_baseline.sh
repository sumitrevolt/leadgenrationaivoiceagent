#!/usr/bin/env bash
# alembic_baseline.sh — live Postgres ko Alembic-managed mark karo (one-time adopt).
# Scaffold + 5 revisions PEHLE se repo me hain; live DB schema create_all se already
# complete hai → sirf `alembic stamp head` chahiye (ZERO DDL — sirf version mark).
# Iske baad har schema change = `alembic revision --autogenerate -m "..."` +
# deploy me `alembic upgrade head` (CI/manual) — create_all drift khatam.
#
# Run (VPS): bash scripts/alembic_baseline.sh          # dry-run (default)
#            bash scripts/alembic_baseline.sh --apply
set -euo pipefail
cd /opt/leadgen 2>/dev/null || cd "$(dirname "$0")/.."

APPLY="${1:-}"
EXEC=""
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q '^leadgen_app$'; then
  EXEC="docker exec leadgen_app"
fi

echo "== alembic current (pehle) =="
$EXEC alembic current 2>&1 || true
echo "== alembic heads =="
$EXEC alembic heads 2>&1 || true

if [ "$APPLY" = "--apply" ]; then
  echo "== stamp head (zero DDL) =="
  $EXEC alembic stamp head
  echo "== alembic current (baad) =="
  $EXEC alembic current
  echo "DONE. Ab se: schema change => alembic revision --autogenerate + upgrade head."
else
  echo "(dry-run) Apply karne ke liye: bash scripts/alembic_baseline.sh --apply"
fi
