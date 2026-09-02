# ADR-009: Two-Product Split — AI Automated Marketing vs AI Voice Calling Agent

**Status:** Accepted (user-approved 2026-06-11)
**Date:** 2026-06-11
**Deciders:** Sumit (founder)
**User decisions (elicited):** voice pricing = HYBRID (monthly tier quota + 10-lead top-up packs) · billable lead = AI-qualified "interested" · marketing tiers = research-driven new prices · scope = code-only (deploy alag se)

---

## Context

Platform ab tak ek hi pricing/niche/agent surface se dono offerings serve karti thi.
User-clarified positioning (2026-06-11): DO ALAG products —

1. **AI Automated Marketing** (MAIN) — Dhanda-jaisa marketing autopilot; Advanced tier me AI voice sirf EK FEATURE (inquiry callback, qualification, follow-ups).
2. **AI Voice Calling Agent** (STANDALONE) — full India-legal (TRAI/DLT) Hinglish AI telecaller.

Problems pehle:
- `niches.py` me PER-LEAD pricing (`pricing_inr.qualified_lead` ₹300–6000/lead ranges) — user ne bola **per-lead system sabhi jagah se hatao**, "per 10 leads, per niche" pricing chahiye.
- Voice product ka koi alag catalog/page/metering nahi tha (sirf marketing Advanced ka 500 min/mo).
- index.html me "Pay Per Lead" badges/FAQ — galat (purani) positioning.
- Agents (12 AI staff) + niches + handling sab shared the — products ke hisaab se split nahi.

## Decision

Same FastAPI monolith ke andar **logical product split** (microservice split NAHI — single VPS, free-stack, ek hi DB):

| Surface | Product 1: Marketing | Product 2: Voice Agent |
|---|---|---|
| Catalog | `app/marketing/packages.py` (as-is module, naye prices) | **NEW** `app/marketing/voice_packages.py` |
| Pricing unit | flat monthly tier (+ minute top-ups for Advanced FEATURE) | monthly tier with **qualified-lead quota** + **10-lead top-up packs**, niche-band priced |
| Niches | `category in (marketing, both)` | `category in (leadgen, both)` — helper `niches_for_product()` |
| Niche pricing field | none (tier-flat) | `lead_band: A/B/C` per niche (replaces `pricing_inr`) |
| Metering | feature caps + `usage.py` minutes (Advanced) | **NEW** `app/billing/lead_usage.py` qualified-lead quota |
| Agents (AI staff) | isha, dev, rohan, meera, guru | swara, tara, arjun |
| Shared/platform staff | boss, kavya, nikhil, vikram (dono products) | — |
| Public page | `/` + `/pricing` | **NEW** `/voice-agent` |
| API | `/api/marketing/packages` (unchanged shape) | **NEW** `/api/voice/*` router |
| Billing plan keys | `starter, growth, advanced` | `voice_starter_{a,b,c}, voice_growth_{a,b,c}, voice_pro_{a,b,c}` |

### Pricing — Product 1: AI Automated Marketing (research-driven, June 2026)

Anchors: Dhanda ₹7,999/yr (≈₹667/mo, features humse kam) · Predis Lite $32/mo ≈ ₹2,700 (sirf social content) · AdBanao budget poster app · Indian agency retainer ₹10k–25k/mo. Hum "agency-replacement at app price" band me:

| Tier | Monthly | Yearly (2 mahine FREE) | Notes |
|---|---|---|---|
| Trial | ₹0 / 7 din | — | unchanged |
| Starter | **₹1,199** | ₹11,990 | Dhanda se premium justified — full 15-feature list in `packages.py` (GBP+WhatsApp+approval+portal, sirf posters nahi) |
| Growth | **₹2,999** | ₹29,990 | Predis Lite (₹2,700, social-only) ke barabar me full stack |
| Advanced | **₹6,999** | ₹69,990 | voice FEATURE (500 min/mo) + uniqueness premium; agency retainer ka ~1/2–1/3 |

Full per-tier feature bullets live in **`app/marketing/packages.py`** (synced to `/api/marketing/packages`, `/pricing`, landing JSON-LD).

Minute top-up packs (Advanced feature ke liye) unchanged: 100/250/500 min = ₹1,499/3,499/5,999.
Repricing risk low: abhi 10 clients, pre-traction. Annual "2 mahine free" pattern retained.

