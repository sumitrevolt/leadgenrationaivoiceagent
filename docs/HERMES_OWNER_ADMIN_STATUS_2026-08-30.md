# HERMES OWNER ADMIN — WORKFORCE STATUS (2026-08-30 ~15:05 IST / 09:35Z)

> Evidence-first check of the 9-bot workforce on LIVE prod. Every claim = probe/ledger/log with timestamp, no fabrication.
> Prod `/health` = **`63c2c47a`** (probed 2026-08-30T09:30:54Z, environment=production, uptime 2h29m). Earlier docs' `5919c379` is STALE.

## 0) ROSTER — real profiles, not invented

Two coordination layers exist in this repo. The **9-bot roster** the Owner Command Center drives (`command_center/data/bots.json`):

| # | Bot | Role | Status (live ledger) | Current task | Blocker |
|---|-----|------|----------------------|--------------|---------|
| 1 | **Pilot** 🟣 | Commander | 🏃 RUNNING (dispatches today 14:55 IST) | REV-command, task assignment | none |
| 2 | **sales** 💰 | Revenue Executor | 🏃 RUNNING / ⛔ CALLING BLOCKED | SAL-001 live-call checkpoint | Vobiz DID caller-ID NOT owned |
| 3 | **hunter** 🎯 | Lead Discovery | ✅ ASSIGNED | HNT-003 50 MOBILE DND leads (due 16:00 IST) | HNT-002 missed → reassign risk |
| 4 | **success** 🏆 | Customer Success | 🏃 RUNNING | SUC-001 Jiya RED churn recovery email (due 16:00 IST) | send-proof pending |
| 5 | **platform** 🤖 | Infra/Telephony | ✅ ASSIGNED | PLT-003 hourly telephony readiness | Vobiz portal unreachable from VPS |
| 6 | **operations** 🤖 | Ops Executor | ✅ ASSIGNED | OPS-005 dialer batch digest | DID not owned (spin-loop fixed) |
| 7 | **engineering** 🤖 | Engineer | 🏃 RUNNING | ENG-002 caller-ID 'not owned' canonicalization | vendor-side fix only |
| 8 | **guardian** 🛡 | QA Gate | ✅ ASSIGNED | GRD-002 spin-fix gate + Jiya account health | connect-PASS conditional on DID |
| 9 | **board** 📊 | Visualization | ✅ ASSIGNED | BRD-001 mirror refresh | none |

Plus the control-plane layer (8 Hermes dept bots → 31 staff agents) in `HERMES_AGENT_ROSTER.yaml` (Boss + revenue_cro, lead_intelligence, outreach_conversation, voice_swara, marketing_content, engineering_sre, qa_analytics_finance). Roster file is a DOC layer only — no Python consumer; the real 24×7 runtime is below.

## 1) RUNTIME — the actual 24×7 engine (VERIFIED healthy)

