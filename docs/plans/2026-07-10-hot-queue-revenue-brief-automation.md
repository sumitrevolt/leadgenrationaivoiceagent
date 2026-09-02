# Hot Queue Revenue Brief Automation

## Goal and approach

Generate the existing Office HQ morning briefing automatically once per IST day, with the existing prioritized Hot Queue and draft-only `/app/inbox` workflow as the revenue action surface. The scheduled path must fail closed when automation health is degraded, write only local/admin-visible artifacts, and remain inert unless `HOT_QUEUE_BRIEF_DAILY=1`.

## Risk tier and rollback

**High-risk — automation loop.** This touches both durable Celery beat and the in-process rollback scheduler. Named rollback: set `HOT_QUEUE_BRIEF_DAILY=0`, recreate worker/scheduler containers, and leave the existing on-demand `/app/office` briefing endpoint unchanged. No migration or data repair is required; daily JSON/MP3 cache files are disposable.

## File ownership map

- `tests/test_hot_queue_brief_schedule.py` — behavior contract: disabled, unhealthy fail-closed, successful cached generation, and wiring parity.
- `app/platform/office_briefing.py` — scheduled wrapper, health preflight, idempotent reuse of the daily cache, and admin event evidence.
- `app/platform/team_scheduler.py` — dispatcher key and 08:15 IST rollback schedule.
- `app/tasks/staff_jobs.py` — durable dispatcher allowlist.
- `app/worker.py` — 08:15 IST Celery beat entry and heavy-queue routing.
- `app/platform/automation_health.py` — daily dead-man SLO.
- `app/platform/today_overview.py` — due-time and non-technical operator label.
- `app/api/automation_flags.py` — default-OFF kill-switch visibility.
- `progress.md`, `memory/decisions.md`, `CLAUDE.md`, `AGENTS.md` — evidence ledger and durable decision write-back.

### Verification-gate blocker discovered during execution

`prod_check.py` exposed a pre-existing FastAPI 0.139 compatibility defect: included routers are lazy `_IncludedRouter` objects, while the startup sweep, production gate, and deep wiring audit inspect only direct `.path` attributes. The lockfile already pins this version, so the gate reports hundreds of false missing routes. Minimal root-cause fix ownership:

- `tests/test_route_inspection.py` — nested-router contract against the locked FastAPI runtime.
- `app/utils/route_inspection.py` — one compatibility helper using FastAPI's public `iter_route_contexts`, with eager-version fallback.
- `app/main.py`, `scripts/prod_check.py`, `scripts/deep_wiring_audit.py` — consume effective route contexts without changing registered routes.
- `app/api/upi_payments.py` — restore the accidentally deleted `BaseModel` import found by the first gate run; no behavior change.

Shared scheduler/worker/config files are edited sequentially only by the main session.

## Tasks and verification

1. Add `tests/test_hot_queue_brief_schedule.py` before production edits. Assert: flag OFF performs no generation; degraded health skips generation and logs a warning event; healthy repeated calls reuse `build_briefing(force=False)`; scheduler/Celery/health/flag/overview registries all contain `hot_queue_brief`. Run the focused test and confirm RED because the scheduled wrapper and wiring do not exist.
2. Add `office_briefing.run_scheduled()` with a default-OFF flag, `automation_health.health()` preflight, no external notification, existing daily cache reuse, and best-effort `team.log_event` evidence. A degraded/unknown preflight returns `False`-equivalent job status and never calls LLM/TTS generation.
3. Wire `hot_queue_brief` into `team_scheduler` at 08:15–09:15 IST, `STAFF_JOBS`, Celery beat at 08:15 IST, heavy routing, `EXPECTED_GAP_MIN=30h`, `_DUE_AFTER_IST`, operator label, and `AUTOMATION_FLAGS`.
4. Run the focused test until GREEN, then the existing office briefing and scheduler wiring regressions. Run `prod_check.py`, `check_secrets.py`, duplicate wiring searches, and inspect the scoped diff.
5. Append the canonical loop evidence to `progress.md`; append the automation decision to `memory/decisions.md`; record the dormant default-OFF loop in Current State and byte-sync `AGENTS.md` from `CLAUDE.md`.
6. RED-test nested route inspection, add the compatibility helper, update the three inspection consumers, then rerun `prod_check.py` to prove real routes are counted under FastAPI 0.139. This is gate-only; application routing and prefixes remain unchanged.

## Enterprise gates

- Outcome: one daily admin-only revenue brief; owner: operator/Rohan; trigger: 08:15 IST; output: existing Office HQ JSON/MP3 plus `/app/inbox` human actions.
- Failure behavior: degraded/unknown automation health skips generation and records a failed heartbeat/admin event.
- Idempotency: existing one-file-per-IST-day cache; repeated runs use `force=False`.
- Retry/DLQ: existing `run_staff_job` bounded retries and worker DLQ.
- Cost/backpressure: one bounded free-LLM/TTS call per day; routed to heavy queue.
- Compliance: no email, WhatsApp, call, publish, billing, customer-data mutation, or deploy action.
- Test matrix: happy path, disabled path, unhealthy path, repeated-call idempotency, and both scheduler paths.

## Fresh-review hardening

Independent review converted six findings into regression contracts: unknown queue depth and other-job failures fail closed; concurrent runs use one atomic daily claim with stale recovery; reported failure reaches Celery retry/DLQ; both scheduler paths honor boot grace; the job ignores only its own prior failed heartbeat to avoid permanent self-deadlock; and an atomic cache-write refusal is a real failure with orphan-audio cleanup. The final review reported no P0/P1/P2 finding. Final brief suite: 11/11 green.
