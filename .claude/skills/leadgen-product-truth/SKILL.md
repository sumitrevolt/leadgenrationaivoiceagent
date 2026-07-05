---
name: leadgen-product-truth
description: Plans/limits/products/promises ka EK source-of-truth enforce karo. Use jab pricing, packages, feature-gate, public claims, route naming, plan limits, billing-sync check karna ho, ya duplicate product/workflow/conflicting customer-promise rokna ho. P1 = Marketing Automation, P2 = Voice (compliance-gated).
---

# LeadGen Product Truth (single source-of-truth guard)

> Enterprise audit skill. Pehle `context-first` se saare pricing/product touch-points Grep karo, phir yeh. FastAPI **first-route-wins** → duplicate-route shadow ka khaas dhyaan.

## Mission
Plans, limits, products, customer-promises ka EK canonical source rakho. Value ko aur jagah COPY karke "fix" mat karo — canonical se READ karwao.

## Workflow
1. Saare product/pricing sources dhoondo: backend constants, templates, frontend config, DB seed, tests, docs, admin pages.
2. Canonical identify karo — yahan = **`app/marketing/packages.py`** (`subscription._sync_plans_from_packages`). Voice = `app/marketing/voice_packages.py` (2026-07-05) (`subscription._sync_voice_plans`, 7 ids).
3. Public pages · backend validation · billing activation · customer portal · admin UI — sab compare.
4. Mismatch / stale plan / hidden legacy / unguarded P2 feature flag karo.
5. Canonical se read karke fix; naya source mat banao.

## Repo truth (CLAUDE.md verified 2026-06-27)
- **Marketing public**: sirf 2 → `starter` ₹1,999 + `advanced` ₹5,999 (voice FEATURE 500 min). Yearly 19990/59990. `growth` ₹2,999 = LEGACY `public:False` — public pricing me KABHI nahi. **`get_public_packages()`** mandatory.
- **Voice**: flat monthly per band — A ₹4,999 · B ₹9,999 · C ₹19,999 (UNLIMITED calls, no per-lead). Pilot ₹0 7din/50calls. Niche→band = `app/niches.py` `lead_band`.
- **GST**: sirf `GST_GSTIN` set pe charge (unregistered = no tax). Invoice Rule-46 sequential `INV/2026-27/0001`, SAC 998313.
- **DO products framing**: (1) Marketing = MAIN, voice uska EK advanced feature; (2) Voice = standalone DLT-gated. "Bundle USP" = banned framing.

## Enterprise checks
- Plan name/price/limit/feature/add-on/currency HAR jagah match.
- Public pricing me disabled/experimental/legacy plan na dikhe.
- P1/P2 ke separate flags, routes, dashboards, activation gates.
- Voice feature DLT/DND/consent/calling-window/opt-out bypass na kar sake.
- Pricing/feature truth diverge ho to test FAIL ho (`test_billing_truth_2026.py`).

## Output
Product-truth map · conflicting files/routes · canonicalization plan · pricing-lock tests · readiness /100.

## Related repo skills (duplicate mat banao)
`product-split-adr` (P1/P2 ADR) · `pricing` + `saas-pricing-strategy` (pricing strategy) · `duplicate-route-guard` (FastAPI first-route-wins) · `leadgen-billing-upi` (payment/entitlement) · `leadgen-test-guardian` (truth-lock tests).
