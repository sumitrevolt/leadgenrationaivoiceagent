#!/usr/bin/env bash
# deploy_all.sh — deploy 87d6015 to ALL app-image services, clearing the
# worker_heavy/worker_video :latest version skew (ADR-097).
# worker-heavy uses a HYPHEN (a wrong name aborts the whole `up`).
set -o pipefail
VER=87d6015
cd /opt/leadgen || exit 1

echo "===PULL==="
git pull --ff-only 2>&1 | tail -2
echo "POST_SHA=$(git rev-parse --short HEAD)"

echo "===BUILD==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml build app > /tmp/all_build.log 2>&1
BUILD_RC=$?
echo "BUILD_RC=$BUILD_RC"
if [ "$BUILD_RC" -ne 0 ]; then echo "BUILD FAILED - ABORT"; tail -8 /tmp/all_build.log; exit 1; fi

echo "===UP (all 5 app-image services; note: worker-heavy has a HYPHEN)==="
APP_VERSION=$VER docker compose -f docker-compose.vps.yml --profile celery \
  up -d --no-deps app worker scheduler worker-heavy worker-video > /tmp/all_up.log 2>&1
echo "UP_RC=$?"
tail -12 /tmp/all_up.log

sleep 25
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
