# NEXT todos — after Next42 (2026-08-15)

Agent-side Next42 is **DONE**. This list is **not** a replay of those 42 tasks.
Money sequence stays: **Hot Queue → UPI Bind/Re-Approve → bank-credit confirm → Phase 0 exit** before ads / GSC / CRO.

**Prod SHA (this file):** `91958c23` · `healthy` · `environment:production`
Re-probe 2026-08-15: `02:37:40Z` uptime `4h 53m 14s` then `02:40:09Z` uptime `4h 55m 43s` (timestamp advanced = not a cached `/health`). Prior same-day pair `01:27:55Z` / `01:28:53Z` still valid ancestry.
Activation: `payments_ready=true` · `blocker_count=1` named **`upi_pending_unactioned`** (SSH `_PROBES`) · `paid_today=0` IST 2026-08-15 honest empty day (`activations_today=0`).
One-command: `.venv\Scripts\python.exe scripts\next_todos_ready.py` · DSH plan: `scripts\dsh_next_todos_plan.py` (not Harness.io).
Evidence: [NEXT_TODOS_READY.md](NEXT_TODOS_READY.md) · [NEXT42_EVIDENCE.md](NEXT42_EVIDENCE.md) · [CAPACITY_50_DAY.md](CAPACITY_50_DAY.md) · [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md) · [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md) · [BOSS_HARNESS_CANARY.md](BOSS_HARNESS_CANARY.md)

Do **not** edit `C:\Users\Ratanshila\.cursor\plans\next_20_tasks_f92eef28.plan.md`.

---

## 1. Situation

Technical money path is **GO**: UPI rail live, inbox shell HTTP 200, T31 ntfy + UPI `list_actionable` True in the running app, Jiya ₹1,999/mo already on ledger. Revenue is **WAIT**: `paid_today=0`, named blocker is owner-unactioned UPI, 2nd Marketing customer does not exist yet. Code/deploy/flags cannot fake the 15–30 min Hot Queue blitz, Bind → Re-Approve, or bank-credit confirm. Capacity toward 50/day is a **backend factory sheet**, not a live claim (`/` 429 at 5 concurrent; heavy worker 155% CPU; `CELERY_ONBOARD_QUEUE` UNSET). Live `.env` already has hub / dunning / `UPI_AUTO_ACTIVATE` / `DSH_RUNTIME_ENABLED` =1 — **observe and confirm, do not flip from this plan**.

---

## 2. Workstreams (max 3)

WS-SEC (voice FROZEN, DND/TRAI/DPDP fail-closed) is a **constraint inside all three**, not a 4th stream.

| ID | Outcome | Next exact action | Stop if |
|---|---|---|---|
| **WS-GTM1** Hot Queue → 2nd paid | 2nd ₹1,999/mo Marketing customer | Owner opens https://leadsgenai.in/app/inbox with **admin token on the page**, 15–30 min, interested/question first (max 10 cards). Ready buyer → `/pricing` or `/start`. UPI aaye to Bind → Re-Approve → **bank-credit confirm**. Checklist: [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md) | Phase 0 exit ticked (Jiya + 1) **or** daily window ends. No DND/TRAI weaken. |
| **WS-BUZZ** Agent-chat | Tools + Boss coordinate; not a 32nd STAFF | Owner (not agent sandbox): `python scripts/buzz_start_harness.py --agent Boss` (**not** `--dry-run`), then `#admin` `@Boss` canary **≥600s**. Canonical Boss `1b13cecc`. Comb Desktop Save **only after** Boss replies. | Boss replies once in `#admin` with Evidence. Hub stays interface, not control plane (`COORDINATION_HUB_ENABLED` live=1 already — do not treat as 32nd STAFF). |
| **WS-REV50** Product-1 capacity | Backend toward 50 paid/day **without claiming live** | After Phase 0 exit only: owner ads/GSC per [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md). Until then: keep `WEB_CONCURRENCY=2`, keep `CELERY_ONBOARD_QUEUE` UNSET, do not dump onboard onto heavy (kb-warmup ~96s + earlier 155% CPU). | Phase 0 **not** exited → **no ads/GSC/CRO**. Heavy warmup still recurring → **no** onboard-queue arm. Ledger `paid_today` never rewritten as “50/day live”. |

---

## 3. Numbered todos

Role: **OWNER** = human click / bank / Desktop. **ENG** = agent-safe after claim. **GATED** = blocked until a named stop-condition.

### Unblock money (do these first)

1. **OWNER — Hot Queue blitz (today, 15–30 min)**
   **Why:** Mid-funnel is the only unpaid bottleneck; code path already GO; HTTP 200 shell ≠ cards loaded.
   **Do:** Token on `/app/inbox` → interested/question → call or 1-click WA draft → **human send only** → log outcome. Max 10/day.
   **Stop:** Window over, or a buyer is on `/start`. Compliance gates untouched.

