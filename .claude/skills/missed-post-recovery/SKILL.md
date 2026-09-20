---
name: "missed-post-recovery"
description: "Recover missed daily social + video posts after missed beat cycles or Postiz downtime"
---

# Missed Post Recovery Skill

## Overview
This skill triggers the recovery of missed daily social + video posts when the Celery beat schedule is skipped or Postiz backend is down.

## When to Use
- Daily social post beat entry missed (9:30/13:00/16:00 IST)
- Postiz API returning 502 Bad Gateway
- Social drain job failed earlier
- Need to recover posted videos for own brand + clients

## Trigger Command (run on VPS)
```bash
# Decode + run the trigger script
python3 -c "
from app.tasks.daily_social_post import run_daily_social_post
from app.tasks.staff_jobs import run_staff_job
import traceback

print('=== Triggering missed daily social post ===')
try:
    r = run_daily_social_post()
    print('OK:', r)
except Exception as e:
    traceback.print_exc()
    print('FAIL:', e)

print('=== Triggering missed social drain ===')
try:
    r2 = run_staff_job('social_drain')
    print('OK:', r2)
except Exception as e:
    traceback.print_exc()
    print('FAIL:', e)
"
```

## VPS Setup (one-time)
Ensure these env vars are set on VPS:
- `POSTIZ_API_KEY` (from Postiz dashboard)
- `POSTIZ_API_URL=https://postiz.leadsgenai.in/api`
- `POSTIZ_INTEGRATIONS=channel_id_1,channel_id_2,...` (5 comma-separated IDs)
- `VIDEO_AD_CYCLE=1`

## Recovery Steps
1. Fix Postiz backend: `docker exec leadgen_postiz pm2 restart backend`
2. Run this skill to trigger missed posts
3. Monitor ntfy summary for posted/failed status
