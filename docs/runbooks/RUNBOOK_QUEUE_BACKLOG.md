# Runbook — Queue Backlog

## Scenario
Celery queue depth grows beyond threshold; staff-jobs (outreach, content, digests,
prospect, voice QA) are delayed or piling up. Often follows a worker recreate or a
provider stall holding tasks open.

## Detection
- `automation_health` reports overdue jobs / `EXPECTED_GAP_MIN` exceeded.
- ntfy/email `ops_alerts` "dead-letter" or "queue backlog" fan-out.
- Manual: Redis queue length.
```bash
ssh … root@72.61.245.204
docker exec leadgen_redis redis-cli llen celery
```

## Immediate Response
1. If customer-facing jobs are stalled, declare incident; assign one owner.
2. **Hard rule:** if `llen celery` **> 500** → the queue is full of transient/regenerable
   tasks. Flush it (beat re-schedules everything):
   ```bash
   docker exec leadgen_redis redis-cli del celery
   ```
3. Pause the noisy loop via its flag if a single engine is flooding (e.g.
   `AUTO_EMAIL_OUTREACH=false`) — flags are inert when OFF, no deploy needed.

## Diagnosis
- Recent deploy? (`docker ps` uptime on `leadgen_app`/`leadgen_worker`).
- Worker alive + consuming? `docker logs --tail 100 leadgen_worker`.
- A provider stall holding tasks open? → see [Provider Outage](RUNBOOK_PROVIDER_OUTAGE.md).
- Dead-letter backlog: `docker exec leadgen_redis redis-cli llen dlq:failed_tasks`.
- Scheduler actually emitting? → see [Scheduler Failure](RUNBOOK_SCHEDULER_FAILURE.md).

## Recovery
1. Flush `celery` if > 500 (above). Tasks are idempotent + regenerable; beat re-schedules.
2. Recreate the worker if wedged:
   ```bash
   cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps --force-recreate worker
   ```
   **After any worker recreate, re-check `llen celery` and flush if > 500** (operating-manual rule).
3. Drain dead-letter with the wired sweeper (gated `DLQ_AUTO_RETRY`): `dlq_retry.run_sweep()`
   (call-sites: `team_scheduler.py` watchdog, `scheduled_ops.py` Sat-hygiene, API `growth.py`).
   `MAX_ATTEMPTS=2` → `dlq:dead` + email alert.
4. Run `python scripts/prod_check.py` from VPS app container; confirm automation 0-gaps.

## Post-Incident
- RCA: what produced the flood (re-entrant loop? provider stall? missing dedupe?).
- If a loop lacked period-dedupe, add success-only state-file marking (`audit-automation` pattern).
- Verify `automation_health.EXPECTED_GAP_MIN` registers the affected job (dead-man coverage).
- Add/extend a regression test in `tests/test_meter_watch.py` / `test_ops_watchdog.py` if wiring changed.
