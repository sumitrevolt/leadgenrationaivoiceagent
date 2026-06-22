#!/usr/bin/env bash
set +e
echo "===== FULL JOB HEARTBEATS (har job: ok? last-ran kab?) ====="
docker exec leadgen_app python -c "
import json,os,time
from datetime import datetime,timezone
d=json.load(open('data/job_heartbeats.json')) if os.path.exists('data/job_heartbeats.json') else {}
now=datetime.now(timezone.utc)
for k in sorted(d):
    v=d[k]; at=v.get('at',''); ok=v.get('ok'); s=v.get('s')
    try:
        t=datetime.fromisoformat(at); 
        if t.tzinfo is None: t=t.replace(tzinfo=timezone.utc)
        mins=int((now-t).total_seconds()/60)
    except: mins='?'
    print(f'  {k:16s} ok={ok}  ran={mins} min ago  dur={s}s')
"
echo ""
echo "===== EXPECTED schedule (IST) vs now ====="
date -u +'  now_UTC=%H:%M  (IST = +5:30)'
echo "  daily: blog 06:30 content 07:00 digest 08:30 prospect 09:30 email 10:30 qa 02:30 trainer 03:00 standup 08:00-09:30 IST"
echo ""
echo "===== DLQ (failures) ====="
docker exec leadgen_redis redis-cli LLEN dlq:failed_tasks
echo ""
echo "===== WORKER last 20 job lines (succeeded/failed) ====="
docker logs leadgen_worker --since 3h 2>&1 | grep -iE 'run_staff_job.*(succeeded|failed)|running job:' | tail -20
echo "===== DONE ====="
