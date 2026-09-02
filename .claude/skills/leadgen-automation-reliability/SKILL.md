---
name: leadgen-automation-reliability
description: Automation reliability hardening — Celery workers/beat, scheduled jobs, retries, idempotency, self-improve/coordinator/process-engine loops, task registration, job logs, silent failures. Use jab background work observable/retryable/safe banana ho ya silent-failure dhoondna ho.
---

# LeadGen Automation Reliability

> Enterprise audit skill. Automation useful output ya operational evidence banaye — silent noise nahi. `automation-pipeline`/`automation-flags` = build/flag map; **yeh = reliability audit**. Pehle `context-first`.

## Mission
Scheduled + background work ko observable, retryable, idempotent, safe banao.

## Repo truth
- **Durable Celery**: `WEB_CONCURRENCY=2` (uvicorn HTTP-only) + `RUN_IN_PROCESS_SCHEDULER=0` + `leadgen_worker` (concurrency=4) + `leadgen_scheduler` (beat), `--profile celery`. Web process KABHI heavy job na chalaye.
- **24 staff jobs** (IST schedule), sab **6-layer wired**, parity `scripts/prod_check.py` automation-gaps se guarded. **boot-grace**: heavy daily job ka window boot pe active ho to is boot SKIP (restart-storm prevent).
- **DLQ** → Redis `dlq:failed_tasks`. **Dead-man trio**: heartbeat (`data/job_heartbeats.json`) + revive-beat */20 + watchdog.
- **Flags**: `GET /api/growth/infra/flags` = saare automation flags live on/off.
- **Celery flood rule**: worker recreate ke baad `docker exec leadgen_redis redis-cli llen celery`; >500-800 = `redis-cli del celery` (beat re-schedules). `saturday_hygiene` auto-trims.

## Workflow
1. Task modules / beat schedules / queues / workers / cron / flags discover.
2. Automation registry banao: task-name · owner · trigger · queue · schedule · inputs · outputs · retries · logs · env-vars.
3. Critical P1 jobs safe test-data se run/simulate.
4. Missing registration · duplicate jobs · silent exception-swallow · non-idempotent writes · missing caps identify.
5. Tests: task registration · retry · failure-handling · output-creation.

## Enterprise checks
- Worker boot pe SAARE registered tasks import ho jaayein.
- Beat schedule business-expectation + IST timezone match.
- Tasks me retries + backoff + timeout + structured logs.
- Repeat-execution possible ho to idempotent.
- Missing env-var clear message ke saath fail-fast.
- Outreach jobs daily-cap + compliance-gate respect.

## Output
Automation registry · broken/unsafe task list · minimal reliability patch · worker/beat validation commands + expected evidence · readiness /100.

## Related repo skills (duplicate mat banao)
`automation-pipeline` + `automation-flags` + `automation-control-center` (flag/loop map) · `scheduler-job` (new job) · `self-improve-control` (self-improve safety) · `leadgen-infra-doctor` (worker/scheduler container health) · `leadgen-observability` (queue-lag alert).
