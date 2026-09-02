# ADR-2026-06-25: Batch 3 — Queue Idempotency + CRM Sync Prep

## Status
**Accepted** — implemented, committed.

## Context
Playbook audit identified Queue score at 70/100 with 0% idempotency coverage across 15 Celery tasks. CRM sync code exists but is gated OFF (`CRM_SYNC=0`).

## Decision
1. Add a reusable `@idempotent_task` decorator using Redis `setnx` for deduplication.
2. Apply it to the two most critical task modules: `staff_jobs.run_staff_job` and `brain_training.train_all_brains`.
3. Leave CRM sync activation as an env-flag change (documented but not forced — needs user to set `CRM_SYNC=1` + credentials).

## Changes

### 1. `app/tasks/idempotency.py` (NEW)
- `@idempotent_task(task_name, ttl=3600)` decorator
- Uses Redis `SET key "1" NX EX ttl` for atomic deduplication
- Returns `{"ok": True, "skipped": "duplicate"}` on duplicate detection
- Gracefully degrades if Redis is unavailable (logs warning, proceeds)

### 2. `app/tasks/staff_jobs.py` (MODIFIED)
- Added `from app.tasks.idempotency import idempotent_task` import
- Applied `@idempotent_task("run_staff_job", ttl=3600)` to `run_staff_job()`
- All 24 staff jobs now inherit idempotency via this single wrapper

### 3. `app/tasks/brain_training.py` (MODIFIED)
- Added `from app.tasks.idempotency import idempotent_task` import
- Applied `@idempotent_task("train_all_brains", ttl=21600)` to `train_all_brains()`
- 6-hour TTL matches the training schedule (prevents duplicate within same window)

## Impact Assessment
- **Risk:** LOW — additive decorator, graceful degradation
- **Production paths modified:** YES (2 task files) but only by adding decorators
- **Rollback:** Remove decorator lines + delete `idempotency.py`
- **Idempotency coverage:** 0% → ~15% (2 of ~15 tasks, but covers the most critical paths)

## Verification
```bash
python -c "from app.tasks.idempotency import idempotent_task; print('import OK')"
python -c "from app.tasks.staff_jobs import run_staff_job; print('staff_jobs OK')"
python -c "from app.tasks.brain_training import train_all_brains; print('brain_training OK')"
```

## Gaps Remaining
- ~13 other Celery tasks still need idempotency decorators
- CRM sync activation requires `CRM_SYNC=1` + Zoho/HubSpot credentials in `.env`
- Queue schema versioning, replay process, and queue-depth alerts still needed

## References
- Playbook Audit: `docs/PLAYBOOK_AUDIT_2026_06_25.md`
- Batch 1 ADR: `docs/archive/2026-06/ADR-2026-06-25-Batch1-Security-Queue-Audit.md`
- Batch 2 ADR: `docs/ADR-2026-06-25-Batch2-Testing-E2E.md`
