#!/usr/bin/env bash
# deploy_adr096.sh — deploy 1feed53. Detached-safe; pipefail so a piped build
# cannot mask a failure. WhatsApp send path runs in the WORKER -> recreate it too.
set -o pipefail
VER=1feed53
cd /opt/leadgen || exit 1

echo "===PULL==="
git pull --ff-only 2>&1 | tail -3
echo "POST_SHA=$(git rev-parse HEAD)"

echo "===BUILD==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml build app > /tmp/adr096_build.log 2>&1
BUILD_RC=$?
echo "BUILD_RC=$BUILD_RC"
tail -3 /tmp/adr096_build.log
if [ "$BUILD_RC" -ne 0 ]; then echo "BUILD FAILED - ABORT (no restart performed)"; exit 1; fi

echo "===UP (app + worker + scheduler)==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker scheduler > /tmp/adr096_up.log 2>&1
echo "UP_RC=$?"
tail -8 /tmp/adr096_up.log

echo "===SETTLE==="
sleep 20
echo "===HEALTH x2==="
curl -s -m 10 127.0.0.1:8000/health; echo
sleep 3
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===IMAGES==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null
echo "===STATE==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'
echo "===PORT TRAP RECHECK (in-network)==="
docker exec leadgen_worker sh -c 'curl -s -o /dev/null -w "worker->app:8080/health/ready = %{http_code}\n" -m 8 http://app:8080/health/ready'
echo "===ADR096_DEPLOY_DONE==="
