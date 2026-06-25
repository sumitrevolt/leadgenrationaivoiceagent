# Runbook — Scheduler Failure

## Scenario
Scheduled jobs stop firing: beat is dead, the dead-man heartbeat goes stale, or
recurring loops (blog 06:30, content 07:00, prospect 09:30, outreach 10:30,
pipeline 11:00, QA 02:30, trainer 03:00) silently miss their window.

## Detection
- `automation_health` flags jobs overdue past `EXPECTED_GAP_MIN`.
- Heartbeats stale: `data/job_heartbeats.json` not advancing.
- ntfy/email `ops_alerts` readiness-digest shows missed runs.

## Immediate Response
1. Confirm which scheduler is live. **Production = Celery durable** (`leadgen_scheduler`
   beat + `leadgen_worker`), `RUN_IN_PROCESS_SCHEDULER=0`.
   ```bash
   docker ps --filter name=leadgen_scheduler --filter name=leadgen_worker
   docker logs --tail 80 leadgen_scheduler
   ```
2. If beat container is down/crashed, restart it:
   ```bash
   cd /opt/leadgen && docker compose -f docker-compose.vps.yml --profile celery up -d --no-deps --force-recreate scheduler worker
   ```

## Diagnosis
- **Dead-man trio:** heartbeat (`data/job_heartbeats.json`) + revive-beat (*/20min) +
  watchdog `ensure_alive`. If revive-beat itself is dead, the whole chain stalls.
- Boot-grace: heavy daily jobs SKIP on a boot that lands inside their window
  (restart-storm guard) — a *single* missed heavy job right after a restart is **expected**, not a failure.
- Scheduler ↔ Celery parity: every `team_scheduler._run_job` job must mirror in
  `worker.py` beat_schedule. Verify with `python scripts/cross_path_audit.py`
  (jobs 0-undispatchable, beat 0-unrecognized).

## Recovery
1. Restart beat + worker (above). Beat re-schedules all due jobs.
2. If Celery itself is the problem, **fail over to the rollback path**:
   ```bash
   # .env on VPS:
   RUN_IN_PROCESS_SCHEDULER=1
   WEB_CONCURRENCY=1
   # then: stop worker+scheduler, recreate app (in-process APScheduler takes over)
   ```
   This trades durability for liveness — use only until Celery is fixed.
3. Re-check queue depth after recovery (`redis-cli llen celery`, flush if > 500).
4. `python scripts/prod_check.py` → automation 0-gaps.

## Post-Incident
- RCA: beat crash vs revive-beat death vs OOM. Check `docker stats` for memory pressure.
- Confirm the job is in `automation_health.EXPECTED_GAP_MIN` so a future miss alerts.
- If a new loop was added without parity, wire it into both `team_scheduler` and
  `worker.py` beat + the gap registry (`scheduler-job` / `agent-loop-design` skills).
- Regression: `tests/test_loop_supervisor.py`, `test_ops_watchdog.py`.
