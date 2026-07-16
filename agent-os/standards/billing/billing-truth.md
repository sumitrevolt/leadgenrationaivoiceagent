# Billing Truth

`app/marketing/packages.py` = SINGLE source of public pricing. Legacy `PRICING_PLANS` in `subscription.py` gets overridden at import via `_sync_plans_from_packages()` (defensive — packages import fail = legacy as-is, never raise).

- **Pricing change = `packages.py` + `test_billing_truth_2026.py` in the SAME change.** Contract test FIRST for any pricing/plan/public-API touch.
- Public surfaces use `get_public_packages()` — Growth ₹2,999 is LEGACY hidden.
- Voice plans have their own truth file (`voice_packages.py`), same sync pattern.
- Yearly discount = 1/6 (12mo × 5/6 = 10mo = "2 mahine free").
- Billing meters are fail-OPEN — never block the revenue path on infra error.

## Invoices (GST, Rule 46)

- Sequential per FY: `INV/2026-27/0001`, ≤16 chars, append-only `data/invoices.jsonl` + file lock.
- Charged price = GROSS (inclusive). GSTIN set → back-calculate taxable (gross/1.18); GSTIN unset → invoice without tax lines.
- Hook = `billing._provision_usage` (single choke-point for ALL gateways) → `on_payment_success()`, deduped by payment_ref/period (double webhooks safe).
- Email send gated `AUTO_INVOICE=1`; the record ALWAYS gets created.
- "Paid" evidence = owned invoice row, NOT a selected plan (ADR-095).
