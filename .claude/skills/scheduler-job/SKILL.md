---
name: scheduler-job
description: Engineer a new scheduled/recurring automation job the LeadGen AI way — in-process APScheduler (team_scheduler.py) + optional durable Celery-beat path + DLQ. Use when adding a recurring task, "naya scheduled job", "cron job", "har din/ghante chalao", "celery beat", "background automation job", or wiring a new AI-staff job.
---

# Scheduler Job (recurring automation · single-instance safe)

2 paths: (a) **in-process** `app/platform/team_scheduler.py` (default, loop + IST windows + single-instance lock) — aaj sab yahin; (b) **durable Celery-beat** `app/tasks/staff_jobs.py` + `worker.py` (opt-in `--profile celery` + `RUN_IN_PROCESS_SCHEDULER=0`, DLQ on failure).

## Add an in-process job (team_scheduler.py)
1. **Register key** in `_last_ran` dict: `"myjob": None`.
2. **Handler** in `_run_job(job)`: `elif job == "myjob": from app.x import y; await y.run()`. **Local import** (ek module fail dusre ko na tode).
3. **Schedule** in `scheduler_loop()` — IST window + dedupe key:
   ```python
   if (7, 0) <= hm < (9, 0) and _last_ran["myjob"] != day_key:
       _last_ran["myjob"] = day_key
       await _run_job("myjob")
   ```
   Hourly = `now.minute >= N and _last_ran["myjob"] != hour_key`. 15-min = `slot_key`.
4. **Gate it** default-OFF: `if os.environ.get("MYJOB","0").lower() in ("1","true"):` (see `automation-flags` skill).

## Durable (Celery, optional)
`app/tasks/staff_jobs.py` me task + `worker.py` beat entry. Fire tabhi jab `celery beat` chale (`RUN_IN_PROCESS_SCHEDULER=0` se double-run avoid). DLQ: failed → Redis `dlq:failed_tasks` (`worker.py on_task_failure`).

## Rules (project discipline)
- **Never-raise**: `_run_job` try/except wrap karta — ek job fail = baaki chalein.
- **Single-instance lock** (`data/.scheduler.lock`, heartbeat + dead-PID reclaim) double-run rokta — naya job apne aap safe.
- **Gated + default-OFF** = zero behaviour change jab tak flag na ho.
- Heavy kaam async + timeout; real-time voice path me scheduler kaam mat daalo (latency).

## Verify
`import app.main` OK → `scripts/prod_check.py` PASS → flag set → container recreate → next window pe `data/*.jsonl`/team_event. `docker logs leadgen_app | grep "running job: myjob"`.
