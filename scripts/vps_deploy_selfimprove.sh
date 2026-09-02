#!/usr/bin/env bash
# Self-improve loop deploy: rebuild app image, flag ON, recreate app+worker+scheduler,
# health-gate + worker-smoke + loop kick. Idempotent. Run: bash scripts/vps_deploy_selfimprove.sh
set -u
cd /opt/leadgen

echo "== git head =="
git log --oneline -1

echo "== build app image =="
docker compose -f docker-compose.vps.yml build app 2>&1 | tail -3

echo "== flag SELF_IMPROVE_LOOP=1 =="
python3 scripts/env_set.py SELF_IMPROVE_LOOP=1 2>&1 | tail -2 || true

echo "== recreate app+worker+scheduler =="
docker compose -f docker-compose.vps.yml --profile celery up -d app worker scheduler 2>&1 | tail -6

sleep 16
echo "== health (x2, boot-grace lesson) =="
curl -s -o /dev/null -w "health=%{http_code}\n" http://127.0.0.1:8000/health
sleep 6
curl -s -o /dev/null -w "ready=%{http_code}\n" http://127.0.0.1:8000/health/ready

echo "== smoke (worker container) =="
docker exec leadgen_worker python scripts/smoke_self_improve.py 2>&1 | tail -14

echo "== kick continuous loop (first tick) =="
docker exec leadgen_worker python -c "from app.tasks.staff_jobs import self_improve_tick; r=self_improve_tick.delay(); print('TICK_QUEUED', r.id)"

echo "== container status =="
docker ps --format '{{.Names}} {{.Status}}' | grep -E 'leadgen_(app|worker|scheduler)' || true
echo "DEPLOY_DONE"
