#!/usr/bin/env bash
# deploy_all.sh — deploy 87d6015 to ALL app-image services, clearing the
# worker_heavy/worker_video :latest version skew (ADR-097).
#
# CONSOLIDATED 2026-07-26: the local pull/build/up chain is gone. The canonical
# parent already rolls all five app-image services (app worker scheduler
# worker-heavy worker-video) and verifies per-container skew itself, so this
# script's whole reason for existing is now a property of the parent. What
# remains here is the extra read-only skew report.
#
# The hyphen in `worker-heavy` used to be this script's main hazard (a wrong
# service name aborts the entire `up`). That risk now lives in exactly one
# place instead of nine.
#
# No fallback: parent denial (90) or unavailability (91) exits immediately.
set -o pipefail
VER=87d6015

# shellcheck source=scripts/_deploy_parent_delegate.sh
_delegate="$(dirname "$0")/_deploy_parent_delegate.sh"
if [ ! -r "$_delegate" ]; then
  echo "FATAL: delegation helper missing: $_delegate"
  exit 91
fi
. "$_delegate" || exit 91

echo "===DELEGATING TO CANONICAL PARENT (guarded, rolls all 5 services)==="
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

echo "===SKEW RECHECK — every container must show the SAME sha==="
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video; do
  img=$(docker inspect --format '{{.Config.Image}}' "$c" 2>/dev/null | sed 's#.*:##')
  ver=$(docker exec "$c" printenv APP_VERSION 2>/dev/null)
  st=$(docker ps --filter "name=^${c}$" --format '{{.Status}}' 2>/dev/null)
  printf '%-24s tag=%-10s APP_VERSION=%-10s %s\n' "$c" "$img" "${ver:-<unset>}" "$st"
done

echo "===GUARD SELF-CHECK==="
docker logs --since 3m leadgen_app 2>&1 | grep -i "provenance\|UNVERSIONED" | tail -2

echo "===REVENUE ROUTES==="
for p in /api/voice/niches /api/billing/plans /health; do
  printf '%-22s -> %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 15 https://leadsgenai.in$p)"
done

echo "===QUEUES/DLQ==="
docker exec leadgen_redis redis-cli llen celery
docker exec leadgen_redis redis-cli llen dlq:failed_tasks
echo "===DEPLOY_ALL_DONE==="
