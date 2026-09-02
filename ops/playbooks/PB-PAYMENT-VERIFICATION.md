# PB-PAYMENT-VERIFICATION — Payment Verification Playbook (P0)

- **Purpose**: Turn UPI proofs into VERIFIED REVENUE — the only revenue that counts.
- **Trigger**: UPI proof received / invoice raised / ledger row pending.
- **Scope**: invoice -> proof -> owner confirm -> ledger -> revenue truth update.
- **Prereqs**: invoice raised (Rule-46 sequential `INV/2026-27/xxxx`), UPI_VPA set.

## Strategy
1. Invoice raised on close intent (packages.py = pricing single source).
2. Customer sends UPI proof (bank ref / screenshot via WhatsApp/phone).
3. **OWNER confirms bank credit** — `payment_verification_method = owner_confirmed_upi`.
4. Ledger updated with invoice id + confirmation -> revenue truth reflects it.
5. PROVIDER_VERIFIED is UNREACHABLE BY DESIGN (Stripe/Razorpay removed) — never fake it.

## Decision tree
```
UPI proof
├─ bank credit CONFIRMED by owner -> ledger VERIFIED -> revenue truth update
├─ proof unclear / pending      -> owner follow-up (Hot Queue pack)
└─ no proof, invoice stale      -> dunning per nikhil (Revenue Ops) — owner-armed
```

## Allowed actions
- Raise/void invoices (append-only markers), reconcile ledgers, push owner reminders.

## Prohibited actions
- Marking revenue verified without owner confirmation.
- Treating proposals/verbal yes/unpaid invoice as revenue.

## Escalation
- Invoice unpaid >48h -> owner via revenue digest.

## KPIs
- Verified ₹/day; invoice-to-confirm cycle time; dunning recovery rate.

## Guardrails
- Ledger append-only; VOID markers not deletes; backups before reconciliation.

## Linked runbooks
RB-SALES-006 (payment not verified), RUNBOOK_BILLING_INCIDENT.

## Evidence requirements
- Ledger id + invoice id + owner_confirmation timestamp.

## Owner approval conditions
- Revenue truth update is OWNER-CONFIRMED ONLY (human gate = manual UPI confirm).
