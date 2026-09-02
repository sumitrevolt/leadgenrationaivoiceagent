# Hot Queue blitz — Phase 0 (2nd paid Marketing)

**Goal:** Close ≥1 new ₹1,999/mo Marketing subscriber this week (2nd paying customer after Jiya).
**Owner time:** 15–30 min/day. Code path GO. HTTP 200 shell ≠ cards. Token page pe hona zaroori.

**Scoreboard:** admin **Aaj ka business** → `💰 Aaj naye paid` (`paid_today`). Jiya already on ledger; north star = +1 Marketing ₹1,999/mo.

## 1) Inbox (token-paste)

1. Login: https://leadsgenai.in/app/admin-login
2. Open: https://leadsgenai.in/app/inbox
3. Agar cards nahi: `#tok` me **Admin token paste karo** → Save → Reload. (login JWT `accessToken` bhi chalta hai)
4. Tab **🔥 Hot Queue / Aaj**. Interested + question pehle. Noise skip.
5. Max 10 cards/day:
   - Call **or** 1-click WA draft → **human send only** (cold auto-WA OFF)
   - Outcome card pe log (interested / later / no)
6. Buyer ready → https://leadsgenai.in/pricing ya https://leadsgenai.in/start
7. Stop jab window khatam ya buyer `/start` pe hai. DND/TRAI/DPDP mat chhedo.

Empty cards **after** token? ENG ticket — pehle paste/screenshot bhejo. Shell 200 pehle se proven.

## 2) UPI aaye to (Bind → Re-Approve)

https://leadsgenai.in/app/admin#sec-upi-selfserve
Card: **UPI payments — customer ne pay claim kiya**

1. Row pending **or** approved-not-activated.
2. Guest / `client: none` → **🔗 Bind client** (marketing client id). Unknown id fail-closed.
3. Phir **✓ Approve** (re-approve). Bind ke bina Approve = `approved_but_unbound`, paid nahi.
4. Queue empty ho to stop. `UPI_AUTO_ACTIVATE` live=1 scoped allowlist — **flip mat**.

## 3) Bank-credit confirm

Canonical method = `owner_confirmed_upi`. Bind ≠ paid. Bank me credit dikhe tab hi admin confirm. Scoreboard = **Aaj naye paid**. Credit na aaye to fake `paid_today` mat likho.

## Exit (Phase 0)

- [ ] ≥2 paying Marketing (Jiya + 1)
- [ ] inbox → start → paid loop ek baar
- [ ] koi compliance gate off nahi

Jab tak dono box false: ads / GSC / CRO = **read-only** → [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md)

## Optional same-day (paisa nahi)

Boss: pehle `python scripts/buzz_start_harness.py --agent Boss --dry-run` (agent sandbox yahi tak). Real start owner machine: [BOSS_HARNESS_CANARY.md](BOSS_HARNESS_CANARY.md)

## Non-goals

Paid ads · GSC arm · DSH flag change · cold WA auto · dunning kill · fake paid · DLQ flush · `WEB_CONCURRENCY` raise · `CELERY_ONBOARD_QUEUE` arm.
