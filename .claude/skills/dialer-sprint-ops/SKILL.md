---
name: dialer-sprint-ops
description: Untapped prospect phones (~90% prospects ke paas phone hai) ko human-dialer sprint se revenue me badalna — DLT ke BINA legal (human call). Use jab "calls karne hain", "leads se paisa", dialer workflow, ya pipeline-review "ready stuck" dikhaye.
---

# Dialer Sprint Ops (sabse bada untapped asset)

## Kyun yeh, kyun ab
Pipeline truth (2026-06-12 snapshot): ~465 prospects "ready" stage pe stuck (stage-progression ~0), inbound ~0, email coverage sirf ~28% — par PHONE coverage **~91%** (sabse bada untapped asset). AI cold-calling DLT-gated hai; **HUMAN dialing legal hai** (TRAI window 9am-7pm conservative, DND respect). Sprint = Sumit/team khud dial kare, system assist kare. (Live counts ke liye `/api/growth/prospects/search` ya `/app/automation` Prospects tab dekho — number badalta rehta hai.)

## Sprint loop (roz 45-60 min)
1. **List banao**: `/app/automation` → Prospects tab → search filters (niche/city/min_score/has_email) YA `GET /api/growth/prospects/search?min_score=60` (params: niche, city, status, has_email, q, min_score, limit — phone-presence backend score me factor hota). Top 20-30 hot-score pehle (`/api/growth/leads/hot`).
2. **Prep**: har number pe dialer ka **📋 Prep** button (memory_api brief: talking points, objections+jawab, next action). Niche pitch = sales-team analysis (`POST /api/growth/sales/prospect-analysis` for deep-dive on A-grade).
3. **Dial**: `/app/dialer` — 9am-7pm IST hi. Disposition HAR call pe set karo (interested/callback/not_interested/wrong_number) — prospector sync hota hai, scoring seekhती hai.
4. **Interested →** turant: WA 1-click send (proposal/demo link) + `sales_pipeline` deal banao + cadence enroll. Speed-to-lead metric track ho raha hai.
5. **End of day**: leaderboard (`/api/voiceai/` dialer leaderboard) + dispositions review — kal ki list disposition-informed.

## Targets (calibrate karte raho)
20-30 dials/day → 3-5 conversations → 1-2 interested/day realistic shuruat. ~2 hafte me poora ready-pool cover. Connect-rate < 30% = phone validation issue (phone_validate E.164 check chalao).

## Rules
- DND number manually bhi mat dial karo promotional ke liye (compliance posture).
- Disposition KHALI mat chhodo — bina feedback scoring/rotation andha hai.
- "Not interested" = 90-din suppress (consent ledger pattern), pestering nahi.
- AI voice agent in numbers pe TABHI jab DLT clear ho — tab tak human-only.

## Enterprise gate (outbound dialing = HIGH-RISK ops)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk** — outbound dialing legal-gated hai; human-dial bhi compliance posture maintain karta. (AI auto-dial in numbers = DLT clear hone tak BAND.)

**Compliance (fail-CLOSED — human sprint me bhi):**
- **TRAI 9am–7pm IST window** — `/app/dialer` is window me hi; bahar promotional dial mat karo.
- **DND respect** — DND number promotional ke liye manually bhi mat dial; lookup-fail = treat-as-block posture.
- **Opt-out / not-interested = 90-din suppress** (consent-ledger pattern) — pestering nahi, cross-channel honor.
- **AI auto-cold-call** in numbers pe = DLT clear hone tak ILLEGAL (₹10L) → human-only.

**Idempotency / data-integrity:** disposition HAR call pe set (interested/callback/not_interested/wrong_number) — prospector sync + scoring isi pe seekhता; khali disposition = scoring/rotation andha + duplicate re-dial risk. Interested → deal-create + cadence-enroll idempotent (double-enroll na ho).

**Observability:** dialer leaderboard (`/api/voiceai/` dialer) + dispositions review (kal ki list disposition-informed) · speed-to-lead metric · connect-rate <30% = phone-validation issue (`phone_validate` E.164).

**Cost/quota:** human-dial = ₹0 (DLT-free, ~91% phone coverage = biggest untapped asset). Live counts `/api/growth/prospects/search` ya `/app/automation` Prospects tab (number badalta).

**Evidence (done):** sprint = roz dispositions logged + leaderboard updated; agar dialer code touch hua → `.venv\Scripts\python.exe scripts\prod_check.py` green + window/DND gate test. No code change = ops loop, evidence = disposition+leaderboard trail.
