# Customer activation recovery — first fix batch

## Goal

Make pending customer approvals impossible to miss so the existing delivery pipeline can convert generated content into visible customer value.

## Risk

Standard: customer-facing UI and an existing response payload only. No new route, database migration, outbound send, WhatsApp action, pricing change, or feature flag. Rollback is reverting the two-file change.

## File map

- `app/api/customer_dashboard.py` — response contract owner; expose a bounded, PII-safe approval banner model from the existing dashboard payload.
- `frontend/customer_dashboard.html` — customer UI owner; render the banner and link to the existing approval card.
- `tests/test_customer_activation_banner.py` — regression owner; lock payload and HTML behavior.

## Tasks

1. Read the existing dashboard response builder, approval endpoint, and dashboard render path.
2. Add a derived `approval_banner` object only when pending approvals exist; include count, urgency, and a fixed internal action target. Never include lead data or raw evidence URLs.
3. Render an accessible, dismissible-but-reappearing banner above the customer dashboard content; do not auto-approve, publish, email, or WhatsApp-send.
4. Add tests for zero pending, one pending, multiple pending, safe fields, and the existing approval-card target.
5. Run focused pytest, `prod_check.py`, `check_secrets.py`, and diff review.

## Wiring and rollback

No new route or flag. Existing customer auth and approval endpoint remain the source of truth. Rollback is reverting the additive payload/UI/test change; no data repair is needed.
