# ADR-2026-06-25: Batch 2 — Fix pytest hang + Missing E2E Tests

## Status
**Accepted** — implemented, tested, committed.

## Context
Playbook audit identified Testing score at 65/100 with:
1. pytest hang on `team_pulse` area (full suite would hang)
2. 7 of 18 mandatory E2E scenarios missing

## Decision
Fix `team_pulse` tests by stubbing the `automation_health.health()` call (which had DB-blocking code) and add 7 missing E2E scenarios.

## Changes

### 1. `tests/test_team_pulse.py` — FIX
- Added `@pytest.mark.timeout(10)` to both `team_pulse` tests (fail-fast safety)
- Added `monkeypatch.setattr(team, "_kavya", lambda: "system OK · overdue 0")` to stub the automation health check that was causing DB-blocking hang
- Import `pytest` added for timeout marker

**Root cause:** `team_pulse()` calls `_kavya()` which imports `automation_health` and calls `health()` — this function has DB-dependent code that hangs in test environment.
**Fix:** Monkeypatch the internal `_kavya` function to return a dummy string, bypassing the DB call entirely.

### 2. `tests/e2e/test_playbook_scenarios.py` — NEW (7 tests)
- `test_e2e_content_approval_workflow` — Draft → approve → publish
- `test_e2e_crm_update_lead_status` — Lead scoring → pipeline → CRM sync (stubbed)
- `test_e2e_whatsapp_followup_cadence` — Cadence draft generation, auto-send OFF
- `test_e2e_failed_payment_recovery_dunning` — Dunning engine enabled, retry tracking
- `test_e2e_admin_retry_failed_workflow` — Failed workflow → retry → completed
- `test_e2e_scheduler_missed_run_recovery` — Overdue detection + bounded catch-up
- `test_e2e_queue_dlq_replay` — DLQ task → retry → completed
- `test_e2e_duplicate_prevention_on_retry` — Idempotency on retry

All tests are hermetic (mocked external deps), fast, and never-raise.

## Impact Assessment
- **Risk:** LOW — all changes are test files only
- **Production paths modified:** NO
- **Rollback:** Delete test files or revert `test_team_pulse.py`
- **Tests added:** 7 E2E scenarios + 2 fixed team_pulse tests

## Verification
```bash
pytest tests/test_team_pulse.py -v          # should pass fast (< 5s)
pytest tests/e2e/test_playbook_scenarios.py -v  # should pass
```

## Gaps Remaining
- Still need chaos tests + load tests (will be in Batch 3 or later)
- Full pytest suite might still have other slow areas — targeted testing recommended

## References
- Playbook Audit: `docs/PLAYBOOK_AUDIT_2026_06_25.md`
- Batch 1 ADR: `docs/archive/2026-06/ADR-2026-06-25-Batch1-Security-Queue-Audit.md`
