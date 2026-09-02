# Trainer timeout isolation

## Follow-up: cold skill-KB ingest

The first fix isolated synchronous telemetry, but live verification exposed a
second timeout source: when `SKILL_PACK=1`, the trainer synchronously called
`skill_pack.ingest_to_kb()`. FastEmbed cold initialization exceeded the Celery
540-second soft / 600-second hard limit. `SKILL_PACK_KB_INGEST` now gates that
expensive path separately and defaults OFF. Prompt lookup remains available;
manual/API ingestion is unchanged.

## Goal

Prevent the daily trainer analytics job from occupying a Celery worker for the full 600-second hard limit when staff-event persistence is slow or unavailable.

## Root cause

`app.agents.staff.run_trainer()` is async but called synchronous `team.log_event()` directly. `team.log_event()` can open/commit a database session and start side-effect publication, so a database/provider stall blocks the trainer coroutine and causes the observed `TimeLimitExceeded(600,)` DLQ item.

## Risk and rollback

High-risk scheduler/runtime fix. Trainer analysis remains unchanged; only its non-critical telemetry write moves off-loop with a 5-second caller deadline. Rollback is reverting the two-file code/test change and recreating the worker. No data migration, flag, or external send.

## File map

- `app/agents/staff.py` — bounded trainer telemetry helper and call-site owner.
- `tests/test_staff_jobs_smoke.py` — blocking telemetry regression owner.

## Contract

- Trainer analysis must return its result even if `team.log_event` blocks.
- Telemetry is best-effort; timeout logs a sanitized warning and does not fail/retry the trainer job.
- Existing normal telemetry remains asynchronous and receives the same event fields.

## Verification

Run trainer smoke/per-niche/threshold/failure tests, `prod_check.py`, `check_secrets.py`, and `git diff --check`. Do not replay or delete the production DLQ item in this change.
