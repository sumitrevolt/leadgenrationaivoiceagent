# Agentic Customer Acquisition Playbook (2026, India) — LeadGenAI
**Goal:** customers tak pahunchne ke SAARE agentic methods. Legend:
✅ legal/safe · ⚠️ limits/opt-in · 🔴 DLT chahiye · `[BUILT]` / `[PARTIAL]` / `[TO-BUILD]`

---

## 🔑 2026 ka asli insight
Single channel nahi jeetta — **AI ek CADENCE chalata hai across channels**: voice → no-answer → SMS → email → LinkedIn → (opted) WhatsApp. **Intent-triggered** (site-visit, audit-start) aur **event-triggered** (funding, naya owner, job-change) outreach, aur khud **A/B optimize** karta. Tumhare paas **journey engine** hai = iska foundation.

## ⭐ DLT = 1 paperwork, 3 channel unlock
Tum DLT register kar rahe ho → **Voice + SMS + RCS teeno** ek saath legal ho jaayenge (SMS/RCS ko app-opt-in NAHI chahiye, sirf DLT consent). Setup 2-4 hafte. Yeh sabse bada multiplier.

---

## A) OUTBOUND — AI khud pahunchta hai

| # | Channel | India-legal | Build | Note |
|---|---------|-------------|-------|------|
| 1 | **Voice / Phone** (set-up ho raha) | 🔴 DLT | `[BUILT]` | AI call → qualify → demo → book → payment-link. **High-intent ke liye IVR**. Sabse bada. |
| 2 | **Email** | ✅ | `[BUILT, LIVE]` | Cold + Day-3/7 nurture, auto. Reply-triage. Abhi chal raha. |
| 3 | **SMS (DLT)** | 🔴 DLT | `[BUILT, gated]` | `app/integrations/sms_dlt.py` — BSP creds + `SMS_DLT_ENABLED=1` flip. Draft/auto gated. |
| 4 | **RCS (DLT)** | 🔴 DLT | `[TO-BUILD]` | Rich cards/carousel/buttons, **no opt-in**, Android (Jio/Airtel/Vi/BSNL). SMS ka premium upgrade. ★ |
| 5 | **WhatsApp** | ⚠️ opt-in | `[PARTIAL]` | Cold-blast = **BAN**. Sirf **opted-in** (audit/inquiry walon) ko official Cloud API + cold ke liye 1-click. 6-10x CTR. |
| 6 | **LinkedIn** | ⚠️ limits | `[BUILT, draft-only]` | `linkedin_assist.py` — comment+connect+DM drafts; manual send (ban-safe). |

## B) INBOUND — customer khud aata hai (best long-term, FREE)

| # | Channel | Legal | Build | Note |
|---|---------|-------|-------|------|
| 7 | **Programmatic SEO / blog** | ✅ | `[PARTIAL]` | AI niche×city pages (`/blog`) → organic discovery. Compounds. `seo-growth` skill. ★ |
| 8 | **Free lead-magnet (GBP audit)** | ✅ | `[BUILT /audit]` | AI auto-audit → email-gate → capture. **Best top-of-funnel**. Promote everywhere. ★ |
| 9 | **Social organic + comment→DM** | ⚠️ | `[PARTIAL]` | AI posts IG/FB/LinkedIn (`post_generator`) + comment pe reply → DM (opt-in). |
| 10 | **Google Business Profile / Maps** | ✅ | `[PARTIAL]` | Reviews → local ranking → inbound (`review_engine`). |
| 11 | **Reels / short-video** | ✅ | `[PARTIAL]` | AI-scripted reels (`reels.py`) → demand-gen. |
| 12 | **Directories (apni listing)** | ✅ | `[TO-BUILD]` | IndiaMart/JustDial/Sulekha pe **apni service** list karo (jahan SMB marketing-help dhundte). |

## C) PAID — agentic (budget chahiye)

| # | Channel | Build | Note |
|---|---------|-------|------|
| 13 | **Google/Meta Ads** | `[PARTIAL]` | AI ad-copy + RSA (`ads_copy.py`) → landing. ₹ budget chahiye. |
| 14 | **Retargeting** | `[TO-BUILD]` | Pixel + audit-starters/visitors ko retarget. |

## D) LOOPS / viral (FREE)

| # | Channel | Build | Note |
|---|---------|-------|------|
| 15 | **Referral engine** | `[BUILT referral_kit]` | Happy client → referral, AI-driven. |
| 16 | **Review-as-acquisition** | `[BUILT review_engine]` | Reviews → rank → inbound. |

## E) ⭐⭐⭐ META: Omnichannel Cadence Orchestrator `[BUILT, gated]`
**Yahi "bahut saare approaches" ko EK system me baandhta hai.** `app/marketing/cadence.py` — per-lead multi-channel sequence (email→sms→wa→voice→linkedin…). **Gated `CADENCE_ENGINE=1`**. Journey engine (`journeys.py`) inquiry/signup triggers ke saath.

---

## 🎯 Mera build-order (FREE + legal pehle)
1. ~~Omnichannel cadence orchestrator~~ ✅ **BUILT** — flip `CADENCE_ENGINE=1`.
2. **SMS-DLT live send** (DLT + BSP creds flip) — code ready, paperwork pending.
3. ~~LinkedIn comment-first agent~~ ✅ **BUILT** (draft-only) — `linkedin_assist.py`.
4. **Inbound push:** SEO niche×city pages + audit-magnet promote — compounding, free.
5. Fir RCS, WhatsApp-opted-in, ads (budget pe).

**Honest:** breadth se zyada **consistency** jeetti — 2-3 channel rozana chalao > 10 channel kabhi-kabhi. DLT tumhara #1 unlock (3 channel kholta).
