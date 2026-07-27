#!/usr/bin/env bash
# deploy_adr095.sh — deploy 91e7d37 to VPS.
#
# CONSOLIDATED 2026-07-26: this script used to carry its OWN copy of the
# release chain — `cd /opt/leadgen`, `git pull --ff-only`, `compose build`,
# `compose up -d`. That chain never touched the runtime-data guard, so running
# this file deployed straight over the live invoice / consent / suppression
# ledgers and the DPDP call recordings that still sit inside the checkout.
#
# The mutation chain is now delegated to the canonical parent (deploy_vps.sh),
# which is guarded. Everything below the delegation is READ-ONLY verification
# and is unchanged.
#
# There is deliberately NO fallback to the old chain: if the parent denies
# (90) or is unavailable (91), this script exits with that exact status and
# does nothing else.
set -o pipefail
VER=91e7d37

# shellcheck source=scripts/_deploy_parent_delegate.sh
_delegate="$(dirname "$0")/_deploy_parent_delegate.sh"
if [ ! -r "$_delegate" ]; then
  echo "FATAL: delegation helper missing: $_delegate"
  exit 91
fi
. "$_delegate" || exit 91

echo "===DELEGATING TO CANONICAL PARENT (guarded)==="
delegate_to_parent "$VER"
_rc=$?
if [ "$_rc" -ne 0 ]; then
  echo "PARENT_RC=$_rc — aborting. (90=guard denied, 91=guard/parent unavailable)"
  echo "No local git/compose fallback exists by design."
  exit "$_rc"
fi

# ------------------------------------------------- read-only verification
# Preserved from the original script. Nothing here mutates the checkout or
# replaces a container.
echo "===MIGRATION_STATE (read-only)==="
docker exec leadgen_app alembic current 2>&1 | tail -3
docker exec leadgen_app alembic heads 2>&1 | tail -3

echo "===HEALTH x2==="
curl -s -m 10 127.0.0.1:8000/health; echo
sleep 3
curl -s -m 10 127.0.0.1:8000/health; echo

echo "===IMAGES==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null

echo "===CONTAINER_STATE==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'

echo "===DEPLOY_DONE==="
