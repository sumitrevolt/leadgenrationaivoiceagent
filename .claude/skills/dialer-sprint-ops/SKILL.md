---
name: dialer-sprint-ops
description: 421 untapped prospect phones (91%) ko human-dialer sprint se revenue me badalna — DLT ke BINA legal (human call). Use jab "calls karne hain", "leads se paisa", dialer workflow, ya pipeline-review "ready stuck" dikhaye.
---

# Dialer Sprint Ops (sabse bada untapped asset)

## Kyun yeh, kyun ab
Pipeline truth (2026-06-12): 464 prospects "ready" stuck, inbound ~0, asli asset = **421 phones (91%)**. AI cold-calling DLT-gated hai; **HUMAN dialing legal hai** (TRAI 10am-7pm, DND respect). Sprint = Sumit/team khud dial kare, system assist kare.

## Sprint loop (roz 45-60 min)
1. **List banao**: `/app/automation` → Prospects tab → search filters (niche/city/min_score, has_phone) YA `GET /api/growth/prospects/search?min_score=60&has_phone=1`. Top 20-30 hot-score pehle (`/api/growth/leads/hot`).
2. **Prep**: har number pe dialer ka **📋 Prep** button (memory_api brief: talking points, objections+jawab, next action). Niche pitch = sales-team analysis (`POST /api/growth/sales/prospect-analysis` for deep-dive on A-grade).
3. **Dial**: `/app/dialer` — 10am-7pm IST hi. Disposition HAR call pe set karo (interested/callback/not_interested/wrong_number) — prospector sync hota hai, scoring seekhती hai.
4. **Interested →** turant: WA 1-click send (proposal/demo link) + `sales_pipeline` deal banao + cadence enroll. Speed-to-lead metric track ho raha hai.
5. **End of day**: leaderboard (`/api/voiceai/` dialer leaderboard) + dispositions review — kal ki list disposition-informed.

## Targets (calibrate karte raho)
20-30 dials/day → 3-5 conversations → 1-2 interested/day realistic shuruat. 2 hafte me 421 cover. Connect-rate < 30% = phone validation issue (phone_validate E.164 check chalao).

## Rules
- DND number manually bhi mat dial karo promotional ke liye (compliance posture).
- Disposition KHALI mat chhodo — bina feedback scoring/rotation andha hai.
- "Not interested" = 90-din suppress (consent ledger pattern), pestering nahi.
- AI voice agent in numbers pe TABHI jab DLT clear ho — tab tak human-only.
