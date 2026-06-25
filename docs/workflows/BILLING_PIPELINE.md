# Billing Pipeline — Production Contract

**Workflow ID:** `billing.invoice` · **Version:** 1 · **Owner:** Nikhil (Revenue Ops) + Vidya (FinOps)
**Trigger:** checkout / UPI submit / subscription event → `billing/subscription.py`, `platform/upi_config.py`

> **Zero-tolerance:** must never duplicate invoices. Controls below are the proof.

## State machine
```
PENDING → VERIFIED → INVOICE_NUMBERED → ACTIVATED → METERED  [terminal: ACTIVE]
   │          │              │              │
   └──────────┴──────────────┴──────────────┴──► FAILED/REFUNDED (terminal, audited)
```
- **Idempotent transitions:** `verify-payment` is PENDING + idempotent (H1); re-trigger = no-op, not re-charge.

## Step → module map (real code)
| Step | Module | Idempotency / control |
|---|---|---|
| Plans (truth) | `billing/packages.py` (`_sync_plans_from_packages`) | single source of truth |
| Verify payment | `api/billing.py` verify-payment | idempotency key (H1) |
| Invoice number | `billing/subscription.py` | **atomic sequential** `INV/2026-27/NNNN`, SAC 998313 |
| GST | gated on `GST_GSTIN` | Rule-46; unregistered = no tax |
| Activate | subscription activation | subscription id |
| Meter | `billing/lead_usage.py` / `usage.py` | FAIL-OPEN, per-call/lead key |
| Pay path | manual UPI (`upi_config.py`, `/api/public/pay-info`); Stripe = international | — |

## Validation & reliability
IDOR closed on every mutation (`_authed_client_id`, C1). Webhook signatures fail-closed in prod.
Dunning recovery (`DUNNING_ENGINE`). Razorpay fully removed — manual UPI primary.

## Events
`payment.received` · `subscription.activated` · `subscription.cancelled`.

## Metrics & alerts
`agent_events` · MRR/churn digest (`REVENUE_DIGEST`) · Vidya margin digest · reconciliation gap alert.

## Test matrix (E2E)
happy pay · idempotent re-verify · duplicate-trigger no-op · invoice numbering atomicity ·
IDOR rejection · GST on/off · refund/void · UPI claim. Coverage: `test_billing_truth_2026.py`,
`test_billing_auth_idor.py`, `test_payment_webhooks.py`.

## Runbook
[Billing Incident](../runbooks/RUNBOOK_BILLING_INCIDENT.md).
