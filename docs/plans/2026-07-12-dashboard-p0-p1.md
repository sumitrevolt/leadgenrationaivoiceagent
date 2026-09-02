# Dashboard P0/P1 Fix Plan — 2026-07-12

## Goal

Close the confirmed customer/admin dashboard activation, auth-honesty, platform-dial, and destructive-action UX gaps without changing compliance gates or enabling outbound automation.

## Risk

Standard/high-risk boundary: customer-auth UI and admin system-summary contract. No billing truth, telephony gate, secret, migration, or outbound-send behavior is changed. Rollback is file revert plus app container recreate; `platform_dial` remains hard-off.

## File map

- `frontend/customer_dashboard.html`: setup CTA, authenticated client identity, webhook error states, approval notification banner, UPI billing fallback.
- `frontend/admin_dashboard.html`: platform-dial rendering, campaign button safety, bulk-delete progress/error honesty, God-Mode toast cleanup.
- `app/api/admin_ops.py`: expose read-only `platform_dial` state in admin summary.
- `tests/test_dashboard_p0_p1_fixes.py`: static contracts for every changed behavior.
- `docs/plans/2026-07-12-dashboard-p0-p1.md`: implementation contract.

## Tasks and acceptance

1. Add tests first and prove the current defects fail.
2. Fix setup CTA, remove URL `client_id` fallback, and make webhook auth/status errors explicit.
3. Render pending-approval customer notification from the existing authenticated delivery response; do not auto-send.
4. Add read-only platform-dial state to the admin summary and disable campaign firing while the effective kill switch is off.
5. Add bulk-delete progress and partial-failure reporting; preserve selection when failures occur.
6. Remove the dead customer billing portal function and replace old `alert()` God-Mode success paths with `adminToast`.
7. Run focused pytest, `prod_check.py`, `check_secrets.py`, duplicate-route scan, and JavaScript syntax checks.

## Verification

- Focused contracts: `tests/test_dashboard_p0_p1_fixes.py` plus existing dashboard/admin suites.
- Runtime gate: `.venv\\Scripts\\python.exe scripts\\prod_check.py`.
- Secret gate: `.venv\\Scripts\\python.exe scripts\\check_secrets.py`.
- No commit, push, or deploy in this implementation session.
