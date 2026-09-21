#!/usr/bin/env bash
# Apply pending Alembic migrations for the prod DB (idempotent, fail-closed).
#
# Why: deploy_vps.sh had NO migration step, so prod could sit on an old alembic
# head (observed: 025) while the new image expected 026/027 = silent schema drift.
# This helper is called by deploy_vps.sh before the /health verification.
#
# The image keeps its venv at /opt/venv, so `alembic` IS on PATH inside the
# containers (verified on prod 2026-09-20: /opt/venv/bin/alembic in both
# leadgen_worker and leadgen_app) even though the host has no working alembic —
# /opt/leadgen/.venv/bin/python does not exist. Prefer a running container, then
# a host .venv, then a host CLI, then the host python module.
#
# The host module candidate is probed by RUNNING it, not by importing it. From
# this cwd, `python3 -c "import alembic"` resolves to the repo's own `alembic/`
# migrations directory as a PEP-420 namespace package and succeeds even with the
# real package absent — the probe that made the 2026-09-19 deploy print
# "using: python3 -m alembic" and then die with "No module named alembic".
# Idempotent: `upgrade head` is a no-op when already at head.
set -euo pipefail

REPO="${REPO:-/opt/leadgen}"
cd "$REPO"

if docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^leadgen_worker$'; then
  ALEMBIC="docker exec leadgen_worker alembic"
elif docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^leadgen_app$'; then
  ALEMBIC="docker exec leadgen_app alembic"
elif [ -x .venv/bin/alembic ]; then
  ALEMBIC=".venv/bin/alembic"
elif command -v alembic >/dev/null 2>&1; then
  ALEMBIC="alembic"
elif python3 -m alembic --help >/dev/null 2>&1; then
  ALEMBIC="python3 -m alembic"
else
  echo "FATAL: no usable alembic (no running leadgen_worker/leadgen_app, no host .venv, no CLI, and \`python3 -m alembic\` does not run)"
  exit 1
fi

echo "[vps_migrate] using: $ALEMBIC"
echo "[vps_migrate] before: $($ALEMBIC current 2>&1 | tail -1)"
$ALEMBIC upgrade head
echo "[vps_migrate] after:  $($ALEMBIC current 2>&1 | tail -1)"
