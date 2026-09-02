#!/usr/bin/env bash
# Post-failed-deploy recovery probe — read-only + minimal state dump.
set -uo pipefail
cd /opt/leadgen || exit 1
echo "=== VPS HEAD ==="
git rev-parse --short HEAD
echo "=== DOCKER PS leadgen ==="
docker ps -a --format 'table {{.Names}}\t{{.Status}}\t{{.Image}}' | grep -E 'leadgen|NAMES' || true
echo "=== APP_VERSION env per container ==="
for c in leadgen_app leadgen_worker leadgen_scheduler leadgen_worker_heavy leadgen_worker_video; do
  printf '%-24s ' "$c"
  docker inspect -f '{{.State.Status}} rev={{.RestartCount}} img={{.Config.Image}} env={{index .Config.Env 0}}' "$c" 2>/dev/null || echo MISSING
done
echo "=== HEALTH host ==="
curl -s -m 8 -w '\nHTTP=%{http_code}\n' http://127.0.0.1:8000/health || true
echo "=== UP LOG tail ==="
tail -25 /tmp/deploy_up.log 2>/dev/null || true
echo "=== CADDY ==="
systemctl is-active caddy 2>/dev/null || true
echo "=== QUEUES ==="
docker exec leadgen_redis redis-cli llen celery 2>/dev/null || echo redis-unavail
docker exec leadgen_redis redis-cli llen dlq:failed_tasks 2>/dev/null || true
