# Approval reminder zero-manual canary

Goal: First-party customer-login email ko safe fallback bana kar existing hourly approval reminder ko Redis-backed, one-tenant canary mode me chalana.

Approach: Marketing profile ka valid email first choice rahega; invalid/placeholder profile email par exact `client_id`-matched customer-auth login email use hoga. Existing env flag/allowlist compatible rahenge. Redis runtime flag `approval_email_notify` sirf `enabled_tenants` mode me env ke bina recipient scope de sakta hai; percentage rollout unsupported/fail-closed aur `APPROVAL_EMAIL_NOTIFY_HARD_OFF=1` sab par precedence lega.

Change-risk tier: **High-risk automation/email**. Gates: tenant isolation, consent/opt-out, happy + invalid-recipient + hard-off + idempotency tests, secrets scan, production check. Named rollback: Redis flag `approval_email_notify=disabled`; emergency precedence `APPROVAL_EMAIL_NOTIFY_HARD_OFF=1`; recreate worker only if code rollback is required.

## File map

- `app/api/customer_auth.py`: exact-client login-email read helper.
- `app/platform/approval_notifier.py`: valid-recipient fallback and runtime tenant scope.
- `app/api/automation_flags.py`: emergency hard-off visibility.
- `tests/test_approval_notifications.py`: fallback/tenant-isolation contracts.
- `tests/test_approval_notify_scheduler.py`: runtime canary/hard-off/idempotency contracts.
- `docs/plans/2026-07-14-approval-reminder-zero-manual.md`: this execution contract.

## Tasks

1. Add failing contracts proving a placeholder marketing email falls back only to the same client's login email, while a valid marketing contact keeps precedence.
2. Add failing scheduler contracts proving an `enabled_tenants=["jiya-makeover"]` runtime flag selects only that tenant, disabled/percentage/unknown states send zero, and hard-off wins.
3. Implement `client_login_email()`, structural email validation, runtime scope, and hard-off registry entry without changing scheduler cadence or send caps.
4. Run approval notification/scheduler/auth regression suites; update the stale signup-race assertion to the platform's standardized nested error envelope without changing its 409 behavior. Then run `prod_check.py`, secrets scan and diff checks.
5. Commit/push, build/recreate worker, set Redis flag to the single Jiya tenant, run one bounded sweep, then verify audit/idempotency/queues/health with recipient data masked.

## Wiring

No route, migration, scheduler or beat change. Existing hourly `approval_email_sweep` remains the only durable trigger. Runtime flag storage is existing Redis `feature_flags:store`; existing `FEATURE_FLAGS` master gate remains mandatory. `enabled_all` without the legacy env allowlist and percentage mode both select zero recipients.
