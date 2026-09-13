#!/usr/bin/env bash
# Apply pending Alembic migrations for the prod DB (idempotent, fail-closed).
#
# Why: deploy_vps.sh had NO migration step, so prod could sit on an old alembic
# head (observed: 025) while the new image expected 026/027 = silent schema drift.
# This helper is called by deploy_vps.sh before the /health verification.
#
# The app image has no `alembic` on PATH, so prefer the repo .venv, then a CLI,
# then the python module. Idempotent: `upgrade head` is a no-op when already at head.
set -euo pipefail

REPO="${REPO:-/opt/leadgen}"
cd "$REPO"

if [ -x .venv/bin/alembic ]; then
  ALEMBIC=".venv/bin/alembic"
elif command -v alembic >/dev/null 2>&1; then
  ALEMBIC="alembic"
elif python3 -c "import alembic" >/dev/null 2>&1; then
  ALEMBIC="python3 -m alembic"
else
  echo "FATAL: no alembic available (no .venv/bin/alembic, no CLI, no python module)"
  exit 1
fi

echo "[vps_migrate] using: $ALEMBIC"
echo "[vps_migrate] before: $($ALEMBIC current 2>&1 | tail -1)"
$ALEMBIC upgrade head
echo "[vps_migrate] after:  $($ALEMBIC current 2>&1 | tail -1)"
