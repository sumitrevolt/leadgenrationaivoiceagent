---
name: saas-pricing-strategy
description: Pricing/packaging/discount decisions for LeadGen AI ke DO products — Marketing (PUBLIC 2 plans — Main ₹1,999 / Combo-Advanced ₹5,999; Growth ₹2,999 legacy-hidden; annual 2-mahine-free, top-ups, ₹0 7-din trial) aur Voice Agent (flat-monthly band A/B/C ₹4,999/9,999/19,999, free pilot). Use jab "pricing change", "naya plan", "discount doon?", "price badhao", "kitna charge karu", "annual offer", "topup", "voice pricing", packaging ya tier-mix ki baat ho.
---

# SaaS Pricing Strategy (LeadGen AI — 2 products)

**DO alag products, DO source-of-truth files** (`packages.py` = single source for marketing; `subscription.py` inhi se plans sync karta — landing, /pricing, /voice-agent, checkout, JSON-LD sab yahin se):
- **Product 1 — AI Automated Marketing** (MAIN): `app/marketing/packages.py` (`subscription._sync_plans_from_packages`).
- **Product 2 — AI Voice Calling Agent** (ALAG standalone, DLT-gated): `app/marketing/voice_packages.py` (`subscription._sync_voice_plans`).

**IRON RULE: koi bhi price/tier change = source file + `tests/test_billing_truth_2026.py` SAATH me update** (yeh tests legacy plan-drift bug dobara hone se rokte hain). **"Marketing + voice bundle / dono ek saath" framing GALAT — alag bech.**

## Current truth (change se pehle yaad rakho)
**Marketing** (`packages.py`): PUBLIC = 2 plans — **Main** (Marketing Automation, `starter`) ₹1,999/mo + **Combo/Advanced** (`advanced`, +AI voice 500 min/mo = ek FEATURE, India me UNIQUE) ₹5,999. Annual = 10× monthly = 2 mahine free (19990 / 59990). **Growth ₹2,999 (`growth`) = legacy hidden (`public:False`, public me NAHI — `get_public_packages()` use karo).** `TOPUP_PACKS` 100/250/500 min = ₹1,499/3,499/5,999 (period-end EXPIRE). FREE trial ₹0, `TRIAL_DAYS=7` (no card, no voice). GST sirf `GST_GSTIN` set pe.
**Voice** (`voice_packages.py`): FLAT MONTHLY per niche-band — Band A ₹4,999 · Band B ₹9,999 · Band C ₹19,999 (UNLIMITED calls, no lead-counting/disputes). Annual = 10× monthly (49990/99990/1,99,990). FREE pilot 7 din / 50 calls (`voice_pilot`, zero payment). Niche→band = `app/niches.py` `lead_band`. Plan IDs `voice_{a,b,c}_monthly`/`_annual` + `voice_pilot`.

## Decision frameworks (distilled)
1. **Value-based, cost-based nahi.** Floor = next-best alternative, ceiling = perceived value. Anchors: marketing → Dhanda ₹7,999/yr, Predis Lite ~₹2,700/mo · voice → human telecaller ₹10k+/agent/mo. Advanced/voice ko "aadhe daam me AI staff" frame me bech do — pricing page pe yeh contrast = anchoring.
2. **India price-sensitivity**: SMB owner monthly cash-flow sochta hai. ₹1,999 (Main) entry = mental accounting frame "₹66/din — ek chai-samose se kam me marketing staff". Starter left-digit pe khelo.
3. **Value metric** = marketing me posts/features gating + voice minutes (Advanced); voice product me niche-band (premium niche = premium price). Naya gate sochte waqt: "zyada use = zyada value?" nahi to galat metric.
4. **Good-Better-Best discipline**: marketing public = 2 tiers (Main + Combo/Advanced; Growth legacy-hidden), voice 3 cards (pilot + monthly + annual). Combo/Advanced (+ voice-monthly) highlighted recommended. Naya tier add karne se pehle: existing tier me limit-gate se kaam chalega?
5. **Discounts**: 20-30% / 2-3 mahine max, time-bound, reason-bound (festival/save-offer). 50%+ KABHI nahi — customers cancel-for-deal seekh jaate. Rule of 100: ₹1,999 pe "% off" bolo, ₹5,999/₹19,999 pe "₹X bachao".
6. **Voice flat-model ka USP**: "koi lead-counting nahi, koi surprise invoice nahi" — yeh trust-anchor hai, dispute-free billing bech.
7. **Price increase kab**: prospects bina flinch ke haan bole / "itna sasta?!" feedback / churn <2% — tab grandfather-existing + new-price-new-customers.

## Pricing change checklist
Source file edit (`packages.py` ya `voice_packages.py`) → `test_billing_truth_2026.py` expected values update → `pytest tests/test_billing_truth_2026.py` green → pricing.html / voice-agent copy/anchor check (conversion-optimization skill) → prod_check → deploy. Landing + GST invoice auto-follow karte (`subscription._sync_*` startup pe sync).

## Red flags
Hardcoded price kahin aur likhna ❌ (sirf source files) · marketing me 4th tier ❌ · trial ko 30-din karna ❌ (urgency khatam) · voice ko per-lead/quota model wapas lana ❌ (flat-monthly = dispute-free, jaan-bujh ke chhoda) · annual ko e-mandate recurring banana ❌ (RBI AFA friction — one-time order rakho) · discount jo unit economics tode (Vobiz ~₹0.45/call + LLM free = margin samajh ke do).

Adapted from coreyhaines31/marketingskills (via VoltAgent/awesome-agent-skills)
