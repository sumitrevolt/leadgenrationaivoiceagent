# Wave 2 Fix: gated-inert semantic bug / false-DLQ amplification
# 
# Problem: When VIDEO_TELEGRAM_DELIVERY_ENABLED=0 (or any gated job OFF),
# team_scheduler._run_job returns ok=False and records status="gated_inert"
# in automation_health for observability. However, staff_jobs.run_staff_job()
# treats ok=False as a failure and raises RuntimeError, which triggers
# Celery retry (max_retries=2) and eventually fills dlq:failed_tasks/dlq:dead.
# 
# 34 dead video_delivery* entries are false positives — the gate is OFF by design,
# not a pipeline failure.
#
# Fix: In run_staff_job(), check gated_inert() before raising. If gated, return
# {"ok": True, "job": job, "status": "gated_inert"} — no retry, no DLQ.
#
# Acceptance criteria:
# 1. Gate OFF still records status=gated_inert, ok=False in health/history
# 2. run_staff_job("video_delivery_retry") completes without Celery retry
# 3. Genuine _run_job_inner=False still retries/fails (non-gated job)
# 4. No customer delivery occurs with flag OFF
# 5. Regression test proves gated-inert jobs never enter dlq:failed_tasks
