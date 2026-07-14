#!/usr/bin/env bash
# deploy_adr097.sh — deploy 3c5a248 (image-provenance guard). Self-verifying:
# the guard must log "Image provenance OK", NOT the unversioned alert.
set -o pipefail
VER=3c5a248
cd /opt/leadgen || exit 1

echo "===PULL==="
git pull --ff-only 2>&1 | tail -2
echo "POST_SHA=$(git rev-parse --short HEAD)"

echo "===BUILD==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml build app > /tmp/adr097_build.log 2>&1
BUILD_RC=$?
echo "BUILD_RC=$BUILD_RC"
if [ "$BUILD_RC" -ne 0 ]; then echo "BUILD FAILED - ABORT"; tail -8 /tmp/adr097_build.log; exit 1; fi

echo "===UP==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker scheduler > /tmp/adr097_up.log 2>&1
echo "UP_RC=$?"
tail -6 /tmp/adr097_up.log

sleep 22
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
