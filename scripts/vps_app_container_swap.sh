#!/usr/bin/env bash
# Swap the live app: systemd uvicorn -> Docker container (leadgen_app).
# ~30-60s downtime. AUTO-ROLLBACK to systemd if /health/ready != 200.
# Image must already be built+verified (scripts/vps_build_verify.sh -> OK).
set -uo pipefail
cd /opt/leadgen
COMPOSE="docker compose -f docker-compose.vps.yml"

echo "=== image present? ==="
docker images ghcr.io/sumitrevolt/leadgenrationaivoiceagent --format '{{.Repository}}:{{.Tag}} {{.Size}}' | head -3

echo "=== stop systemd leadgen (frees :8000) ==="
systemctl stop leadgen
sleep 2

echo "=== start app container ==="
$COMPOSE up -d app

echo "=== wait for /health/ready (up to ~90s) ==="
ok=0
for i in $(seq 1 30); do
  code=$(curl -s -o /tmp/cready.json -w '%{http_code}' http://127.0.0.1:8000/health/ready 2>/dev/null || echo 000)
  if [ "$code" = "200" ]; then ok=1; break; fi
  sleep 3
done
echo "----- /health/ready (HTTP $code) -----"
cat /tmp/cready.json 2>/dev/null | head -c 900; echo

if [ "$ok" = "1" ]; then
  systemctl disable leadgen 2>/dev/null || true   # keep installed for rollback, but no boot auto-start (avoid :8000 clash)
  echo ""
  echo "✅ APP_CONTAINER_OK — live app now runs in Docker (leadgen_app), on Postgres+Redis."
  echo "   Rollback if ever needed: $COMPOSE stop app ; systemctl enable --now leadgen"
else
  echo ""
  echo "❌ HEALTH NOT 200 — AUTO-ROLLBACK to systemd"
  $COMPOSE stop app
  systemctl start leadgen
  sleep 6
  curl -s -o /dev/null -w 'rollback /health: %{http_code}\n' http://127.0.0.1:8000/health 2>/dev/null || true
  echo "ROLLED BACK to systemd uvicorn. Logs: docker compose -f docker-compose.vps.yml logs --tail=80 app"
  exit 1
fi