2. **OWNER — UPI Bind → Re-Approve**
   **Why:** Named blocker `upi_pending_unactioned`; `payments_ready=true` so the rail is waiting on owner, not engineering.
   **Do:** Admin pending (pending **or** approved-not-activated) → Bind → Re-Approve. Guest bind if no login. Manual UPI only.
   **Stop:** Row bound + re-approved, **or** queue empty. Do not flip `UPI_AUTO_ACTIVATE` (live=1, still scoped to allowlist).

3. **OWNER — Bank-credit confirm**
   **Why:** Canonical payment method is `owner_confirmed_upi`. Bind without bank credit ≠ paid.
   **Do:** Confirm credit in bank, then owner-confirm in admin. Scoreboard = admin “Aaj naye paid” (`paid_today`).
   **Stop:** Ledger shows the new Marketing sub + invoice, **or** no credit landed (do not fake paid).

4. **OWNER — Phase 0 exit tick**
   **Why:** Ads/GSC/CRO before 2nd paid burns time and ₹.
   **Do:** Tick [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md) exit: ≥2 paying Marketing (Jiya + 1) + one inbox→start→paid loop.
   **Stop:** Both boxes true. Until then Phase 1 runbook is **read-only**.

### Parallel (does not replace 1–4)

5. **OWNER — Boss harness + `#admin` canary**
   **Why:** Next42 left harness dry-run only; agents cannot spawn Desktop.
   **Do:** `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` in `#admin`, wait **≥600s**. Identity `1b13cecc`.
   **Stop:** One real reply with Evidence. Do not start from agent sandbox.

6. **GATED — Comb Desktop Save**
   **Why:** Comb is CODE-READY; Save before Boss replies creates a silent second identity.
   **Stop-condition to start:** Todo 5 reply exists. Then owner Desktop Save only.

7. **OWNER — Confirm live flag mismatches (observe, do not flip)**
   **Why:** Live ≠ some memory lines: `COORDINATION_HUB_ENABLED=1`, `DUNNING_ENGINE=1`, `UPI_AUTO_ACTIVATE=1`, `DSH_RUNTIME_ENABLED=1`. Next42 did not change `.env`.
   **Do:** Say stay-as-is **or** schedule a dedicated owner session to change. Check dunning is not harassing Jiya (observe sends; no kill from ENG).
   **Stop:** Written stay/change. ENG must not set these from this plan.

### ENG (only if 1–4 are moving or blocked on a **code** bug)

8. **ENG — Stay behind origin without `reset --hard`**
   **Why:** PR #364 docs-only merged (`c35edb4d`); local main may lag.
   **Do:** `git fetch`; surgical pull/rebase only if owner asks. Never `git add -A`.
   **Stop:** Fetch done. No deploy unless owner asks.

9. **ENG — Inbox only if owner reports cards empty after token**
   **Why:** Shell 200 is proven; card load is unproven without auth. Do not pre-debug.
   **Stop:** Owner paste of empty-cards after token, **or** cards work (no ticket).

10. **ENG — After 2nd paid: onboard fail-rate for **that** tenant (T17)**
    **Why:** `setup_done` vs real KB seed; wizard rewrite forbidden.
    **Do:** Measure; retry `onboard_client` only if that tenant is stuck.
    **Stop:** Tenant `setup_done` **or** fail recorded. Do not arm `CELERY_ONBOARD_QUEUE`.

11. **ENG — Heavy-worker heat (read-only, after Phase 0 or if GTM stalls on onboard)**
    **Why:** 155% CPU / `heavy=2` is why onboard→heavy is NO-GO.
    **Do:** Identify job names; do not flush `dlq:dead=23` (trainer TimeLimitExceeded).
    **Stop:** Names written in evidence. No queue arm, no DLQ flush.

### GATED — Phase 1 (after Phase 0 exit only)

See [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md). Do not start from this file.

12. **GATED — T13 ads (OWNER ₹)** — Meta/Google → `/audit` or `/start` + UTM; daily cap + kill **outside** product; pause if CAC > 1-month GM. No in-app auto-spend.
13. **GATED — T14 GSC** — creds first, then separate `GSC_ENABLED` (today UNSET).
14. **GATED — T15 Postiz own-brand cadence** — existing channels only; no new social stack.
15. **GATED — T19 `/start` CRO** — one CTA; manual UPI unchanged. Copy/layout only after Phase 0.
16. **GATED — T18 referral** — existing `/app/affiliates` + kit POST; no new engine.
17. **GATED — `CELERY_ONBOARD_QUEUE`** — arm only after measured enqueue→start >5 min on a **staging** 50-job burst **and** heavy CPU not 155%. Still routes to existing `heavy` worker (no new queue name).

---

## 4. Explicit non-goals

