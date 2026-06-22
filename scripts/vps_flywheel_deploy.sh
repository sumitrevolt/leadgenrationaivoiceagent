#!/usr/bin/env bash
set -euo pipefail
cd /opt/leadgen
git pull origin main
docker compose -f docker-compose.vps.yml build app
docker compose -f docker-compose.vps.yml up -d --no-deps app
# Alembic migration (flywheel tables)
docker compose -f docker-compose.vps.yml exec -T app alembic upgrade head || true
chmod +x scripts/vps_flywheel_enable.sh
bash scripts/vps_flywheel_enable.sh /opt/leadgen/.env
docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps worker scheduler 2>/dev/null || true
docker compose -f docker-compose.vps.yml up -d --no-deps app
sleep 16
curl -sf http://127.0.0.1:8000/health | head -c 400
echo ""
curl -sf http://127.0.0.1:8000/api/growth/campaign/optimize/status | head -c 400
echo ""