### Pricing — Product 2: AI Voice Calling Agent (HYBRID, per-niche per-10-leads)

**Billable unit = AI-qualified "interested" lead** (`call_qualifier` verdict) — outcome-based.
Research: outcome pricing $3–25/qualified lead global; India AI call cost ₹2–6/min; human telecaller ₹55–85/resolved contact; humara COGS (free AI stack + Exotel ₹0.45–0.75/min) ≈ ₹30–50/qualified lead → 85%+ margin even Band A.

**Niche bands** (purane per-lead research midpoints se derive, niches.py me ab `lead_band`):
- **Band A** (mid <₹800): mass local services — gyms, salons, tuition, repairs…
- **Band B** (₹800–2,500): high-ticket — real estate, study abroad, solar, interiors…
- **Band C** (>₹2,500): premium/HNI — luxury real estate, wealth, fertility…

**Monthly tiers (quota included) + top-up pack, sab "per 10 qualified leads" units:**

| | Quota/mo | Band A | Band B | Band C |
|---|---|---|---|---|
| Voice Starter | 10 leads (1×10) | ₹3,999 | ₹9,999 | ₹24,999 |
| Voice Growth ⭐ | 30 leads (3×10) | ₹9,999 | ₹26,999 | ₹69,999 |
| Voice Pro | 60 leads (6×10) | ₹17,999 | ₹49,999 | ₹1,29,999 |
| Top-up (extra 10) | +10 leads | ₹4,499 | ₹11,999 | ₹29,999 |

- Effective/lead tier me: A ₹300–400 · B ₹900–1,000 · C ₹2,200–2,500 — purane research ranges ke andar, top-up rate tier-rate se UPAR (upsell lever, minute-topup pattern jaisa). Quota + top-up leads period-end pe EXPIRE.
- Fair-use minute cap per tier (qua quota ke saath): Starter 600 · Growth 1,800 · Pro 3,600 min/mo (abuse-guard, page pe "fair use" footnote).
- DLT-gated cold-calling tak: consented/inbound/own-database calling hi (TRAI-safe, AI disclosure built-in).

**PER-LEAD system REMOVED everywhere:** `pricing_inr` (qualified_lead/appointment/monthly_starter) deleted from niches.py; index.html "Pay Per Lead"/"Per-Lead Pricing"/FAQ ₹200–500/lead copy replaced; legacy `PAY_AS_YOU_GO` PER_LEAD billing plan removed.

## Options Considered

### Option A: Logical split in monolith (CHOSEN)
Complexity Low · Cost ₹0 · ek hi deploy/DB/auth · saare existing engines reuse.
**Cons:** product boundary discipline convention pe depend karta hai (modules + plan-key namespacing).

### Option B: Alag service/repo for voice product
**Pros:** hard isolation. **Cons:** single founder + single VPS pe ops×2, shared KB/telephony/auth duplicate — reject (premature).

### Option C: Pure per-lead marketplace pricing (purana)
**Cons:** unpredictable billing, COGS attribution per lead, user ne explicitly hataya — reject.

## Consequences

**Easier:** clear positioning (no bundle confusion), voice MRR independent, niche-appropriate value capture (Band C 8x Band A), outcome-aligned pricing = sales pitch ("sirf qualified leads ke paise").
**Harder:** qualified-lead disputes possible → transcripts dashboard me evidence; lead quota metering ka naya store; 9 voice plan keys checkout me.
**Revisit later:** band assignments per niche (data aane pe), appointment-booked premium add-on, DLT unlock pe cold-outreach tiers, voice annual plans.

## Action Items (is batch me implemented)
1. [x] `voice_packages.py` — tiers×bands + lead packs + helpers
2. [x] `packages.py` — naye marketing prices + copy
3. [x] `niches.py` — `pricing_inr` → `lead_band` + `products` helpers
4. [x] `lead_usage.py` — qualified-lead quota metering (+ qualifier hook)
5. [x] `subscription.py` — voice plans sync, PER_LEAD legacy plan removed
6. [x] `team.py` — staff `product` field + rosters per product
7. [x] `/api/voice/*` router + `/voice-agent` page
8. [x] index.html/pricing.html copy — per-lead hatao, 2-product framing
9. [x] tests: billing-truth updated + test_product_split.py
