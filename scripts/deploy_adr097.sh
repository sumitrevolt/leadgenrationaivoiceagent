#!/usr/bin/env bash
# deploy_adr097.sh — deploy 3c5a248 (image-provenance guard). Self-verifying:
# the guard must log "Image provenance OK", NOT the unversioned alert.
#
# CONSOLIDATED 2026-07-26: local pull/build/up chain removed in favour of the
# guarded canonical parent. Note the irony this script exists to fix — ADR-097
# was about images of UNKNOWN provenance reaching production; the script that
# deployed that fix was itself an unguarded release path.
#
# No fallback: parent denial (90) or unavailability (91) exits immediately.
set -o pipefail
VER=3c5a248

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

echo "===GUARD SELF-CHECK (expect 'Image provenance OK', NOT the alert)==="
docker logs --since 3m leadgen_app 2>&1 | grep -i "provenance\|UNVERSIONED" | tail -3

echo "===CRITICAL ROUTE SWEEP==="
docker logs --since 3m leadgen_app 2>&1 | grep -i "Critical route sweep\|CRITICAL routes missing" | tail -2

echo "===REVENUE ROUTES==="
for p in /api/voice/niches /api/billing/plans /api/public/pay-info /health; do
  printf '%-24s -> %s\n' "$p" "$(curl -s -o /dev/null -w '%{http_code}' -m 15 https://leadsgenai.in$p)"
done

echo "===ERRORS SINCE BOOT==="
for pat in "_IncludedRouter" "lead_topup_price" "fastembed model not ready"; do
  printf '%-28s %s\n' "$pat" "$(docker logs --since 3m leadgen_app 2>&1 | grep -ci "$pat")"
done

echo "===STATE==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'
docker exec leadgen_redis redis-cli llen celery
docker exec leadgen_redis redis-cli llen dlq:failed_tasks
echo "===ADR097_DONE==="
