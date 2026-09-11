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

## Enterprise gate

Operating loop chalao — Discover → Contract → Execute → Self-review → Evidence (full loop `fable-operating-manual`).

**Change-risk tier: High-risk always** (billing/pricing). Yeh skill jo bhi chhuता hai woh paisa locks: `app/marketing/packages.py` + `app/marketing/voice_packages.py` = **single source of truth**. Number kabhi duplicate mat likho (landing/JSON-LD se hardcode nahi — source se render). Public pricing me KABHI `growth` (`public:False`) mat dikhao → `get_public_packages()` use karo, `get_packages()` nahi.

- **Billing-truth (fail-CLOSED):** har price/plan/SKU change = `packages.py`/`voice_packages.py` + `tests/test_billing_truth_2026.py` SAATH green. Plan-id drift mat karo — `subscription._sync_plans_from_packages` (marketing) + `_sync_voice_plans` (7 ids: `voice_{a,b,c}_{monthly,annual}` + `voice_pilot`) mirror rakho.
- **Compliance:** GST sirf `GST_GSTIN` set pe charge (unregistered = no tax); invoice Rule-46 sequential `INV/2026-27/0001`, SAC 998313 — yeh logic touch mat karo bina test. Auth/IDOR: koi bhi billing mutation `_authed_client_id` dep ke peeche (cross-tenant price/plan change block).
- **Safety:** voice band-pricing `lead_band` A/B/C se aati (`app/niches.py`) — niche band badla to voice bill badal jata, dono saath verify. Tenant boundary: per-client custom pricing global packages override na kare bina explicit grant.
- **Observability/Rollback (NAMED):** pricing change deploy = container recreate (stale .pyc warna purani price serve) → `/api/marketing/packages` + `/api/voice/packages` live verify. Galat price live → packages.py git-revert + recreate (fast, no migration).

**Evidence (done):** `pytest tests\test_billing_truth_2026.py -q` green (non-negotiable) + `.venv\Scripts\python.exe scripts\prod_check.py` + deploy ke baad `curl.exe -fsS https://leadsgenai.in/api/marketing/packages` me sirf 2 public plans (Main+Advanced, growth chhupa) + `/api/voice/packages` me 3 bands. Bina billing-truth green pricing done KABHI mat bolo.
