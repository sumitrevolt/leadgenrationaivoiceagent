#!/bin/bash
# Trigger missed social + video posts on VPS
# This runs the daily_social_post task + social_drain job directly inside the scheduler

set -e

echo "=== Triggering missed social posts ==="

# Run daily social post task directly (missed 9:30 AM run)
docker exec -t leadgen_scheduler sh -c '
  cd /opt/leadgen && python3 -c "
import traceback
try:
    from app.tasks.daily_social_post import run_daily_social_post
    r = run_daily_social_post()
    print(\"[OK] Daily social post completed:\", r)
except Exception as e:
    print(\"[FAIL] Daily social post error:\", e)
    traceback.print_exc()
"
' 2>&1

echo ""
echo "=== Triggering social drain (missed hourly) ==="

# Run social drain job
docker exec -t leadgen_scheduler sh -c '
  cd /opt/leadgen && python3 -c "
import traceback
try:
    from app.tasks.staff_jobs import run_staff_job
    r = run_staff_job(\"social_drain\")
    print(\"[OK] Social drain completed:\", r)
except Exception as e:
    print(\"[FAIL] Social drain error:\", e)
    traceback.print_exc()
"
' 2>&1

echo ""
echo "=== Done ==="