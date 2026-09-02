#!/usr/bin/env bash
# deploy_adr096.sh — deploy 1feed53. WhatsApp send path runs in the WORKER.
#
# CONSOLIDATED 2026-07-26: the local `git pull` / `compose build` / `compose up`
# chain is gone and now runs inside the guarded canonical parent. The parent
# rolls all five app-image services, so the old "recreate the worker too"
# special case is covered by it rather than by a second chain here.
#
# No fallback: parent denial (90) or unavailability (91) exits immediately.
set -o pipefail
VER=1feed53

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
  exit "$_rc"
fi

# ------------------------------------------------- read-only verification
echo "===HEALTH x2==="
curl -s -m 10 127.0.0.1:8000/health; echo
sleep 3
curl -s -m 10 127.0.0.1:8000/health; echo

echo "===IMAGES==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null

echo "===STATE==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'

# The 2026-07-14 port trap: in-network callers must use 8080, not 8000.
echo "===PORT TRAP RECHECK (in-network)==="
docker exec leadgen_worker sh -c 'curl -s -o /dev/null -w "worker->app:8080/health/ready = %{http_code}\n" -m 8 http://app:8080/health/ready'

echo "===ADR096_DEPLOY_DONE==="
