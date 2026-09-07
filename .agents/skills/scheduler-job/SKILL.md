---
name: scheduler-job
description: Engineer a new scheduled/recurring automation job the LeadGen AI way — durable Celery-beat (PRIMARY, live) + in-process APScheduler (rollback path) + DLQ. Use when adding a recurring task, "naya scheduled job", "cron job", "har din/ghante chalao", "celery beat", "background automation job", or wiring a new AI-staff job.
---

# Scheduler Job (recurring automation · single-instance safe)

2 paths, alag primacy:
- **(a) Durable Celery-beat = PRIMARY / LIVE** (`app/tasks/staff_jobs.py` tasks + `app/worker.py` `beat_schedule`). VPS pe `leadgen_worker` + `leadgen_scheduler` containers chal rahe hain (`--profile celery`), `.env`: `RUN_IN_PROCESS_SCHEDULER=0` + `WEB_CONCURRENCY=2`. Restart-safe, retry, DLQ on failure.
- **(b) In-process APScheduler = ROLLBACK path** (`app/platform/team_scheduler.py`, loop + IST windows + single-instance lock). Sirf tab active jab `RUN_IN_PROCESS_SCHEDULER=1` + `WEB_CONCURRENCY=1` (rollback config). Default-live me yeh OFF — Celery tick ko team_scheduler khud skip karta (`_run_job_inner` me `RUN_IN_PROCESS_SCHEDULER` check).

> Naya job dono jagah register karo taaki rollback pe bhi chale. Production me Celery-beat path hi fire karega.

## Durable Celery job (PRIMARY — yeh pehle)
1. **Task**: `app/tasks/staff_jobs.py` me `run_staff_job` already generic dispatcher hai — naya staff-job iska `job` key add karke route hota. Custom task = `@celery_app.task(bind=True, max_retries=3)` in `worker.py`.
2. **Beat entry**: `app/worker.py` `celery_app.conf.beat_schedule` me dict entry — `{"task": "app.tasks.staff_jobs.run_staff_job", "schedule": <crontab/seconds>, "args": ["myjob"], "options": {"queue": ...}}`. Existing `staff-*` entries pattern dekho (`staff-ops-hourly`, `staff-qa-daily`, etc.).
3. **Heavy job?** → `heavy` queue (`-Q heavy` worker, concurrency=1) taaki light jobs (alerts/dunning/triage) starve na hon. `CELERY_HEAVY_QUEUE=1` send-side routing on karta.
4. **DLQ**: failure → `worker.py on_task_failure` → Redis `dlq:failed_tasks` (last 1000). Verify wahin.

## In-process job (ROLLBACK path — team_scheduler.py)
Agar rollback config (`RUN_IN_PROCESS_SCHEDULER=1`) pe bhi chahiye:
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

## Rules (project discipline)
- **Never-raise**: `_run_job`/task try/except wrap karta — ek job fail = baaki chalein.
- **No double-run**: Celery beat single scheduler container; in-process path beat-mode me khud disable hota. team_scheduler me bhi `data/.scheduler.lock` (heartbeat + dead-PID reclaim).
- **Gated + default-OFF** = zero behaviour change jab tak flag na ho.
- Heavy kaam async + timeout; real-time voice path me scheduler kaam mat daalo (latency).
- **Boot-grace**: heavy daily job ka window agar boot pe active ho to is boot pe SKIP (restart-storm prevent — in-process path). Celery profile me yeh non-issue (dedicated scheduler).

## Verify
`import app.main` OK → `scripts/prod_check.py` PASS → rebuild + recreate (`worker` + `scheduler` bhi: `--profile celery up -d --no-deps worker scheduler`) → beat next window pe fire → `docker logs leadgen_scheduler | grep myjob` + `docker logs leadgen_worker` + `data/*.jsonl`/team_event. After worker recreate: `redis-cli llen celery` (>500 = `del celery`).

## Enterprise gate

- **Operating loop**: Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). Discover me **dono** paths grep karo (Celery beat + team_scheduler) warna job ek path me wired, dusre me nahi (cross-path gap = real prod lesson).
- **Risk-tier: High** (automation loop) — naya durable job blast-radius = poora worker. Locks: Celery↔APScheduler parity, `automation_health.EXPECTED_GAP_MIN` registry entry (dead-man), `AUTOMATION_FLAGS` (growth.py) registry so `/api/growth/infra/flags` pe dikhe.
- **Net-new beyond the patterns above:**
  - **Idempotency** (only if job sends/bills/posts/CRM-writes): success-pe-hi-mark dedupe key (state-file / DB row), warna beat ka re-fire = duplicate email/call/bill. team_scheduler `_last_ran[day_key]`-style + engine-side ledger.
  - **DLQ-on-failure already covered** (`worker.py on_task_failure` → `dlq:failed_tasks`) — naye task me `max_retries` + bounded backoff set karo, raise mat swallow karo bina record kiye.
  - **Rollback (NAMED)**: flag OFF + worker/scheduler recreate (job inert) · ya full rollback config `RUN_IN_PROCESS_SCHEDULER=1`+`WEB_CONCURRENCY=1` (APScheduler path). Beat entry bug = remove entry + scheduler recreate.
- **Evidence (done)**: `.venv\Scripts\python.exe scripts\prod_check.py` PASS + changed-file pytest + `docker logs leadgen_scheduler | grep myjob` (beat fired) + `data/*.jsonl`/team_event (real output) + `redis-cli llen celery` sane.
