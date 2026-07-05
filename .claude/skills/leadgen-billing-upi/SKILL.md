---
name: leadgen-billing-upi
description: Manual UPI billing/approval/invoice/plan-activation/entitlement ko operationally safe banao (jab tak full gateway na ho). Use jab payment manual ho, UPI ke baad customer activate karna ho, plan→portal-access sync karna ho, ya invoice/GST artifacts consistent karne ho.
---

# LeadGen Billing UPI (manual payment hardening)

> Enterprise audit skill. Razorpay REMOVED (2026-06-18) → koi online India gateway nahi → **manual UPI = PRIMARY path**. Pehle `context-first`.

## Mission
Manual UPI billing ko safe rakho jab tak full gateway integrate na ho. Entitlement server-side, approval audited, invalid plan activate na ho.

## Repo truth
- **UPI config**: `app/platform/upi_config.py` — env → settings → data-file fallback. Admin no-restart set: `POST /api/admin/upi/configure`. Public: `GET /api/public/pay-info` (`enabled:true`).
- **Plan source**: `app/marketing/packages.py` (marketing) + `app/marketing/voice_packages.py` (voice bands) — dono canonical (2026-07-05). Approval sirf VALID public plan activate kare; retired/legacy (`growth public:False`) nahi.
- **Entitlement**: har billing mutation pe `_authed_client_id` dep (C1 IDOR closed). Server-side check, client-trust nahi.
- **Invoice**: Rule-46 sequential `INV/2026-27/0001` (atomic numbering, H7), SAC 998313, GST sirf `GST_GSTIN` set pe.
- **Stripe** = international only; unconfigured India checkout → clean 503 → UPI fallback.

## Workflow
1. Plan source, UPI VPA/QR config, approval UI, invoice gen, entitlement checks dhoondo.
2. Payment-proof / admin-note flow verify.
3. Admin approval EXACTLY purchased plan+duration activate kare confirm.
4. Failed/rejected payment access BLOCKED rakhe + useful customer state.
5. Audit log: kaun ne kya, kab, kyun approve kiya.

## Enterprise checks
- UPI VPA/QR config se aaye, template me hardcode nahi.
- Admin approval invalid/retired plan activate na kar sake.
- Entitlements server-side.
- Invoice business-name/tax/amount/plan-period consistent.
- Expiry/renewal/cancel/refund-note represented (dunning `DUNNING_ENGINE`).

## Output
Billing flow map · entitlement risks+fixes · invoice/approval test cases · payment-activation readiness /100.

## Related repo skills (duplicate mat banao)
`pricing` (plan strategy) · `revops` (dunning/lifecycle) · `leadgen-product-truth` (plan canonical) · `leadgen-security-rbac` (entitlement/IDOR) · `leadgen-test-guardian` (`test_billing_truth_2026.py`).