- Re-planning or re-implementing Next42 (agent-side complete on `91958c23`).
- Swara / voice / telephony code (FROZEN). `VOICE_LAUNCH_KILL=0` stays; do not edit the path.
- Arming: cold WA (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0` OK), `GSC_ENABLED` without creds, `HARNESS_SESSION_EVENTS`, `CELERY_ONBOARD_QUEUE`, raising `WEB_CONCURRENCY` off `/` 429s.
- Flipping hub / dunning / `UPI_AUTO_ACTIVATE` / `DSH_RUNTIME_ENABLED` from an agent session.
- Claiming **50/day live**. Simulated 50 onboard tests ≠ production throughput.
- Flushing DLQ. `git add -A`. `reset --hard`. Commit / push / deploy unless owner asks.
- Treating Buzz / Coordination Hub as production control plane or a 32nd STAFF.
- Paid LLM. Stripe/Razorpay. In-app ad-spend buttons.
- Creative OS / HyperFrames / daily-video flag arm. DSH retirement / executor delete. Stage B AMBER OpenClaw.
- A 4th workstream (WS-SEC / WS-DSH / WS-AMAX stay parked).

---

## 5. Success

**This week (Phase 0):**
- Owner did ≥1 authenticated inbox blitz.
- If a UPI arrived: Bind → Re-Approve → bank confirm.
- **North star:** 2nd paying Marketing customer on ledger (`paid_today` ≥1 on that IST day, ≥2 total Marketing paying).
- Optional: Boss `#admin` canary reply (≥600s). Comb still gated.

**This month (Phase 1, only after Phase 0 exit):**
- Repeatable inbox→start→paid loop.
- Owner ads with external daily cap + CAC kill.
- GSC creds then consider `GSC_ENABLED`.
- Onboard fail-rate measured on the 2nd tenant.
- Still **not** 50/day live; still `WEB_CONCURRENCY=2`; still no onboard→hot-heavy.

**North-star KPI (unchanged):** new paid Marketing activations / day on the billing ledger — not leads, not `/health` 200s, not simulated onboard tests.

---

## 6. READY board (2026-08-15 02:40Z, CURSOR + governed DSH)

| # | Todo | Status | Evidence |
|---|---|---|---|
| 1 | Hot Queue blitz | **OWNER-WAIT** | `/app/inbox` HTTP 200; token-paste one-pager [HOT_QUEUE_BLITZ_CHECKLIST.md](HOT_QUEUE_BLITZ_CHECKLIST.md). Cards unproven without owner token. |
| 2 | UPI Bind → Re-Approve | **OWNER-WAIT** | Named blocker `upi_pending_unactioned`; `payments_ready=true`; UI `/app/admin#sec-upi-selfserve`. |
| 3 | Bank-credit confirm | **OWNER-WAIT** | `owner_confirmed_upi`. `paid_today=0` / `activations_today=0` (02:42Z). Do not fake. |
| 4 | Phase 0 exit | **GATED** | Still 1 paying Marketing (Jiya). |
| 5 | Boss `#admin` canary | **OWNER-WAIT** | `--dry-run` EXIT 0 identity `1b13cecc`; real start = owner. [BOSS_HARNESS_CANARY.md](BOSS_HARNESS_CANARY.md) |
| 6 | Comb Desktop Save | **GATED** | After todo 5 reply. |
| 7 | Live flag mismatches | **OWNER-WAIT** | Observe, do not flip: hub/dunning/UPI_AUTO/DSH_RUNTIME=`1`. Cold WA=0, GSC UNSET, HSE UNSET, onboard queue UNSET, `WEB_CONCURRENCY=2`. |
| 8 | Stay behind origin | **READY** | `git fetch` done. Local `cb289d61` behind `origin/main` `c35edb4d`. No `reset --hard`. No deploy. |
| 9 | Inbox empty-cards debug | **GATED** | No owner empty-after-token paste. |
| 10 | Onboard fail-rate 2nd tenant | **GATED** | After 2nd paid. Do not arm `CELERY_ONBOARD_QUEUE`. |
| 11 | Heavy-worker heat | **READY** | 02:41Z heavy CPU **0.46%** (earlier same-day 155% during warmup). Jobs: `self_improve_tick` (`channel_experiments`), `run_staff_job`, `[kb-warmup]` fastembed ~96s (`solar_residential`). `heavy` llen=0. `dlq:dead=24` — do not flush. Still **no** onboard→heavy arm. |
| 12–17 | Phase 1 ads/GSC/CRO/onboard-queue | **GATED** | [PHASE1_GATED_RUNBOOK.md](PHASE1_GATED_RUNBOOK.md) |

DSH how-used: `verify_dsh_supply_chain.py` EXIT 0; local Linux `dsh_runtime_smoke.py --image leadgen-dsh:smoke-a` **DSH_RUNTIME_SMOKE_OK** shutdown=0.719s cancel=3.875s; governed MCP memory turn `scripts/dsh_next_todos_plan.py` (Kavya `ops_health_check`, UPI proposal 403, `*` allowlist collapses). Binary **not** pointed at prod. `DSH_RUNTIME_ENABLED` live=1 observed, not flipped. `swara`/`ananya` frozen. Legacy executor not deleted. `HARNESS_SESSION_EVENTS` UNSET.
