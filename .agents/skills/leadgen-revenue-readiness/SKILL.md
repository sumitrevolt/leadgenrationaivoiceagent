---
name: leadgen-revenue-readiness
description: P1 AI Marketing Automation ko SELLABLE banane ka audit — kya customer discover→pay→activate→output tak pahunch sakta hai. Use jab "launch ready hai?", "kya bech sakte", "revenue blocker", "kaunsa feature fake/adhoora", ya kaam ko business-impact se rank karna ho. P1 north-star; P2 voice ko sirf readiness/compliance ke liye audit karo, launch-blocker mat banao.
---

# LeadGen Revenue Readiness (P1 sellable gate)

> Enterprise audit skill. **P1 = AI Marketing Automation = MAIN product** (Dhanda-jaisa). P2 = AI Voice Calling Agent = ALAG product, DLT-gated → readiness audit karo par P1 launch ko block mat karne do. Pehle `context-first` se repo padho, phir yeh.

## Mission
Feature "revenue-ready" tabhi hai jab customer use **discover** kare, **pay** kare, **activate** ho, aur **useful output** paaye. Platform expand karne se pehle yeh chain band karo.

## The paid path (yeh exact map verify karo)
`/` landing → `/pricing` (public 2 plans only) → `/start` signup → **manual UPI** instructions (`/api/public/pay-info`) → admin approval (`POST /api/admin/upi/configure` / approve) → onboarding (`AUTO_ONBOARD=1`, website→KB seed + first content pack) → `/app/customer` portal login → `auto_content.py` marketing output → CRM/cadence follow-up.

Har step ko mark karo: `working` · `broken` · `incomplete` · `mock` · `external blocker`.

## Repo source-of-truth (yahi check karo, guess mat)
- **Single readiness signal**: `GET /api/activation/readiness` → 13 probes → single boolean `ready_for_first_paid_customer` (F.2). Yeh pehle chalao — yeh tumhara baseline scorecard hai.
- **Pricing truth**: `app/marketing/packages.py` → public sirf 2 (`starter` ₹1,999 + `advanced` ₹5,999); `growth` LEGACY hidden (`public:False`). `get_public_packages()` use karo, `get_packages()` nahi.
- **Payment**: Razorpay REMOVED (2026-06-18) → UPI primary, ARMED (`app/platform/upi_config.py`, `/api/public/pay-info` `enabled:true`). Stripe = international only.
- **Voice (P2)**: `voice_packages.py` band A/B/C ₹4,999/9,999/19,999 — separate page `/voice-agent`, DLT/DID external-blocked.

## Enterprise checks
- P1 aur P2 public copy, routes, packages, flags, admin flows me clearly SEPARATE. "Marketing+voice bundle USP" framing = GALAT.
- Har visible paid feature ka real backend path ho ya feature-flag ke peeche chhupa ho (mock customer ko na dikhe).
- Manual UPI activation admin bina code-edit complete kar sake (no-restart `POST /api/admin/upi/configure`).
- Demo/seed data real customer se labeled ya hidden.
- Activation ke baad customer ko kam-se-kam EK useful marketing output mile.

## Output (standard enterprise format)
1. Scope checked · 2. Evidence (file:func/route) · 3. Top 10 revenue blockers by impact×confidence×effort · 4. Must-fix / should-fix / later · 5. Safe additive fix order · 6. Tests to add (`test_billing_truth_2026.py` + activation probes) · 7. Rollback · 8. **P1 sellable readiness /100**.

## Related repo skills (duplicate mat banao)
- `production-ready` — launch/GO certification (yeh skill = revenue-lens uska complement).
- `product-split-adr` — P1/P2 split truth. · `revops` — revenue automation loops. · `leadgen-billing-upi` — payment activation depth. · `leadgen-customer-journey-e2e` — actual click-through test.
