# System health fixes — 2026-07-11

## Goal

Repair the verified local/runtime reliability failures without weakening compliance gates or enabling external-send features implicitly.

## Risk tier

High-risk: touches Celery/async database lifecycle, logging/security verification, and production integration health.

## File map

| Owner | Files | Responsibility |
|---|---|---|
| Main | `app/tasks/staff_jobs.py` | Per-Celery-process event-loop lifecycle and safe shutdown |
| Main | `tests/test_staff_jobs_smoke.py` or new focused test | Regression proof for loop reuse and cleanup |
| Main | `tests/test_logging_redaction.py` | Replace secret-shaped fixtures with non-secret equivalents while preserving redaction coverage |
| Main | `scripts/agent_flow_check.py` | Make repo-root imports deterministic for the diagnostic probe |
| Main | `scripts/workflow_gap_probe.py` | Make local-vs-live dependency state explicit; never report local failure as live failure |
| Main | `app/marketing/postiz_publish.py` | Add bounded Postiz health probe only if existing status path lacks one; no credential creation |
| Main | `progress.md` | Loop evidence only after verification |

## Tasks and gates

1. Reproduce the Celery loop issue with a focused unit test that runs two coroutines through the wrapper and asserts the same loop is reused; expected RED before implementation.
2. Implement persistent per-worker loop reuse, cancel pending tasks only on explicit shutdown, and expose a test-reset hook without touching production flags.
3. Run focused staff/scheduler/async tests and confirm no event-loop warnings in the test process.
4. Replace GitHub-token-shaped test literals with structurally equivalent inert fixtures; run the redaction test and `check_secrets.py`.
5. Repair diagnostic script import path and output semantics; add tests or static assertions for repo-root execution.
6. Validate Postiz/WAHA/Vobiz without sending messages, calls, or creating credentials. External user actions remain blockers.
7. Run `prod_check.py`, focused pytest, secret scan, duplicate-route/static wiring checks, then re-audit live health. No deploy until an explicit live deployment authorization is confirmed.

## Wiring and rollback

- No new env flag or scheduler entry.
- Rollback is a surgical revert of the changed files; no DB migration and no data deletion.
- WAHA QR/session recovery and Postiz OAuth/API-key setup are operator actions, not code changes.
- Compliance gates, `PLATFORM_DIAL` hard-off, WhatsApp auto-send gates, and free-provider policy remain unchanged.
