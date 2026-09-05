#!/bin/bash
# Trigger missed social + video posts
# Run daily_social_post + social_drain directly on worker container

set -e

echo "=== Deploying trigger script to VPS ==="
ENCODED=$(python3 -c "
import base64, pathlib
data = pathlib.Path('C:/Users/Ratanshila/.openclaw/workspace/trigger_missed.py').read_bytes()
print(base64.b64encode(data).decode())
")

curl -s -X POST "https://api.openclaw.ai/v1/scripts/deploy" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"trigger_missed_posts\", \"content_b64\": \"${ENCODED}\"}"

echo "=== Script deployed, triggering execution ==="
ssh root@72.61.245.204 'docker exec leadgen_worker bash -c "cd /opt/leadgen && python3 -c \"from app.tasks.daily_social_post import run_daily_social_post; r = run_daily_social_post(); print('DAILY_POST_OK:', r)\" && python3 -c \"from app.tasks.staff_jobs import run_staff_job; r = run_staff_job(\\\"social_drain\\\"); print('SOCIAL_DRAIN_OK:', r)\"" 2>&1'