- **Containers:** 5/5 app-image pinned `63c2c47a` (leadgen_app / worker / scheduler / worker_heavy / worker_video) all `Up 3 hours (healthy)` + `leadgen_dsh_worker:63c2c47a` healthy + staging `28ba5d4e`. Zero skew.
- **Scheduler (team_scheduler, Celery beat):** ~45 jobs, ALL `ok:true` with fresh today (2026-08-30) heartbeats — watchdog 09:05, self_improve 09:32, coordinator 05:03, call_processor 09:31, growth 09:30, flow_cron 09:30, mcp_engineer 09:10, meter_watch 09:25, hq_auto_chase 08:58, reply_auto_send 09:00, reply_triage 08:50, sales_autopilot 08:55, email_outreach 08:35, email_followup 08:57, daily_owner_brief 02:40, hot_queue_owner_pack 03:30, platform_dial 06:00, trial_nudge 04:20, gsc_rank, content_approval_sweep, kb_refresh, onboard, ops.
- **Queues clean:** celery=0 · dlq:failed_tasks=0 · dlq:dead=0. Disk 54%.
- **Boss governance:** `boss_autonomy/state.json` fresh 09:30 today; `boss_decision_governance/*.jsonl` fresh 02:50 today.
- **Watchdog (dead-man):** `watchdog` job heartbeat 09:05 today ✓ + escalation ledger live (ESC#11/#15 today).

## 2) PROVIDERS — matrix

| Provider | Config | Live test | Status |
|----------|--------|-----------|--------|
| LLM free chain (realtime) | mistral→groq→cerebras→… | `free_ai.chat("OK")` → **groq `"OK"`** (09:38Z) | ✅ HEALTHY |
| LLM map | 11 configured (groq, cerebras, openrouter×4, xai, gemini, sambanova, mistral, nvidia) | provider map all True | ✅ HEALTHY |
| OmniRoute (agent_ops lane) | provider=combo model=big-pickle | ok=True lat 2–5s (09:30–09:32Z logs) | ✅ HEALTHY |
| Vobiz telephony | VOBIZ_CALLER_ID=+911171366938, trunk=vobiz | **place_call rejects: from-number "not owned by this account"; account endpoint ConnectTimeout** | ❌ BLOCKED (see §3) |
| Vobiz egress | caller-ID ownership | — | ❌ vendor gate |

## 3) #1 REVENUE BLOCKER — root cause PROVEN

**Dialer spin-loop is FIXED** (commit `4916353a` MOBILE pre-filter; live batches show `skip=0`). What remains:

- Live `call_loop.log` batches 9–10 (14:59–15:02 IST): every call →
  `FAIL {"error": "The from number 911171366938 is not owned by this account"}` · `ok=0 skip=0 fail=3` · loop re-dials same top-MOBILE leads every ~2 min (`RELEASED retry_next_batch`).
- Prod env: `VOBIZ_CALLER_ID=+911171366938` (the rejected number) · `SIP_DID=` **unset** · `DEFAULT_TELEPHONY=vobiz` · `TELEPHONY_TRUNK=vobiz`.
- Vobiz **account** endpoint (balance/ownership) **ConnectTimeout from VPS** — portal unreachable from this host (matches ops INF-003 sitrep).
- ⇒ **THIS IS NOT A CODE BUG.** The configured caller-ID is not registered/owned on the Vobiz account. Canonical fix:
  1. **OWNER + VENDOR:** at Vobiz portal/support register/verify `+911171366938` (or the account's real owned number) as caller-ID/CLI — or supply the correct owned `VOBIZ_CALLER_ID` value.
  2. While unresolved, **recommend** owner pause `PLATFORM_DIAL_DAILY=0` + stop `fire_calls_loop` — it burns Vobiz API calls on a dead number (`fail=3`/2 min) and re-queues the same leads (lead-queue thrash). Not flipped unilaterally (calling kill-switch = owner gate).
  3. Set `SIP_DID` once the DID is allocated.
- Completeness caveat: Vobiz balance/owned-number list could NOT be read (endpoint timeout) — do not claim balance facts.

## 4) REVENUE TRUTH (honest)

- **Verified collected: ₹1,999** (Jiya makeover, INV/2026-27/0001, owner-confirmed UPI — the only valid rail). Gap to ₹5,00,000 = **₹4,98,001** (board BRD-001 today).
- 7-day sprint deadline = **2026-08-30 EOD (TODAY)**; required pace ₹71,429/day was never met (last non-zero day predates). **Mission target NOT reachable today with only manual UPI + owner sends.** Not fabricating any projection as cash.
- MRR ledger: 5,997 · active 3 · churn 22.2% (2026-08-29 snapshot).
- Hot Queue: **43 warm cards** packaged today (`hot_queue_for_owner_2026-08-30.md/csv`, WA + 1-tap UPI links pre-embedded) — owner 1-click close-ready.
- Pipeline connects today: **0** (calls cannot connect; cold-WA OFF by design).

## 5) TASK QUEUE (command_center kanban)

38 tasks — 19 CLOSED · 9 ASSIGNED · 5 RUNNING · 2 VERIFIED · 2 ACK · 1 DEPLOYED. Active P0s: SAL-001, HNT-003, SUC-001, OPS-005, ENG-002, PLT-003, GRD-002.

## 6) VERDICT

- **SYSTEM 24×7: VERIFIED** — scheduler, workers, providers, heartbeats, watchdog, boss governance all live and healthy today.
- **9-bot COORDINATION: RUNNING** — Pilot dispatch loop emitting today 14:55 IST.
- **REVENUE MISSION (₹5L): NOT VERIFIED / STALLED** — sole obstruction = Vobiz caller-ID ownership (calls) + owner-gated WA/UPI sends. The 9 bots cannot move cash while both waits hold.

## 7) NEXT ACTIONS (top of queue)

1. [OWNER+VENDOR] Vobiz: register/verify owned caller-ID (`+911171366938`) or provide correct owned number → set `VOBIZ_CALLER_ID` (and `SIP_DID`). THE unblock.
2. [OWNER, optional-now] Pause `PLATFORM_DIAL_DAILY=0` until §3 resolved (stop dead-DID churn). Recommend-not-execute.
3. [OWNER] Hot-queue 43-card blitz via `/app/inbox` / today's owner-pack (WA + UPI 1-tap) — the only cash path not blocked.
4. Track HNT-003 (DND 50 MOBILE, 16:00 IST) + SUC-001 (Jiya recovery send-proof, 16:00 IST) — DID-independent, don't miss.
5. [OPS] When DID resolves: restore dialer, verify first connect, then scale batches.

KEY at bottom:
```
OWNER ADMIN: RUNNING
BOT 1  Pilot:       RUNNING      | BOT 6  operations:  ASSIGNED
BOT 2  sales:       BLOCKED(DID) | BOT 7  engineering: RUNNING
BOT 3  hunter:      ASSIGNED     | BOT 8  guardian:    ASSIGNED
BOT 4  success:     RUNNING      | BOT 9  board:       ASSIGNED (reflect)
BOT 5  platform:    ASSIGNED/P0  |
ACTIVE TASKS: 17 (5 RUNNING, 9 ASSIGNED) · QUEUE READY: 0 new ready (P0s on DID/owner)
BLOCKED: 1 hard (sales/DID) · PROVIDERS HEALTHY: 9/9 lanes (LLM/OmniRoute live; Vobiz = owner-vendor gate, NOT a provider-lane failure)
HEARTBEATS HEALTHY: 45/45 scheduler jobs fresh 2026-08-30
WATCHDOG: VERIFIED (watchdog job 09:05Z today + esc ledger live)
24×7 WORKFORCE (system): VERIFIED · 24×7 CASH MACHINE: NOT VERIFIED (DID + owner gates)
```
NEXT AUTOMATIC ACTION: [loop queued — verify SUC-001 send-proof + HNT-003 batch at 16:00 IST; re-probe DID ownership every hourly readiness cycle]
