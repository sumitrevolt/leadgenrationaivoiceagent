#!/usr/bin/env bash
# launch_probe.sh — read-only production evidence collector (LAUNCH audit)
set +e
echo "===HEALTH==="
curl -s -m 10 127.0.0.1:8000/health; echo
echo "===VPSGIT==="
cd /opt/leadgen || exit 1
git rev-parse HEAD
echo "--- dirty (top20) ---"
git status --porcelain | head -20
echo "===CONTAINERS==="
docker ps --format '{{.Names}}|{{.Status}}' | head -40
echo "===QUEUES==="
docker exec leadgen_redis redis-cli llen celery 2>/dev/null
docker exec leadgen_redis redis-cli llen dlq:failed_tasks 2>/dev/null
echo "===SCHEDULER_TAIL==="
docker logs --tail 8 leadgen_scheduler 2>&1 | tail -8
echo "===WORKER_TAIL==="
docker logs --tail 8 leadgen_worker 2>&1 | tail -8
echo "===APP_ERR_TAIL==="
docker logs --since 2h leadgen_app 2>&1 | grep -iE "error|traceback|500" | tail -15
echo "===PROBE_DONE==="
