#!/usr/bin/env bash
# deploy_adr095.sh — deploy 91e7d37 to VPS. Buffers build log to /tmp (SSH tunnel
# dies on verbose build output) and uses `set -o pipefail` so a piped build cannot
# mask a non-zero exit code (known landmine).
set -o pipefail
VER=91e7d37
cd /opt/leadgen || exit 1

echo "===PRE_SHA==="
git rev-parse HEAD

echo "===PULL==="
git pull --ff-only 2>&1 | tail -5
echo "PULL_RC=${PIPESTATUS[0]}"

echo "===POST_SHA==="
git rev-parse HEAD

echo "===MIGRATION_STATE (read-only)==="
docker exec leadgen_app alembic current 2>&1 | tail -3
docker exec leadgen_app alembic heads 2>&1 | tail -3

echo "===BUILD (log -> /tmp/adr095_build.log)==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml build app > /tmp/adr095_build.log 2>&1
BUILD_RC=$?
echo "BUILD_RC=$BUILD_RC"
tail -5 /tmp/adr095_build.log
if [ "$BUILD_RC" -ne 0 ]; then echo "BUILD FAILED - ABORT"; exit 1; fi

echo "===UP (app + worker + scheduler: the fix runs in the WORKER)==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps app worker scheduler > /tmp/adr095_up.log 2>&1
UP_RC=$?
echo "UP_RC=$UP_RC"
tail -12 /tmp/adr095_up.log

echo "===SETTLE==="
sleep 18

echo "===HEALTH x2==="
curl -s -m 10 127.0.0.1:8000/health; echo
sleep 3
curl -s -m 10 127.0.0.1:8000/health; echo

echo "===IMAGES==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null

echo "===CONTAINER_STATE==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'

echo "===DEPLOY_DONE==="
