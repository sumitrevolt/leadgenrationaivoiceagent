# SESSION_HANDOFF - overwrite every session end

## Session objective
Fix the 12 OpenCode issues found in the 2026-08-02 live launch-check session. No deploy unless the owner asks.

## Progress — ISSUES FIXED (local, 2026-08-02)
- ISSUE-01 WAHA status UI — `frontend/whatsapp.html`: FAILED/SCAN_QR_CODE/WORKING states, QR auto-refresh (20s), Start-button poll. Backend endpoints already existed.
- ISSUE-02 CSP PostHog — `app/middleware/__init__.py`: `_posthog_src` in script-src + connect-src on non-embeddable pages only. Tests: `tests/test_csp_posthog_allowlist.py` (3 passed).
- ISSUE-03 Sales autopilot idle — `app/platform/sales_autopilot/scheduler.py`: explicit `idle_reason="no_eligible_prospects"` + status-count breakdown in `last_tick.json`; `frontend/automation.html` Schedule tab surfaces it. Tests: 2 added, scheduler+CSP suite green (21 passed).
- ISSUE-04 Staging `:latest` — `docker-compose.staging.yml`: `APP_VERSION` now MANDATORY (`${APP_VERSION:?...}`), `:latest` refused (ADR-097). Compose fail-closed verified locally.
- ISSUE-05 Context docs refresh — `CURRENT_STATE.md` (prod `15613b35`, autopilot live, WAHA FAILED, staging fail-closed) + `ACTIVE_WORK.md` (3 workstreams) rewritten.

## Known (pre-existing, NOT mine)
- `test_email_channel_fail_closed_without_smtp` FAILS locally because local `.env` has SMTP configured → send() attempts real send → outcome SKIPPED vs test's expected FAILED. Passes only in clean CI env (no SMTP creds). Verified pre-existing via git-stash isolation.

## Owner actions (exact)
1. Open `/app/whatsapp` → restart WAHA session → scan QR before timeout → reply `WAHA CONNECTED`
2. Feed sales_autopilot new non-converted prospects (or accept idle until new leads)
3. Confirm Estique payment ledger (autopilot shows `converted`)

## Safety
No deploy this session. `WHATSAPP_AUTO_SEND=0` stays. Dial test-mode cap 10. Do not paste WAHA webhook tokens from logs into chat/PRs. Verify (pytest targeted + prod_check + secrets scan) before any deploy.
