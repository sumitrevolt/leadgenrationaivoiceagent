# Runbook — Billing Incident

## Scenario
A payment/invoice problem: customer paid but not activated, a UPI claim to verify, a
suspected duplicate invoice/charge, or a GST/invoice-numbering question.

> **Zero-tolerance gate:** billing must never duplicate invoices. The controls below
> are the proof that gate holds.

## Standing controls (the safety net)
- **Single source of truth:** `app/marketing/packages.py` (`subscription._sync_plans_from_packages`).
  Pricing change = `packages.py` + `test_billing_truth_2026.py` together.
- **Invoice numbering:** atomic, sequential, Rule-46 (`INV/2026-27/0001`), SAC 998313.
  GST charged **only** when `GST_GSTIN` is set (unregistered = no tax).
- **Idempotency:** `verify-payment` is PENDING + idempotent (H1); webhook handlers idempotent.
- **IDOR:** every billing mutation guarded by `_authed_client_id` (C1).
- **Payments path:** **manual UPI** is primary (`app/platform/upi_config.py`,
  `GET /api/public/pay-info`). Razorpay fully removed. Stripe intact for international.

## Detection
- Customer reports paid-but-inactive; admin sees mismatch; reconciliation flags a gap.
- `payment.received` / `subscription.*` webhook anomalies.

## Immediate Response
1. **Do not** re-issue an invoice or re-charge before checking idempotency state —
   that is exactly the duplicate the gate forbids.
2. Pull the customer's billing record (admin) + invoice ledger; confirm the
   sequential number and whether a row already exists.
3. For a UPI claim: verify the submitted reference against the bank/notification;
   activation is manual-confirm by design (no auto-gateway).

## Diagnosis
- Was the payment captured but activation hook not fired? Check `payment.received` emit.
- Duplicate suspicion: invoice numbering is atomic — two rows with the **same** number
  is impossible by construction; two *different* numbers for one payment = the real bug
  (trace the idempotency key on `verify-payment`).
- GST applied unexpectedly? Confirm `GST_GSTIN` state.

## Recovery
1. If activation simply didn't fire, run the activation manually (admin), do **not** re-charge.
2. If a genuine duplicate invoice row exists, void the later one (keep audit trail) and
   record an ADR — duplicate billing is a certification blocker, treat as P1.
3. Reconcile: confirm ledger == payments == active subscription.

## Post-Incident
- RCA + regression: extend `tests/test_billing_truth_2026.py`,
  `tests/test_payment_webhooks.py`, `tests/test_billing_auth_idor.py`.
- If the activation hook was the gap, wire/verify the `payment.received` → activation path.
- Record decision as `docs/ADR_*.md` if the billing flow changed.
