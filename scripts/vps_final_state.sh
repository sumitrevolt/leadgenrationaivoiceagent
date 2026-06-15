#!/usr/bin/env bash
set +e
echo -n "DLQ="; docker exec leadgen_redis redis-cli LLEN dlq:failed_tasks
docker exec leadgen_app python -c "
import json
d=json.load(open('data/job_heartbeats.json'))
v=d.get('content',{}); print('content ok=',v.get('ok'),'at=',v.get('at'),'dur=',v.get('s'))
"
curl -s -o /dev/null -w "ext_health=%{http_code}\n" -m 10 https://leadsgenai.in/health
docker ps -a --format '{{.Names}}|{{.Status}}' | grep -Ei 'unhealthy|restarting' || echo "no unhealthy containers"
echo DONE
