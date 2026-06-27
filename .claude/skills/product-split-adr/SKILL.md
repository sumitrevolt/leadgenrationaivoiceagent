---
name: product-split-adr
description: Two-product split ADR-009 — Marketing vs Voice Agent separate SKUs, pricing truth, copy rules, niches, agents. Use for pricing, landing copy, features, or anything that touches both products.
---
# Product Split (ADR-009) — CURRENT truth

**DO alag products.** Bundle framing **GALAT**.

| | Product 1: Marketing | Product 2: Voice Agent |
|--|------------------------|----------------------|
| **Main page** | `/`, `/pricing` | `/voice-agent` |
| **Pricing source** | `app/marketing/packages.py` | `app/marketing/voice_packages.py` |
| **API** | `/api/marketing/packages` | `/api/voice/*` |
| **Niches** | `niches_for_product("marketing")` | `niches_for_product("voice")` + `lead_band` A/B/C |
| **Staff** | isha, dev, rohan, neha… | swara, ananya, riya, arjun, tara |
| **Voice in Marketing** | Advanced tier = **feature** (500 min) | — |

## Live prices (sync packages.py — change = test_billing_truth)

**Marketing (PUBLIC = 2 plans):** Main (`starter`) ₹1,999 · Combo/Advanced (`advanced`) ₹5,999/mo (annual = 10× monthly). Growth ₹2,999 (`growth`) = legacy hidden (`public:False`).

**Voice:** Flat monthly per band — A ₹4,999 · B ₹9,999 · C ₹19,999/mo · pilot free 7d/50 calls · **unlimited calls** (no lead-counting)

## Copy rules

- ❌ "Marketing + voice bundle USP"
- ❌ Per-lead voice pricing (removed)
- ✅ Advanced = "AI voice callback feature"
- ✅ Voice product = standalone telecaller SKU

## Code change checklist

1. Edit `packages.py` OR `voice_packages.py` (source of truth)
2. `tests/test_billing_truth_2026.py`
3. Landing `/pricing`, `/voice-agent`, JSON-LD
4. `subscription._sync_plans_from_packages`

Full ADR history: `docs/ADR_2026_06_11_Product_Split_Pricing.md` (pricing evolved — **packages.py wins**)
