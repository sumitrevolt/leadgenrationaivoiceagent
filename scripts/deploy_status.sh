#!/usr/bin/env bash
# deploy_status.sh — read-only: did the ADR-095 deploy land?
set +e
echo "===HEALTH==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===IMAGES==="
docker inspect --format '{{.Config.Image}}' leadgen_app leadgen_worker leadgen_scheduler 2>/dev/null
echo "===STATE==="
docker ps --filter name=leadgen_app --filter name=leadgen_worker --filter name=leadgen_scheduler --format '{{.Names}}|{{.Status}}'
echo "===VPS_SHA==="
cd /opt/leadgen && git rev-parse HEAD
echo "===BUILD_LOG_TAIL==="
tail -4 /tmp/adr095_build.log 2>/dev/null || echo "(no build log yet)"
echo "===UP_LOG_TAIL==="
tail -8 /tmp/adr095_up.log 2>/dev/null || echo "(no up log yet)"
echo "===STATUS_DONE==="
