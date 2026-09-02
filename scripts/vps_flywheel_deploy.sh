#!/usr/bin/env bash
# vps_flywheel_deploy.sh — release + enable the growth-flywheel feature.
#
# CONSOLIDATED 2026-07-26. The old body was a bare unguarded chain:
#   cd /opt/leadgen; git pull origin main; compose build; compose up -d ...
#
# UNLIKE the other consolidated wrappers, this one has genuine work of its own
# AFTER the release: an Alembic upgrade and a .env mutation via
# vps_flywheel_enable.sh. That is recorded honestly in the deployment manifest
# as post_parent_mutation=true rather than described as "read-only
# verification" — it is not read-only, and pretending otherwise is exactly the
# kind of comment-vs-code mismatch that made vps_selfheal.sh unclassifiable.
#
# What matters for containment is the ordering, which is enforced here:
#   * NOTHING mutates before the guarded parent runs.
#   * NOTHING mutates if the parent denies (90) or is unavailable (91).
# The feature-enable steps run only on a successful, guarded release.
set -o pipefail

# shellcheck source=scripts/_deploy_parent_delegate.sh
_delegate="$(dirname "$0")/_deploy_parent_delegate.sh"
if [ ! -r "$_delegate" ]; then
  echo "FATAL: delegation helper missing: $_delegate"
  exit 91
fi
. "$_delegate" || exit 91

echo "===DELEGATING TO CANONICAL PARENT (guarded)==="
delegate_to_parent ""
_rc=$?
if [ "$_rc" -ne 0 ]; then
  echo "PARENT_RC=$_rc — aborting BEFORE any migration or .env change."
  echo "(90=guard denied, 91=guard/parent unavailable)"
  exit "$_rc"
fi

# ---------------------------------- post-release feature enablement (MUTATES)
# Reached only after a guarded, successful release.
echo "===ALEMBIC (flywheel tables)==="
docker compose -f docker-compose.vps.yml exec -T app alembic upgrade head || true

echo "===FEATURE ENABLE (.env)==="
_enable="$(dirname "$0")/vps_flywheel_enable.sh"
if [ ! -r "$_enable" ]; then
  echo "FATAL: vps_flywheel_enable.sh missing — release succeeded but the"
  echo "       feature was NOT enabled. Do not re-run the release to fix this."
  exit 92
fi
chmod +x "$_enable"
bash "$_enable" /opt/leadgen/.env

# Restart to pick up the new env only — no rebuild, no pull.
echo "===APPLY ENV (restart app, no rebuild)==="
docker compose -f docker-compose.vps.yml up -d --no-deps app

# ------------------------------------------------- read-only verification
sleep 16
curl -sf http://127.0.0.1:8000/health | head -c 400
echo ""
curl -sf http://127.0.0.1:8000/api/growth/campaign/optimize/status | head -c 400
echo ""
echo "===FLYWHEEL_DEPLOY_DONE==="
