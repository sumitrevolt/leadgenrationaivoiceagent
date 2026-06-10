---
name: saas-pricing-strategy
description: Pricing/packaging/discount decisions for LeadGen AI tiers (₹999 Starter / ₹2,499 Growth / ₹5,999 Advanced, annual 2-months-free, topup packs, ₹0 7-din trial). Use jab "pricing change", "naya plan", "discount doon?", "price badhao", "kitna charge karu", "annual offer", "topup", packaging ya tier-mix ki baat ho.
---

# SaaS Pricing Strategy (LeadGen AI)

**Single source of truth = `app/marketing/packages.py`** — landing, /pricing, checkout (`subscription.py _sync_plans_from_packages`), JSON-LD sab isi se. **IRON RULE: koi bhi price/tier change = packages.py + `tests/test_billing_truth_2026.py` SAATH me update** (yeh tests legacy ₹15k-plans bug dobara hone se rokte hain).

## Current truth (change se pehle yaad rakho)
- Starter ₹999/mo (marketing-only) · Growth ₹2,499 (recommended anchor) · Advanced ₹5,999 (+AI voice 500 min = UNIQUE tier).
- Annual `price_inr_year` = 2 mahine free (9990/24990/59990, one-time order — RBI e-mandate AFA se bachke). Topup `TOPUP_PACKS` 100/250/500 min. ₹0 trial 7-din (signup plan="trial"). GST sirf `GST_GSTIN` set pe.

## Decision frameworks (distilled)
1. **Value-based, cost-based nahi.** Price floor = next-best alternative, ceiling = perceived value. **Anchor: MyOperator/human telecaller ₹10k+/agent/mo** — Advanced ₹5,999 already "aadhe daam me AI staff" frame me bech do; pricing page pe yeh contrast dikhana = anchoring.
2. **India price-sensitivity**: SMB owner monthly cash-flow sochta hai. ₹999 entry = psychological "under ₹1000" — Starter ka left-digit mat todo. Mental accounting frame: "₹33/din — ek chai se kam me marketing staff".
3. **Value metric** = voice minutes (Advanced) + posts/features gating — usage ke saath value scale hoti hai ✓. Naya gate sochte waqt poochho: "zyada use = zyada value?" nahi to galat metric.
4. **Good-Better-Best discipline**: 3 tiers hi rakho (paradox of choice), Growth highlighted recommended, Advanced = 2.4x anchor. Naya tier add karne se pehle: kya existing tier me limit-gate se kaam chalega?
5. **Discounts**: 20-30% / 2-3 mahine max, time-bound, reason-bound (festival/save-offer). 50%+ KABHI nahi — customers cancel-for-deal seekh jaate hain. Rule of 100: ₹999 pe "% off" bolo, ₹5,999 pe "₹X bachao".
6. **Price increase kab**: prospects bina flinch ke haan bole / "itna sasta?!" feedback / churn <2% — tab grandfather-existing + new-price-new-customers.

## Pricing change checklist
`packages.py` edit → `test_billing_truth_2026.py` expected values update → `pytest tests/test_billing_truth_2026.py` green → pricing.html copy/anchor check (conversion-optimization skill) → prod_check → deploy. Landing + GST invoice (`gst_invoice.py`) auto-follow karte.

## Red flags
Hardcoded price kahin aur likhna ❌ (sirf packages.py) · 4th tier ❌ · trial ko 30-din karna ❌ (urgency khatam) · annual ko e-mandate recurring banana ❌ (RBI ₹15k AFA friction) · discount jo unit economics tode (Exotel ~₹0.75/call + LLM free = margin samajh ke do).

Adapted from coreyhaines31/marketingskills (via VoltAgent/awesome-agent-skills)
