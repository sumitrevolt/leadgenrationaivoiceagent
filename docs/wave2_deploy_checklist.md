# Wave 2 Fix: Gated-Inert DLQ Semantic Bug — Deployment Checklist

## Fix Summary
**File:** `app/tasks/staff_jobs.py` (line 485-495)
**Problem:** Gated-off jobs (e.g., `VIDEO_TELEGRAM_DELIVERY_ENABLED=0`) return `ok=False`, which `run_staff_job()` treated as failure → Celery retry → DLQ fill.
**Solution:** Check `automation_health.gated_inert(job)` before raising. If gated, return `{"ok": True, "status": "gated_inert"}` — no retry, no DLQ.

## Pre-Deploy Verification
- [ ] `git diff` shows only `app/tasks/staff_jobs.py` and `tests/test_gated_inert_dlq_regression.py`
- [ ] `pytest tests/test_gated_inert_dlq_regression.py -v` → 3/3 PASS
- [ ] `pytest tests/test_gated_inert_heartbeat.py -v` → all PASS (regression)
- [ ] `prod_check.py` → no new FAILs

## Deploy Steps (Owner Action)
1. **Dry-run:** `DRY_RUN=1 bash scripts/deploy_vps.sh` → verify plan
2. **Deploy:** `bash scripts/deploy_vps.sh` → canonical deploy
3. **Verify:** `curl http://127.0.0.1:8000/health` → `version: <new-sha>`
4. **Wait:** 1 natural 15-minute retry tick (video_delivery_retry runs hourly :15)
5. **Confirm:** `redis-cli llen dlq:failed_tasks` → still 0 (no new false positives)
6. **Archival:** After clean tick, move 34 historical dead rows to `dlq:resolved` with resolution="GATED_INERT_FALSE_POSITIVE"

## Post-Deploy Verification
- [ ] `/health.version` = deployed SHA (not `:latest`)
- [ ] All containers same image digest
- [ ] `celery` queue = 0 (no backlog)
- [ ] `dlq:failed_tasks` = 0 (no new false positives after fix)
- [ ] `dlq:dead` = 34 (historical, pending archival)
- [ ] `automation_health.health()` shows `video_delivery_retry` status = `gated_inert` (not `last_failed`)

## Rollback Plan
- **If issue:** `git revert <fix-commit>` → redeploy previous SHA
- **Historical DLQ:** 34 dead rows remain harmless (already dead, no active impact)

## Success Criteria
1. ✅ Gate OFF still records `status=gated_inert, ok=False` in health/history
2. ✅ `run_staff_job("video_delivery_retry")` completes without Celery retry
3. ✅ Genuine `_run_job_inner=False` (non-gated) still retries/fails
4. ✅ No customer delivery occurs with flag OFF
5. ✅ Regression test proves gated-inert jobs never enter `dlq:failed_tasks`

---
Created: 2026-09-18 05:30 IST
🐦 pelican