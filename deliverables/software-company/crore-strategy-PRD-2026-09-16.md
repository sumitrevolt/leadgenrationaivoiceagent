# PRD — ₹1,00,00,000/month Integrated Revenue Strategy
### LeadGen AI · Product Requirement Document · Stage 1 (Product)

> **Author:** 许清楚 (Alice / Xu) — Product Manager
> **Date:** 2026-09-16
> **Handoff to:** Architect (Stage 2) → Engineering (Stage 3) → QA (Stage 4)
> **Repo:** `C:\Users\Ratanshila\Documents\leadgenrationaivoiceagent`
> **Authority chain:** `7_DAY_REVENUE_PLAN.md` (revenue SSOT) → this PRD (product decisions) → ADR/architecture docs.
> **Evidence labels:** `PRODUCTION-PROVEN` · `CODE-PRESENT` · `TEST-PROVEN` · `LOCAL-ONLY` · `PARTIAL` · `STALE` · `UNKNOWN`
> **Rule (inherited from the blueprint):** a claim with no label is a claim nobody may act on.

---

## 0. TL;DR — Seedha jawab: ₹1 Cr/month reachable hai ya nahi?

- **Aaj ki honest position:** ₹1 Cr/month **current rails pe reachable NAHI hai.** Verified baseline **₹5,997 collected FY 2026-27**, 3 real invoices, 13 voided synthetic, Aug 24 ke baad koi naya invoice nahi (`PRODUCTION-PROVEN`). ₹1 Cr/month = aaj ke collected revenue ka **~16,680×** (`5,997 → 1,00,00,000`).
- **Kyun nahi:** sirf **2 owner gates** revenue rok rahe hain (Smartflo DID→VOICE destination `null`; manual UPI + bank-credit confirm). Code GO hai; paisa human-gated hai (`PRODUCTION-PROVEN`). Aur channels cap out hote hain — outbound **~875 contacts/week** (`CODE-PRESENT`).
- **Rails ka hard ceiling:** manual UPI + owner bank-confirm ek din me realistically **~10–25 naye customers** process kar sakta hai. Us rate pe **max ~₹25k–₹10L/month** — ₹1 Cr nahi.
- **Automation honesty:** "31 agents defined 31/31 ✅ · armed partial 🟡 · **proven-executing ❌ NO**" — `dev_workers` = **0 rows**, `_IDEMPOTENCY` process-local (`CODE-PRESENT`). Ye ₹1 Cr ka *engine* nahi hai — ye **starting-line gap** hai.
- **Verdict — 3 horizons:**
  - **2–4 mahine:** ₹50,000–₹5,00,000/month **reachable**, dono gates khulne pe.
  - **6–12 mahine:** ₹5L–₹25L/month **stretch-reachable** agar DLT + paid-rail decision + human telecaller capacity aaye.
  - **₹1 Cr/month:** **12–24 mahine ka programme**, do conditions pe — (a) DLT registration complete + cold outbound legal, (b) ek **verified payment rail** (ya owner-run collections desk) jo daily 300+ payments handle kare. In dono ke bina ₹1 Cr sirf ek number hai, plan nahi.
- **Primary engine:** **AI Automated Marketing** (ARPU up + volume) = ₹1 Cr ka ~60–65%. **AI Voice Calling Agent** = ~35–40%, **DLT-gated**.
- **Highest-leverage lever:** **volume** (customer count), **NA ki** ARPU. ₹1 Cr ke liye 1,999-ARPU pe **~5,000 customers** chahiye; 9,999-ARPU pe bhi **~1,000**. ARPU sirf 3–5× badh sakta hai; volume ko 100×+ karna padega — isliye **funnel + rails capacity** asli problem hai.

---

## 1. Evidence baseline — jo verified hai, wahi seedha line

### 1a. Money truth (`PRODUCTION-PROVEN`)

