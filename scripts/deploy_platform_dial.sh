#!/usr/bin/env bash
# Surgical deploy: platform_dial (LeadGen AI self-sale daily cold-call batch, Swara).
# VPS pe root se chalao:  bash /opt/leadgen/scripts/deploy_platform_dial.sh
#
# NO rebuild / NO recreate — running containers docker-cp hotfix drift carry karte
# hain (recreate = hotfix loss). Isliye: git checkout (sirf target files) + docker cp
# + restart (restart drift PRESERVE karta hai).
#
# Enable/disable (no-restart): data/platform_dial.json -> {"enabled": true|false}
# Hard kill-switch: .env me PLATFORM_DIAL_DAILY=0 (recreate ke baad effective).
set -euo pipefail
cd /opt/leadgen

FILES="app/tasks/calling.py app/platform/team_scheduler.py app/tasks/staff_jobs.py app/worker.py app/platform/automation_health.py app/api/automation_flags.py app/platform/platform_dial.py app/marketing/postiz_publish.py app/social_engine/engine.py app/api/growth_automation.py app/voice_agent/universal_pitch.py"
# Office frontend (Reliability Console panel) — static file, leadgen_app only.
APP_ONLY_FILES="frontend/office_map.html"

git fetch origin -q
# shellcheck disable=SC2086
git checkout origin/main -- $FILES $APP_ONLY_FILES tests/test_platform_dial.py scripts/deploy_platform_dial.sh

# Daily auto-dial config (bind-mounted -> har container me live, recreate-proof).
# limit=15 calls/day conservative start; niche=all -> poora harvested pool.
if [ ! -f data/platform_dial.json ]; then
  printf '{"enabled": true, "limit": 15, "niche": "all"}\n' > data/platform_dial.json
  echo "wrote data/platform_dial.json (enabled, 15/day, all niches)"
fi

for c in leadgen_app leadgen_worker leadgen_worker_heavy leadgen_scheduler; do
  for f in $FILES; do
    docker cp "/opt/leadgen/$f" "$c:/app/$f"
  done
  echo "copied -> $c"
done

# Office frontend -> leadgen_app only (worker/scheduler don't serve HTTP).
for f in $APP_ONLY_FILES; do
  docker cp "/opt/leadgen/$f" "leadgen_app:/app/$f"
done
echo "copied office frontend -> leadgen_app"

docker restart leadgen_worker leadgen_worker_heavy leadgen_scheduler
docker restart leadgen_app

sleep 16
curl -s -m 20 localhost:8000/health && echo
sleep 4
curl -s -m 20 localhost:8000/health && echo

echo "--- beat entry present? ---"
docker exec leadgen_scheduler sh -c "grep -c 'staff-platform-dial-daily' /app/app/worker.py"

cat <<'EOT'
DONE. Ab (TRAI window 10:00-19:00 IST ke andar):
1) DRY-RUN (0 real calls, sirf pipeline verify):
   docker exec leadgen_app python -c "from app.worker import celery_app; r=celery_app.send_task('app.tasks.calling.run_campaign_task', kwargs={'limit':3,'dry_run':True,'niche':'all','client_id':'','platform':True,'transactional':False}); print('queued', r.id)"
   # 30s baad status: docker exec leadgen_app python -c "import redis,os,json; r=redis.Redis.from_url(os.environ.get('REDIS_URL','redis://leadgen_redis:6379/0'),decode_responses=True); print(r.get('admin:campaign:last_run'))"
2) PEHLI REAL BATCH (10 AI calls, ~Rs.10-30 Vobiz):
   admin UI se: /app/automation -> Campaign launch (platform=true, limit=10)
   ya: docker exec leadgen_app python -c "from app.worker import celery_app; r=celery_app.send_task('app.tasks.calling.run_campaign_task', kwargs={'limit':10,'dry_run':False,'niche':'all','client_id':'','platform':True,'transactional':False}); print('queued', r.id)"
3) Roz 11:30 IST automatic 15-call batch chalegi (data/platform_dial.json se ON).
   Band karna ho: data/platform_dial.json me "enabled": false likh do (no restart).
EOT
