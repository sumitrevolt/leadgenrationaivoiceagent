#!/usr/bin/env bash
# Fable batch deploy — rebuild image (code-layer; heavy ML layers cached) + recreate
# app + celery workers + scheduler, then health-gate. Run AFTER git pull on VPS.
# Usage: nohup bash scripts/vps_deploy_fable.sh > /tmp/fable_deploy.log 2>&1 &
set -uo pipefail
cd /opt/leadgen || exit 1
CF="docker compose -f docker-compose.vps.yml --profile celery"
echo "=== FABLE DEPLOY start $(date -u) ==="
echo "HEAD=$(git rev-parse --short HEAD)"

echo "--- build (shared image) ---"
$CF build app 2>&1 | tail -25
echo "--- recreate app worker worker-heavy scheduler ---"
$CF up -d app worker worker-heavy scheduler 2>&1 | tail -25

echo "--- boot grace 18s ---"
sleep 18
echo "--- health x2 (internal) ---"
H1=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health || echo 000)
echo "h1=$H1"
sleep 5
H2=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8000/health || echo 000)
echo "h2=$H2"
echo "--- /health body ---"
curl -s http://127.0.0.1:8000/health; echo
echo "--- /health/ready body ---"
curl -s http://127.0.0.1:8000/health/ready; echo
echo "--- containers ---"
docker ps --format '{{.Names}} | {{.Status}}' | grep leadgen_ || true

if [ "$H2" = "200" ]; then
  echo "=== DEPLOY OK (health 200) $(date -u) ==="
else
  echo "=== DEPLOY HEALTH FAIL h2=$H2 — app logs tail ==="
  docker logs --tail 40 leadgen_app 2>&1 || true
fi