| Metric | Verified value | Label | Source |
|---|---|---|---|
| Collected, FY 2026-27 | **₹5,997** | `PRODUCTION-PROVEN` | `data/invoices.jsonl` via `app.billing.gst_invoice.stats()` |
| Invoices | 16 total · **13 voided (synthetic)** · 3 real | `PRODUCTION-PROVEN` | same |
| Last new invoice | **Aug 24** | `PRODUCTION-PROVEN` | ledger mtime |
| Paying customers | **1** — `jiya-makeover` (MRR ₹1,999) | `PRODUCTION-PROVEN` | `CURRENT_STATE.md` |
| `data/revenue_attribution.jsonl` | **NOT money** — 27 rows, `amount_inr`=0 except 2 test rows | `CODE-PRESENT` | blueprint §1 |
| Current MRR / active subs | **UNKNOWN** — is session re-verify nahi hua | `UNKNOWN` | — |
| Payment rail | **Manual UPI ONLY** — Stripe + Razorpay **REMOVED** (issue #243 `not_planned`) | `PRODUCTION-PROVEN` | blueprint §3 |
| Verification method | `owner_confirmed_upi` — `PROVIDER_VERIFIED` **unreachable BY DESIGN** | `PRODUCTION-PROVEN` | same |

> **Verify karne ka tareeka (VPS-only, ledger local tree me nahi hai):**
> `docker exec leadgen_app python -c "from app.billing import gst_invoice as g; print(g.stats())"`

### 1b. Product truth (`CODE-PRESENT`)

| Product | Files | Public pricing | Status |
|---|---|---|---|
| **AI Automated Marketing** (MAIN) | `app/marketing/packages.py` | ₹1,999/mo · ₹19,990/yr | Revenue engine #1 |
| Marketing "Advanced" (callback feature) | `app/marketing/packages.py` (`advanced`) | ₹5,999/mo · ₹59,990/yr + 500 voice min | Upsell tier |
| Growth (legacy, hidden) | `app/marketing/packages.py` (`growth`, `public:False`) | ₹2,999/mo | **Do NOT surface** |
| **AI Voice Calling Agent** (standalone) | `app/marketing/voice_packages.py` | ₹4,999 / ₹9,999 / ₹19,999 per niche-band/mo | **DLT-gated** for cold outbound |
| Voice Starter / Freemium / Pilot | `voice_packages.py` | ₹1,999/mo · ₹0 · ₹0 (7d/50 calls) | Funnel entry |
| Combos (marketing almost free) | `app/marketing/combo_packages.py` | ₹4,999 / ₹9,999 / ₹21,999 | Anchor pricing |
| Voice top-up packs | `packages.py` (`TOPUP_PACKS`) | 100min ₹1,499 · 250min ₹3,499 · 500min ₹5,999 | Expire at period-end |

### 1c. Automation truth — NEVER "31 agents running" (`CODE-PRESENT`)

| Question | Verdict | Evidence |
|---|---|---|
| Defined? | ✅ **31/31** | `app/platform/team.py` → `STAFF` = 31 keys |
| Armed? | 🟡 **partial** | 12 dispatchable / 19 non-dispatchable |
| **Proven-executing?** | ❌ **NO** | `dev_workers` = **0 rows**; `service._IDEMPOTENCY` = process-local dict |
| 9 Hermes bots | ✅ defined | `AutomationOrchestrator.HERMES_BOTS`: board, pilot, guardian, engineering, platform, sales, hunter, operations, success |
| Kill switch | ✅ code-present | `is_kill_switch_active()` → `AUTOMATION_STOP_NEW_CLAIMS` |
| DLQ / retry | ✅ code-present | `retry_count` / `max_retries` / `dlq_count`; `recover_stale_running_tasks()` |

> **`HERMES_AGENT_ROSTER.yaml` self-declares SUPERSEDED** (8-bot old view). Canonical = **9 bots → 31 agents** per `docs/architecture/24X7_FINAL_DECISION_2026-09-12.md`. Architect ko 9-bot map use karna hai, YAML ka 8-bot map nahi.

### 1d. Deployment truth (`PRODUCTION-PROVEN`)

- Prod app = **systemd unit `leadgen`** → `127.0.0.1:8000`, `uvicorn app.main:app --workers 2`.
- **NO `leadgen_app` container exists.** `docker compose up -d ... app` = **guaranteed false success**.
- Single deploy authority = `scripts/deploy_vps.sh`. Single VPS = Hostinger Mumbai, `root@72.61.245.204`. PM2 **NOT** used.
- AI stack = **free-tier providers only** (owner mandate). No paid STT/TTS/LLM.

### 1e. Compliance spine — NEVER loosen (`PRODUCTION-PROVEN`)

| Invariant | Rule |
|---|---|
| TRAI DND | Voice window **9am–7pm IST**; DND lookup fail ⇒ **BLOCK** (fail-CLOSED) |
| Consent ledger | Har contact ka consent record; no consent ⇒ no send/call |
| DPDP 2023 | Lawful purpose + data minimisation |
| Opt-out suppression | Unreadable store ⇒ **everyone suppressed** (fail-CLOSED) |
| Cold WhatsApp | **OFF by design** |
| `DND_FAIL_OPEN` | **Refused in production** |

> **Risk flag (P0, do NOT fail-close blindly):** `SMARTFLO_WEBHOOK_SECRET` currently **unset** ⇒ webhook auth disabled. Ye ek security gap hai — Architect/Eng ko fix karna hai **bina** inbound calls todne ke.

---

## 2. Product definition

### 2a. Product goals (3, orthogonal)

1. **Revenue unblock karo** — dono owner gates ke baad, ek **repeatable, measurable** funnel banao jo weekly ₹ collected revenue produce kare (target: week 4 pe ≥ ₹50k/week).
2. **Product-market fit ko productized karo** — Marketing product ko **₹1 Cr ka primary engine** banao (volume + retention), Voice ko **DLT-gated premium add-on**.
3. **Execution proof real banao** — `dev_workers` instrumentation + DB-backed idempotency, taaki "agents are working" ek **measured fact** ho, claim nahi.

### 2b. Revenue contribution split (₹1 Cr/month target state)

| Product | Share of ₹1 Cr | ₹ value | Rationale |
|---|---|---|---|
| AI Automated Marketing (incl. Advanced) | **62%** | ₹62,00,000 | Non-DLT-gated, wider SMB TAM, low ARPU-high volume |
| AI Voice Calling Agent (standalone bands A/B/C) | **33%** | ₹33,00,000 | DLT-gated ⇒ segment-limited, high ARPU |
| Top-ups + annual prepay uplift | **5%** | ₹5,00,000 | Margin lever, usage-driven |

**Primary engine of ₹1 Cr = AI Automated Marketing.** Kyun: Voice product cold-outbound **DLT-gated** hai (`voice_packages.py` compliance_note: *"Cold outbound DLT approval ke baad; tab tak inbound / consented / own-database calling"* — `CODE-PRESENT`). Marketing ko is gate ki zaroorat nahi. Isliye volume yahin se aayega.

### 2c. User stories

**Owner (operator) — sole human:**
- As the owner, I want **one screen** that shows aaj ka collected ₹, pending UPI payments, aur gate status, so that I can run the business in 30 min/day.
- As the owner, I want each payment to need **exactly one** bank-credit confirmation, so that collections scale without hiring a finance person.
- As the owner, I want the bot fleet to **escalate only actionable items**, so that my 30 min is spent on money, not noise.

**Customer (SMB owner, Hinglish):**
- As a salon/hospital/clinic owner, I want **aaj ke ready social posts + review replies**, so that I look active online without hiring an agency.
- As a customer, I want to pay via **UPI QR** and get a **GST invoice**, so that billing is clean.
- As a customer, I want a **7-day free trial** (no card), so that I can try before paying.

**Bot / agent fleet:**
- As **Rohan (Leads Manager)**, I want a deduped, scored lead list, so that outreach hits the right SMB.
- As **Swara (Telecaller)**, I want consent + DND-checked call lists within the 9am–7pm window, so that I never violate TCCCPR.
- As **Nikhil (Revenue Ops)**, I want dunning + churn-risk signals, so that MRR leaks get plugged.
- As **Lekha (Call Analytics)**, I want per-call KPIs (qualified-rate, booking-rate), so that script tuning is data-driven.
- As **Guardian (bot)**, I want to **reject** any task that weakens a compliance gate, so that revenue never costs us the licence to operate.

---

## 3. Target audience segmentation

### 3a. Marketing product segments (non-DLT-gated)

| Segment | Niche examples | City tier | Est. ARPU | Product fit | Priority |
|---|---|---|---|---|---|
| **Local services — salon/spa/gym** | beauty, fitness | Tier 1–2 | ₹1,999 | Starter — posts, reviews, booking | **P0** (jiya-makeover already proving) |
| **Clinics & diagnostics** | dental, derma, physio | Tier 1–2 | ₹1,999–₹5,999 | Starter→Advanced | **P0** |
| **Restaurants & cloud kitchens** | cafe, bakery | Tier 1–3 | ₹1,999 | Starter — festivals, offers | **P1** |
| **Coaching & tuition** | upskilling, test-prep | Tier 1–3 | ₹2,999–₹5,999 | Advanced (callback for enquiries) | **P1** |
| **Real estate & interiors** | modular kitchen | Tier 1 | ₹5,999 | Advanced | **P1** |
| **Retail & boutiques** | clothing, jewellery | Tier 2–3 | ₹1,999 | Starter | **P2** |

### 3b. Voice product segments — **DLT-gated, alag bucket**

> Ye segments sirf **inbound / consented / own-database** calling ke liye valid hain jab tak DLT registration complete na ho.

| Band | Niches (`niches.py: lead_band`) | Price/mo | Validity |
|---|---|---|---|
| Band A | Insurance, coaching, solar, hospital, upskilling, travel | ₹4,999 | Own-DB + inbound OK; cold **DLT-gated** |
| Band B | Home loans, study abroad, dental, finance advisory, CA | ₹9,999 | same |
| Band C | IVF, immigration, commercial solar, HVAC, hair transplant | ₹19,999 | same |
| Voice Starter | Any niche, 100 min | ₹1,999 | Funnel entry |
| Pilot | Any niche, 7d/50 calls | ₹0 | Lead magnet |

**Voice segment strategy:** sirf **own-database + inbound + consented** calling promote karo (DID `+918069879757` inbound bhi gate-blocked hai — §6 Gate 1). Cold outbound = **roadmap item, DLT approval ke baad**.

---

## 4. Pricing strategy (grounded in `packages.py` / `voice_packages.py`)

### 4a. Current price ladder (`CODE-PRESENT`)

| Plan | Monthly | Annual (10× = 2 mo free) | Notes |
|---|---|---|---|
| Free Trial | ₹0 | — | 7 din, marketing-lite |
| Marketing Starter | ₹1,999 | ₹19,990 | **POPULAR**, revenue engine |
| Voice Freemium | ₹0 | — | 10 calls/mo forever (viral) |
| Voice Pilot | ₹0 | — | 7d / 50 calls |
| Voice Starter | ₹1,999 | ₹19,990 | 100 min |
| Marketing Advanced | ₹5,999 | ₹59,990 | + 500 callback min |
| Combo Starter | ₹4,999 | ₹49,990 | marketing almost free anchor |
| Voice Band A | ₹4,999 | ₹49,990 | unlimited calls |
| Combo Growth | ₹9,999 | ₹99,990 | — |
| Voice Band B | ₹9,999 | ₹99,990 | — |
| Voice Band C | ₹19,999 | ₹1,99,990 | premium/HNI |
| Combo Pro | ₹21,999 | ₹2,19,990 | — |
| Top-up 100/250/500 min | ₹1,499 / ₹3,499 / ₹5,999 | — | Expire at period-end |

### 4b. Highest-leverage lever: **ARPU up vs volume up**

₹1 Cr/month decomposition:

| Path | ARPU | Customers needed | Feasibility |
|---|---|---|---|
| Pure Starter | ₹1,999 | **5,006** | Volume 100×+ — needs rails capacity |
| Pure Band B | ₹9,999 | **1,001** | ARPU 5× — still 1,000 customers |
| **Recommended mixed** | **₹2,990 blended** | **~3,345** | Combos + Advanced lift blend |

**Conclusion:** ARPU sirf **3–5×** badh sakta hai (price ceiling = SMB budget). Volume ko **100×+** karna padega. **Lever = volume (customer count), supported by ARPU-mix.** Isliye P0 = funnel + rails capacity.

**Annual/prepay (cash-flow lever, `CODE-PRESENT`):** annual = 10× monthly (2 mo free baked in). Owner ko **annual-first** push karna chahiye — yahi ₹1 Cr ki cash timing ka asli unlock hai (monthly collect karne se 12 mo lagenge).

**Top-up packs:** 500 min ₹5,999 = ₹12/min — included-minute rate se UPAR (upsell lever), `CODE-PRESENT`. Heavy voice users ke liye upgrade sasta lagta hai.

---

## 5. Revenue decomposition + funnel math

### 5a. Arithmetic (no assumptions — pure math)

| Target | Tier | Units needed |
|---|---|---|
| ₹1 Cr / month | Starter ₹1,999 | **5,006** |
| ₹1 Cr / month | Advanced ₹5,999 | **1,668** |
| ₹1 Cr / month | Mixed (blended ₹2,990) | **3,345** |
| ₹1 Cr / month | Voice Band C ₹19,999 | **501** |

### 5b. Scenario table (conservative / base / aggressive)

> **Assumptions clearly labelled.** Koi proven funnel ledger me nahi hai — "8 months flat" ka matlab yahi hai. Ye rates **ASSUMPTION** hain, measurement nahi.

Assume chain: **contact → reply 2% · reply → qualified 30% · qualified → trial 40% · trial → paid 20%** ⇒ **contact → paid ≈ 0.048%** (ek customer ~2,083 contacts).

| Scenario | Contact→Paid (ASSUMPTION) | Customers needed | Contacts needed/mo | Contacts/day | Verdict |
|---|---|---|---|---|---|
| **Conservative** | 0.048% | 3,345 (mixed) | **~69.7 crore** | **~2.3 crore/day** | **Impossible** — rails 875/week |
| **Base** | 0.5% (conversion-optimised) | 3,345 | **~6.7 lakh** | ~22,300/day | **Not reachable** on current rails |
| **Aggressive** | 2% | 3,345 | **~1.67 lakh** | ~5,580/day | Stretch — needs paid channels + human telecallers |
| **₹1 Cr via ARPU** | 0.5% | 501 (Band C) | **~1 lakh** | ~3,350/day | Best-shot path but **DLT-gated** |

### 5c. Rails capacity vs requirement (`CODE-PRESENT`)

| Rail | Current cap | Source | Weekly capacity |
|---|---|---|---|
| Email outreach | 25/day (warmup) | `auto_outreach.py` | 175 |
| Outbound voice | `PLATFORM_DIAL_LIMIT=100`/day | `automation_flags.py` / `platform_dial` | 700 |
| Cold WhatsApp | **OFF by design** | compliance invariant | 0 |
| **Total** | | | **~875 contacts/week (~3,800/mo)** |

**Gap:** conservative scenario needs **~69.7 crore** contacts vs **3,800 available** ≈ **183,000×**. Even aggressive 1.67 lakh ≈ **44×** beyond rails.

### 5d. Honest reachability verdict

| Horizon | Monthly collected | Reachable? | What must be true |
|---|---|---|---|
| **Month 1–2** | ₹10k–₹50k | ✅ Yes | Dono gates khule |
| **Month 3–4** | ₹50k–₹5L | 🟡 Stretch | Conversion optimised + annual prepay push |
| **Month 6–12** | ₹5L–₹25L | 🟡 Stretch | DLT cleared + paid rails funded + human telecaller pod |
| **₹1 Cr/month** | ₹1 Cr | ❌ **Not on current rails** | **Requires:** DLT registration, verified/high-volume payment rail, 20–50 human agents (or equivalent proven-automation), ₹X paid-ad budget |

> **Blueprint se consistent:** 7-day blueprint ne ₹5L/7d target ko **97× gap** bataya. ₹1 Cr/month bhi **same structure** ka gap hai — bada number document me likhne se gap band nahi hota; **capacity** chahiye.

---

## 6. Sales funnel + conversion mechanisms (har mechanism code-backed)

> **Rule:** koi bhi "conversion mechanism" likhne se pehle repo me check kiya gaya. Jo code me nahi hai, wo `UNKNOWN`/`CODE-ABSENT` mark hai.

| Stage | Mechanism | Code path | Label |
|---|---|---|---|
| **Lead magnet** | GBP self-audit (16 questions, teaser score) | `app/api/public_site.py` `/api/public/audit/questions` + `/audit/score` | `CODE-PRESENT` |
| **Lead magnet** | `/audit`, `/site-audit`, `/demo` public pages | `public_site.py` (`_RL_AUDIT` bucket) | `CODE-PRESENT` |
| **Capture** | Lead-capture widget → dashboard | `app/marketing/embed_widget.py` | `CODE-PRESENT` |
| **Trial** | 7-din FREE trial (`TRIAL_PACKAGE`) | `packages.py` `trial_status()` | `CODE-PRESENT` |
| **Hot Queue** | Owner-authenticated `/app/inbox` blitz | `CURRENT_STATE.md` WS-GTM1 | `CODE-PRESENT` |
| **Pay page** | Hosted `/pay/{order_ref}` — UPI intent + QR, `tn=order_ref` | `CURRENT_STATE.md` revenue-sprint batch | `TEST-PROVEN` |
| **Promo** | Promo codes (fixed/pct, once-per-customer) | `app/billing/promo_codes.py` | `TEST-PROVEN` |
| **Offers** | DFY setup offers (explicit amount, immutability) | `offers.issue_custom_offer()` | `TEST-PROVEN` |
| **Payment** | Manual UPI submit → owner bank-confirm | `upi_payments.py`, `/app/inbox` | `PRODUCTION-PROVEN` |
| **Invoice** | GST invoice | `app/billing/gst_invoice.py` | `PRODUCTION-PROVEN` |
| **Referral** | Lead→paid flip credit | `_credit_referral` | `TEST-PROVEN` |
| **Reactivation** | Win-back campaign drafts | `packages.py` `_STARTER_CORE` | `CODE-PRESENT` |
| **Speed-to-lead** | Instant reply on new lead | `packages.py` "Speed-to-lead instant reply" | `CODE-PRESENT` |
| **Owner alerts** | Payment/health/incident to Telegram | `config/telegram/setup_spec.yaml` `owner_alerts` `-1003878635977` | `CODE-PRESENT` |

**Funnel stages (canonical):**
`Audit/Lead-magnet → Capture → Trial(7d) → Hot Queue (owner 1-click) → /pay/{order_ref} UPI → owner bank-confirm → GST invoice → Onboarding → Upsell/Annual → Referral`

**Conversion mechanisms jo hum NAHI claim kar sakte (transparency):**
- "Automated payment collection" — **NO**. Manual UPI + owner bank-confirm only (`PRODUCTION-PROVEN`).
- "31 agents converting leads" — **NO**. `dev_workers` = 0 rows (`CODE-PRESENT`).
- "Cold WhatsApp at scale" — **NO**. OFF by design.

---

## 7. Product development roadmap

### Track A — AI Automated Marketing (primary engine)

| # | Milestone | Type | Acceptance | Priority |
|---|---|---|---|---|
| A1 | **Gate 2 unblock** — UPI collection + owner bank-confirm end-to-end, zero synthetic | **Revenue-unblocking** | 1 real ₹ paid via `/pay/{ref}` → invoice in `data/invoices.jsonl` | **P0** |
| A2 | **Hot Queue conversion loop** — owner `/app/inbox` session measurable | Revenue-unblocking | 42 warm leads → ≥2 paid (assumption 5%) | **P0** |
| A3 | **Trial → Paid nudge automation** | Revenue-scaling | Trial expiry nudge fires; tracked conversion | **P1** |
| A4 | **Annual-first checkout** — prepay push on `/pay/{ref}` | Revenue-scaling | ≥30% new sales choose annual | **P1** |
| A5 | **Retention/churn dashboard** (Nikhil) | Revenue-scaling | Churn-risk list live in dashboard | **P1** |
| A6 | **Programmatic SEO (niche×city)** (Ravi) | Revenue-scaling | 500+ SEO pages indexed | **P2** |

### Track B — AI Voice Calling Agent (DLT-gated)

| # | Milestone | Type | Acceptance | Priority |
|---|---|---|---|---|
| B1 | **Gate 1 unblock** — Smartflo DID→VOICE destination set | **Revenue-unblocking** | `GET /v1/my_number` → non-null `destination` | **P0** |
| B2 | **Inbound AI receptionist (Riya)** on live DID | Revenue-scaling | ≥1 real inbound call handled + transcript | **P0** |
| B3 | **Own-DB + consented outbound** (within 9am–7pm, DND fail-closed) | Revenue-scaling | N calls, 0 compliance violations | **P1** |
| B4 | **DLT registration complete** | Revenue-unblocking (cold) | DLT approved; cold outbound legal | **P0** (owner) |
| B5 | **Voice quality tuning** (Meera/Arjun) | Revenue-scaling | qualified-rate ↑ measurable | **P1** |
| B6 | **Yoga/Ayurveda + Band C pilot** | Revenue-scaling | ≥1 Band C customer | **P2** |

### Track C — Execution proof (dono tracks ke liye infra)

| # | Milestone | Type | Acceptance | Priority |
|---|---|---|---|---|
| C1 | **`dev_workers` instrumentation** — lease + heartbeat + idempotency-key UNIQUE | Revenue-unblocking (trust) | `dev_workers` > 0 rows; a task completes idempotently | **P0** |
| C2 | **DB-backed idempotency** (replace `service._IDEMPOTENCY`) | Revenue-unblocking (trust) | Restart-safe; no double-execute | **P0** |
| C3 | **Telegram delivery reliability** (egress + owner creds) | Revenue-scaling | owner_alerts receives payment alert in real time | **P0** |
| C4 | **`_KNOWN_TOOLS` fix** (`openclaw`/`workbuddy`/`codex`) | Revenue-scaling | enrollment reaches `buzzlock_enrolled:true` | **P1** (owner-gated) |
| C5 | **`SMARTFLO_WEBHOOK_SECRET` set** | Security | Webhook auth enforced without breaking inbound | **P0** |

---

## 8. Requirements pool

### P0 — Must have (revenue-blocking)

1. **Owner Gate 1** — Smartflo console DID `+918069879757` → **VOICE Bot** destination set (`PRODUCTION-PROVEN` that API cannot set — 422).
2. **Owner Gate 2** — UPI collection via `/app/inbox` + **bank-credit confirmation** (`owner_confirmed_upi`).
3. **`dev_workers` instrumentation** — DB-backed lease/heartbeat/idempotency (`dev_workers` = 0 rows today).
4. **Telegram delivery reliability** — owner_alerts group (`-1003878635977`) gets real payment/health alerts.
5. **`SMARTFLO_WEBHOOK_SECRET`** set (currently unset — webhook auth disabled).
6. **Real execution proof** — replace process-local `_IDEMPOTENCY` with DB unique constraint.
7. **No new module/agent/loop** until a correlated real-funnel defect is proven (blueprint § "REVENUE VERDICT").

### P1 — Should have (scaling)

8. Annual-first checkout push on `/pay/{order_ref}`.
9. Trial→paid nudge automation with tracking.
10. Dunning + churn-risk dashboard (Nikhil).
11. `_KNOWN_TOOLS` add `openclaw`/`workbuddy`/`codex` (owner-gated trust boundary).
12. Own-DB consented outbound calling (DND fail-closed, 9am–7pm).
13. Voice quality telemetry per-call (Lekha KPIs).

### P2 — Nice to have

14. Programmatic SEO niche×city pages (Ravi).
15. HyperFrames advanced video (currently INERT — toolchain missing in prod image).
16. Community-led growth via Telegram community groups.
17. Affiliate/partner referral programme scale-up.

---

## 9. UI / UX notes (light — Architect will detail)

| Surface | Path | Notes |
|---|---|---|
| Owner dashboard | `/app/revenue-kit` | Pay-link → WhatsApp close text, LAUNCH promo create, ledgers. Owner ka **primary** surface. |
| Hot Queue | `/app/inbox` | Owner-authenticated; **1-click UPI** blitz. 15–30 min/session. |
| Bot Command Center | `/app/bot-command-center` | 9 bots → 31 agents visibility. Must show **honest** state (never fake "all active"). |
| Payment page | `/pay/{order_ref}` | UPI intent + QR, `tn=order_ref`, promo box. Already `TEST-PROVEN`. |
| Customer portal | `/app/...` customer view | 40+ Studio tools, drafts → approve → share. |
| Telegram | `owner_alerts` `-1003878635977` | Payments + health + incidents. Alerts only, no discussion. |
| Telegram | `internal_admin` `-1004460536807` | Deploys, incidents, bot-status. |

**Honesty requirements (UI):**
- Dashboard me **"proven-executing"** ko 🟡/❌ dikhao, ✅ nahi, jab tak `dev_workers` > 0 na ho.
- `team.py` me ek bug hai: `today_actions = max(per_member_today, wf_agent.cycle)` — `workforce_live_status.json` se **`cycle`** uthata hai jo fabricated telemetry thi (`team.py` comment khud kehta hai "TRUST REAL EVENTS, NOT FAKE JSON STATUS" par `cycle` fallback bacha hua hai) — Architect ko yeh flag karna chahiye.

---

## 10. 待确认问题 — Open questions for the Owner (hard questions only)

1. **Realistic monthly target:** ₹1 Cr/month ke liye 3,345+ customers chahiye (blended ₹2,990). Manual UPI + ek owner bank-confirm pe realistically **~10–25 customers/day** process ho sakte hain = **max ~₹25k–₹10L/month**. Kya ₹12 mahine ke liye target **₹5–25L/month** karein, ya ₹1 Cr ke liye **paid rails/human capacity** fund karenge?
2. **DLT registration status:** cold outbound Voice product ke liye DLT registration **kitne % complete** hai? Bina iske Band A/B/C ka bada volume **illegal** hai.
3. **Payment rails:** Stripe/Razorpay removed (permanent decision). ₹1 Cr ke liye manual UPI sufficient nahi — kya **koi verified rail (UPI-verified merchant / bank PG / Razorpay re-eval)** reconsider karenge? (Blueprint forbids reinstating; owner decision chahiye.)
4. **Human telecallers:** kya 20–50 human telecallers hire/train kar sakte hain? Automation alone ₹1 Cr tak nahi pahunch payega (contact cap 875/week).
5. **Marketing budget:** ₹1 Cr ke liye ~5,580 contacts/day chahiye. Kya **paid ads** (Meta/Google) ka budget approve karenge? Kitna/month?
6. **Owner time:** UPI bank-confirm + Hot Queue sessions ke liye roz **kitne minutes** de sakte hain? Ye ₹1 Cr ka **actual bottleneck** hai.
7. **`_KNOWN_TOOLS` edit approval:** `coordination_hub_auth.py` me `openclaw`/`workbuddy`/`codex` add karna owner-gated trust boundary hai — approve karenge?
8. **Telegram owner credentials:** `api_id`/`api_hash` + egress code ke liye green light? (Revenue blocker nahi, par owner alerts ke liye chahiye.)
9. **Voice product positioning:** kya cold outbound ke bina (inbound + own-DB + consented), Voice product ko promote karein — ya DLT approval tak **park** karein?
10. **Automation truth:** kya `dev_workers` instrumentation (Track C) ko **revenue work se pehle** priority denge? Bina execution proof, "maximum automation" ek claim rahega.

---

## 11. Repo evidence contradictions found (Architect ke liye zaroori)

| # | Contradiction | Resolution | Label |
|---|---|---|---|
| 1 | `HERMES_AGENT_ROSTER.yaml` = **8 bots**; `automation_orchestrator.py HERMES_BOTS` = **9 bots** | YAML self-declares SUPERSEDED; canonical = **9 bots** (`docs/architecture/24X7_FINAL_DECISION_2026-09-12.md`) | `CODE-PRESENT` |
| 2 | `7_DAY_REVENUE_PLAN.md §1` "docker exec leadgen_app ..." vs "NO `leadgen_app` container" (§3 brief) | Blueprint ka own §3 + task brief confirm: prod = **systemd `leadgen`**, no container. Blueprint §1 command **stale/wrong** — Architect ko systemd path use karna hai | `STALE` |
| 3 | `DAY_0_REVENUE_BASELINE.md` "₹7,997 / MRR ₹3,998" vs ledger **₹5,997 / 3 real invoices** | Blueprint ne baseline ko STALE declare kiya — **₹5,997 authoritative** | `STALE` |
| 4 | `PRODUCTION_TRUTH.md` "prod SHA `d32a4934` (2026-07-20)" vs `CURRENT_STATE.md` newer SHAs | `PRODUCTION_TRUTH.md` **STALE** (Jul 20). Re-probe `/health` before quoting | `STALE` |
| 5 | `PRODUCTION_TRUTH.md` "`PLATFORM_DIAL_DAILY` HARD OFF" vs `CURRENT_STATE.md` "`PLATFORM_DIAL_DAILY=1`" | Newer probe (2026-08-20) wins: **`=1`**, cap `PLATFORM_DIAL_LIMIT=100` | `STALE` |
| 6 | `AGENT_REGISTRY.md` documents **19** agents vs `team.py` **31** | `AGENT_REGISTRY.md` dated 2026-06-20, **STALE** — must be generated from `team.py` | `STALE` |
| 7 | Brief says `app/platform/automation_flags.py`; actual = `app/api/automation_flags.py` | Brief path wrong; **417 flags** in `app/api/automation_flags.py` | `CODE-PRESENT` |
| 8 | `team.py` comment "TRUST REAL EVENTS, NOT FAKE JSON STATUS" vs `today_actions = max(..., wf_agent.get("cycle", 1))` | `cycle` fallback still reads fabricated `workforce_live_status.json` — **internal inconsistency in live code** | `CODE-PRESENT` |
| 9 | `7_DAY_REVENUE_PLAN.md §3` "Telegram NOT a revenue blocker" vs brief "Telegram delivery reliability" P0 | Both true: Telegram **revenue** blocker nahi, par **owner-alert reliability** P0 hai (operator loop ke liye) | `PARTIAL` |
| 10 | `voice_packages.py` BANDS has **5 bands** (S/F/A/B/C) but `_make_tiers()` returns pilot/starter/freemium/band — S and F planes overlap confusion | Architect ko band→plan mapping clear karni hai; `voice_starter_monthly` (S) aur `voice_a_monthly` (A) dono ₹1,999/₹4,999 pe **separate** hain | `CODE-PRESENT` |

---

## 12. Appendix — evidence index

| Claim | Source |
|---|---|
| ₹5,997 collected FY26-27 | `data/invoices.jsonl` via `app.billing.gst_invoice.stats()` (`PRODUCTION-PROVEN`) |
| 31 agents | `app/platform/team.py` → `STAFF` |
| 9 Hermes bots | `app/platform/automation_orchestrator.py` → `HERMES_BOTS` |
| Kill switch | `is_kill_switch_active()` → `AUTOMATION_STOP_NEW_CLAIMS` |
| DLQ/retry | `retry_count` / `max_retries` / `dlq_count`; `recover_stale_running_tasks()` |
| Pricing | `app/marketing/packages.py`, `app/marketing/voice_packages.py`, `app/marketing/combo_packages.py` |
| Telegram groups | `config/telegram/setup_spec.yaml` (10 chat_ids) |
| Audit funnel | `app/api/public_site.py` `/api/public/audit/questions`, `/audit/score` |
| Deploy | `scripts/deploy_vps.sh` (single authority) |
| Compliance | Blueprint §7; `app/telephony/consent_ledger.py` |

---

**Stage 1 complete.** Handoff → Architect: yeh PRD decision-grade hai, numbers honest hain, aur evidence-labeled hai. Sabse pehla architectural decision: **Track C (execution proof) ko revenue work ke saath parallel chalana hai** — warna "₹1 Cr" aur "31 agents running" dono claims rahenge, facts nahi.
