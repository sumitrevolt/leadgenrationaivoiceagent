# Approval reminder launch hardening — 2026-07-14

## Goal and approach

Make customer approval reminders safe to enable on launch day. The sweep must
fail closed without an explicit client scope and send at most one reminder per
customer, while Alembic-managed production gets the missing audit table.

## Change-risk tier

High-risk: outbound email automation plus an additive production DB migration.
Rollback: set `APPROVAL_EMAIL_NOTIFY=0`, recreate worker; code rollback to the
previous SHA; migration rollback is `alembic downgrade 017_add_lead_pipeline_tables`
only while the audit table is empty/disposable.

## File map

- `app/platform/approval_notifier.py`: allowlist and per-client selection.
- `tests/test_approval_notify_scheduler.py`: send-safety contracts.
- `alembic/versions/018_add_approval_notifications.py`: additive audit table.
- `tests/test_approval_notification_migration.py`: upgrade/idempotency/downgrade proof.
- `.env.example`: non-secret configuration names and safe defaults.

## Tasks and verification

1. Add failing contracts proving an empty allowlist sends zero emails and 22
   approvals for one client produce one send. Run the scheduler test and observe
   both failures before implementation.
2. Add mandatory `APPROVAL_EMAIL_CLIENT_ALLOWLIST` filtering and per-client
   dedupe. Run notification suites; expect all green.
3. Add revision 018 with model-parity columns/indexes. Run isolated SQLite
   upgrade twice, inspect indexes, downgrade, and confirm table removal.
4. Run notification tests, `prod_check.py`, `check_secrets.py`, and diff check.
5. Back up production, apply migration directly, deploy app/worker image, keep
   notification flag off until Jiya recipient eligibility is proven.

## Wiring and safety

The existing hourly Celery schedule and `APPROVAL_EMAIL_NOTIFY` kill switch stay
unchanged. No new route is added. `APPROVAL_EMAIL_CLIENT_ALLOWLIST` is runtime
configuration, empty by default, and must contain exact client IDs. Consent,
opt-out, DB idempotency, timeout, single-flight lock, and audit behavior remain.
