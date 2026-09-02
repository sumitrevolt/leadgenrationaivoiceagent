#!/usr/bin/env bash
# watch_sweep.sh — wait past the hourly :20 onboard sweep, then capture the
# empirical proof that the synthetic "Test Biz" PAID alert no longer fires.
set +e
{
  echo "WATCH_START=$(date -u +%H:%M:%S)"
  # sleep until ~:21:30 past the hour
  MIN=$(date -u +%M); SEC=$(date -u +%S)
  TARGET=$(( (21 - 10#$MIN) * 60 + (30 - 10#$SEC) ))
  if [ "$TARGET" -lt 0 ]; then TARGET=$(( TARGET + 3600 )); fi
  echo "SLEEPING ${TARGET}s until the :20 sweep completes"
  sleep "$TARGET"
  echo "WATCH_WAKE=$(date -u +%H:%M:%S)"

  echo "===STUCK LOG (last 4) — expect NO row at/after 13:20==="
  docker exec leadgen_app sh -c 'tail -4 data/delivery_stuck.jsonl 2>/dev/null'

  echo "===ONBOARD JOB RAN?==="
  docker logs --since 12m leadgen_worker 2>&1 | grep -c "job.*onboard"

  echo "===ANY NEW PAID-UNDELIVERED WARNING IN LAST 12m?==="
  docker logs --since 12m leadgen_worker 2>&1 | grep -c "PAID customer undelivered"

  echo "===QUEUES/DLQ==="
  docker exec leadgen_redis redis-cli llen celery
  docker exec leadgen_redis redis-cli llen dlq:failed_tasks

  echo "===HEALTH==="
  curl -s -m 10 127.0.0.1:8000/health; echo
  echo "WATCH_DONE"
} > /tmp/sweep_watch.log 2>&1 &
echo "WATCHER_LAUNCHED pid=$!"
