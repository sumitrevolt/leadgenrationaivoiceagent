#!/bin/bash
set -euo pipefail
echo '=== VPS Runtime Probe ==='
echo '--- App Process ---'
systemctl status leadgen --no-pager | head -20
echo '--- Docker Containers ---'
docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'
echo '--- Image Digests ---'
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.ID}}' | head -20
echo '--- System Resources ---'
df -h / | tail -1
free -h | head -2
uptime
echo '--- Redis Health ---'
docker exec leadgen_redis redis-cli ping 2>/dev/null || echo 'Redis not reachable'
echo '--- Celery Queues ---'
docker exec leadgen_redis redis-cli llen celery 2>/dev/null || echo 'celery queue check failed'
docker exec leadgen_redis redis-cli llen dlq:failed_tasks 2>/dev/null || echo 'dlq check failed'
echo '--- /health from localhost ---'
curl -s http://127.0.0.1:8000/health | head -c 500
echo
echo '--- Deploy Log Tail ---'
tail -30 /tmp/dep.log 2>/dev/null || echo 'No deploy log found'
