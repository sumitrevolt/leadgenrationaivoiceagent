#!/usr/bin/env bash
set +e
echo "===== dispatch content + standup (fill today's gap) ====="
docker exec leadgen_app python -c "
from app.tasks.staff_jobs import run_staff_job
for j in ['content','standup']:
    r = run_staff_job.apply_async(args=[j]); print('dispatched', j, r.id)
"
echo "===== wait 40s, check success ====="
sleep 40
echo "DLQ:"; docker exec leadgen_redis redis-cli LLEN dlq:failed_tasks
docker logs leadgen_worker --since 1m 2>&1 | grep -iE "run_staff_job.*(succeeded|failed)" | tail -4
echo "===== content heartbeat now ====="
docker exec leadgen_app python -c "
import json
d=json.load(open('data/job_heartbeats.json'))
for k in ['content','standup']:
    v=d.get(k,{}); print(' ', k, 'ok=', v.get('ok'), 'at=', v.get('at'))
"
echo "===== DONE ====="
