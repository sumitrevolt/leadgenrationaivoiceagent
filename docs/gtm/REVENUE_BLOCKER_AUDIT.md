# REVENUE BLOCKER AUDIT — LeadGen AI

**Date:** 2026-08-15
**Auditor:** Cursor (fresh after timed-out agent `c8fee2b7`; leftover audit file was absent)
**Prod:** https://leadsgenai.in
**DSH:** this repo's governed DeepSeek Harness runtime (lineage deepseek-ai/deepseek-harness) — **not** Harness.io
**Evidence labels:** VERIFIED · PARTIAL · BROKEN · DISABLED · NOT_CONNECTED · NOT_TESTED · UNKNOWN

Probes (UTC): public `/health` 07:51:24Z uptime `10h 6m 58s` → 07:55:32Z `10h 11m 6s` → host `08:08:50Z` `10h 24m 24s`. Timestamps advanced = live, not cache.

---

## 1. EXECUTIVE VERDICT

**Measurable revenue aaj nahi aa raha kyunki owner execution rukha hai, payment rail nahi.**

| Gate | Verdict | Evidence |
|---|---|---|
| Technical money path | **GO** | Funnel HTTP 200; `payments_ready=true`; UPI rail + `list_actionable` live |
| Authenticated Hot Queue | **WAIT (owner)** | `/app/inbox` shell 200; cards need admin token |
| UPI activation | **WAIT (owner)** | 1 approved-unbound row, `has_client=0`, stale ≥6h |
| Bank-credit confirm | **WAIT (owner)** | Canonical `owner_confirmed_upi`; cannot be faked |
| REVENUE GENERATED today | **WAIT** | `paid_today=0` / `activations_today=0` IST 2026-08-15 — honest empty day |
| Deploy truth | **DRIFT** | Live `91958c23`; `origin/main` `920a3e62` (#365+#366 undeployed) |

**First money-path break:** owner ne `/app/inbox` blitz + UPI Bind→Re-Approve + bank confirm nahi kiya. Code naya module bana ke yeh unlock nahi karega.

**Second (code) break, undeployed on live:** PR #365 `hot_queue_candidates` + `auto_forward_positive_replies` live inbox se **NOT_CONNECTED** the. Is session ne unhe `/app/inbox` Hot Queue me synthetic `callflag:` cards ke through wire kiya (branch `cursor/revenue-blocker-p0`, **not deployed**).

**Do not claim:** 50 paid/day live · fake `paid_today` · Boss harness running · DSH generating revenue.

---

## 2. TOP 10 REVENUE-BLOCKING MISTAKES

### Rank 1 — P0 — Owner Hot Queue unused
- **Mistake:** Mid-funnel human action (token-on-page, 15–30 min) nahi ho rahi.
- **Evidence:** VERIFIED — `/app/inbox` 200; `HOT_QUEUE_BRIEF_DAILY=1`; ntfy URL/topic SET; `_notify_owner_once` present in running app; owner blitz still remaining per SESSION_HANDOFF.
- **Revenue impact:** 2nd ₹1,999/mo Marketing customer nahi banta.
- **Root cause:** Process/owner time, not missing route.
- **Exact failure point:** Authenticated cards after `#tok` paste — agent login nahi karega.
- **What should happen:** Owner interested/question pe Call ya 1-click WA (human send).
- **What actually happens:** Shell live, cards unproven this session (NOT_TESTED without token).
- **Fix:** Owner follows `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md`. Code cannot fake this.
- **Files:** `frontend/inbox.html`, `app/platform/reply_agent.py`, `app/api/growth.py`
- **Validation:** After token, cards render; outcome logged.
- **Path unlocked:** 1 closeable conversation / day.

### Rank 2 — P0 — UPI approved-unbound sitting stale
- **Mistake:** Named blocker `upi_pending_unactioned` = money claim without client bind/activation.
- **Evidence:** VERIFIED SSH 08:08Z — `UPI {n:1, pending:0, approved:1, needs_bind:1, has_client:0, stale_n:1, alert_hours:6}`; `payments_ready=true`; `blocker_count=1`.
- **Revenue impact:** Us row ka plan activate nahi; `paid_today` 0 rehta.
- **Root cause:** Guest/unbound approve path requires Bind then Re-Approve; owner nahi kiya.
- **Exact failure point:** `/app/admin#sec-upi-selfserve`
- **What should happen:** Bind marketing client id → Re-Approve → bank confirm.
- **What actually happens:** 1 approved row, `client_id` empty, ≥6h stale.
- **Fix:** Owner Bind/Re-Approve. ENG must not fabricate paid.
- **Files:** `app/platform/upi_payments.py` `list_actionable`, `app/api/activation.py` `_upi_pending_unactioned`
- **Validation:** `list_actionable` n=0 after bind+activate **or** reject; then `paid_today` only if bank credit real.
- **Path unlocked:** That one claim → possible activation (still needs bank truth).

### Rank 3 — P0 — Bank-credit confirm missing (canonical rail)
- **Mistake:** Bind/Approve ko paid samajh lena.
- **Evidence:** VERIFIED design — Stripe/Razorpay removed; `PROVIDER_VERIFIED` unreachable; `payment_verification_method = owner_confirmed_upi`.
- **Revenue impact:** Ledger `paid_today` tabhi badhega jab owner bank me credit dekhe.
- **Root cause:** Policy (ADR #243), not a bug.
- **Exact failure point:** Owner bank app + admin confirm.
- **Fix:** Owner confirm. Do not auto-activate beyond scoped allowlist (`UPI_AUTO_ACTIVATE=1` live but scoped — do not flip).
- **Files:** `app/platform/upi_payments.py`, `app/billing/paid_activations.py`
- **Validation:** Invoice + `paid_today>=1` after real credit.
- **Path unlocked:** Honest MRR increment.

### Rank 4 — P0 — origin/main undeployed vs live SHA
- **Mistake:** Treating merged PRs as live revenue code.
- **Evidence:** VERIFIED — `/health.version=91958c23`; VPS HEAD `91958c23feac5aa09d85ccf7dd3a3a62c981f119`; 5/5 app images `:91958c23` zero skew; `origin/main=920a3e62` = #366 squash. Undeployed: `c35edb4d` (#364 docs), `56ff46a9` (#365 funnel), `920a3e62` (#366 next42).
- **Revenue impact:** #365 inbox-wiring / renewal-guard **live pe nahi**; yeh branch ke patches bhi tab tak dead jab tak owner `deploy_vps.sh` na chalae.
- **Root cause:** Manual deploy; CI `DEPLOY_ENABLED` unset.
- **Exact failure point:** Operator deploy, not git merge.
- **Fix:** Owner deploy `920a3e62` **or** this P0 branch after merge — `docs/gtm/OWNER_DEPLOY_920a3e62.md`. This session did **not** deploy.
- **Files:** `scripts/deploy_vps.sh`
- **Validation:** `/health.version` matches deployed SHA; 5/5 pin; VLK=0.
- **Path unlocked:** Code remediations actually reach production.

### Rank 5 — P0 — #365 Hot Queue data source was NOT_CONNECTED
- **Mistake:** `hot_queue_candidates` + `calling_flagged` likhe, `/app/inbox` `reply_agent.hot_queue()` (drafts) padhta raha.
- **Evidence:** VERIFIED in `origin/main` / this branch — grep callers of `hot_queue_candidates` = definition only (before this fix). Inbox uses `GET /api/growth/reply/hot-queue` → `reply_agent.hot_queue`.
- **Revenue impact:** Interested prospects jinke paas draft row nahi, owner queue me gayab.
- **Root cause:** #365 added a parallel list, never merged into the live card builder.
- **Exact failure point:** `reply_agent.hot_queue` after paychase append.
- **What this session did:** synthetic `callflag:<id>` cards + Done/Park. Tests in `tests/test_revenue_funnel_p0_20260815.py`.
- **Fix status:** CODE on `cursor/revenue-blocker-p0` — **NOT live** until deploy.
- **Files:** `app/platform/reply_agent.py`, `app/platform/auto_outreach.py`
- **Validation:** pytest calling_flagged surfaces + Done hides.
- **Path unlocked:** Owner sees calling-flagged people in the same Hot Queue tab.

### Rank 6 — P1 — #365 unguarded duplicate renewal (celery-dead, in-process-spam)
- **Mistake:** `send_renewal_reminders()` in-process loop me **har tick**; celery beat me job nahi; `DUNNING_ENGINE=1` pe `run_due._renewal_reminders` already emails.
- **Evidence:** VERIFIED code on `origin/main`; live `RUN_IN_PROCESS_SCHEDULER=0` so path currently DEAD in prod (not spamming). Live `DUNNING_ENGINE=1` so content-job dunning already covers renewals.
- **Revenue impact:** If someone sets in-process=1 later → Jiya double-email / tick storm. If they deploy #365 as-was onto in-process, retention spam.
- **Fix this session:** skip when `_enabled()` (dunning on); day-key `_last_ran["renewal_reminders"]`; register `RENEWAL_REMINDER_ENABLED`. **Did not** add a new STAFF_JOB (parity registry blast).
- **Files:** `app/billing/dunning.py`, `app/platform/team_scheduler.py`, `app/api/automation_flags.py`
- **Validation:** tests skip-when-dunning + day-key source assert.
- **Path unlocked:** Safe deploy of #365 without retention spam.

### Rank 7 — P1 — `REPLY_AUTO_SEND=1` vs HARD_OFF default mismatch
- **Mistake:** Manifest says `REPLY_AUTO_SEND_HARD_OFF` default ON; `_flag()` treats unset as False, so `REPLY_AUTO_SEND=1` + HARD_OFF UNSET = auto-mail armed.
- **Evidence:** VERIFIED live `REPLY_AUTO_SEND=1`. HARD_OFF printenv this session: PARTIAL (dedicated probe quoting failed; not re-proven). Code path VERIFIED in `reply_agent._reply_auto_send_enabled`.
- **Revenue / ban impact:** Known-prospect auto-reply (not cold WA). Still outbound. Fail-closed default missing.
- **Fix this session:** HARD_OFF env default `"1"` (unset = blocked). Owner must set `=0` to arm after deploy.
- **Files:** `app/platform/reply_agent.py`
- **Validation:** `test_hard_off_defaults_on_when_unset`
- **Do not:** flip prod `.env` from this session.

### Rank 8 — P1 — first_paid_delivery WARN (Jiya fulfilment)
- **Mistake:** Survival probe still WARNs — paid customer delivery not “complete”.
- **Evidence:** VERIFIED SSH `WARNS first_paid_delivery`. Paid customers count includes Jiya. Exact % NOT dumped (no PII).
- **Revenue impact:** Churn / no-referral; not today's 0 paid.
- **Fix:** Owner/Jiya delivery review — not a fake metric. Do not weaken SLA probe.
- **Files:** `app/api/activation.py` `_first_paid_delivery`
- **Validation:** WARN clears when deliverable_completion real.

### Rank 9 — P2 — 31 STAFF exist; revenue work is drafts + pulses, not closes
- **Mistake:** Agent UI/workforce ≠ money.
- **Evidence:** VERIFIED `EVENTS_N=500` cap; `reply_triage:7` / 24h; `email_sent:9`; `growth_pulse:26`; `task_assigned:186`. No `paid` events. DSH worker runs fail `cancellation_store_unavailable` (ok:False) — NOT generating revenue.
- **Revenue impact:** Automation illusion if counted as GTM.
- **Fix:** Keep STAFF as ops; owner closes Hot Queue. Do not add 32nd agent.
- **Validation:** `paid_today` still the scoreboard.

### Rank 10 — P2 — Capacity / DLQ / DSH noise mistaken for money blockers
- **Mistake:** Heavy CPU / `dlq:dead` / DSH cancel store ko paid=0 ka cause banana.
- **Evidence:** VERIFIED `dlq:dead=24` trainer `TimeLimitExceeded` (do not flush); celery/failed_tasks=0; heavy CPU 0.17% at 08:08Z (app 103% during our docker-exec import — transient); DSH allowlist csv_n=29 not `*`; `DSH_RUNTIME_ENABLED=1` / shadow 0; Kavya local plan `upi_proposal_status=403`.
- **Revenue impact:** None direct. Onboard→heavy still NO-GO.
- **Fix:** Observe. Do not raise `WEB_CONCURRENCY`. Do not arm `CELERY_ONBOARD_QUEUE`.
- **Validation:** `/` 200 at 1 concurrent; prior loadtest 429 at 5.

---

## 3. ADDITIONAL ISSUES

| Domain | Issue | Label |
|---|---|---|
| Deploy | `leadgen_dsh_worker` image `leadgen-dsh-worker:fb3d0bc2` vs app `91958c23` | VERIFIED (expected different image lineage) |
| Flags | Live hub/dunning/UPI_AUTO/DSH_RUNTIME=1 vs some docs saying OFF | VERIFIED observe, do not flip |
| Flags | `GSC_ENABLED` UNSET, `HARNESS_SESSION_EVENTS` UNSET, cold WA=0 | VERIFIED never-arm |
| Flags | `RENEWAL_REMINDER_ENABLED` UNSET (code default ON) but path dead on celery | VERIFIED |
| Flags | `MULTI_CHANNEL_FOLLOWUP` UNSET — function does not even read this name | NOT_CONNECTED |
| Email | `EMAIL_ENABLED` UNSET; autopilot/outreach still 1 | PARTIAL |
| Scheduler | `RUN_IN_PROCESS_SCHEDULER=0` on app; workers hardcoded 0 | VERIFIED |
| Reply | `REPLY_AUTO_SEND=1` | VERIFIED |
| DSH | Local supply-chain EXIT 0 commit `47f94385`; Kavya MCP heartbeat 200 / gtm_ops_ready 200 / UPI 403 | VERIFIED LOCAL-ONLY |
| DSH | Prod `run_dsh_workforce` cancelled `cancellation_store_unavailable` | PARTIAL (not a paid blocker; do not allowlist `*`) |
| Voice | FROZEN; `VOICE_LAUNCH_KILL=0`; Vobiz get_balance ConnectTimeout in worker logs | PARTIAL (not GTM-1) |
| Funnel pages | Burst TLS reset earlier; delayed re-probe `/pricing` `/start` `/privacy` `/` all 200 | VERIFIED |
| Boss | Harness real-start owner-only; dry-run previously EXIT 0 | NOT_TESTED this session |
| GSC / ads | Phase 1 gated until 2nd paid | DISABLED by policy |

---

## 4. BROKEN / DISABLED / NOT_CONNECTED TOOLS

| Tool | State | Note |
|---|---|---|
| Manual UPI rail | VERIFIED | Only payment rail |
| Stripe / Razorpay | DISABLED | Removed by design |
| Hot Queue ntfy | PARTIAL | Creds SET, flag 1; send success today NOT_TESTED (no log hit in app tail) |
| IMAP reply_triage | VERIFIED | Beat fired 13:20 IST, job ok True |
| Email outreach | VERIFIED running | `AUTO_EMAIL_OUTREACH=1`, `email_sent:9` in 24h events |
| Cold WhatsApp auto | DISABLED | `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` |
| `hot_queue_candidates`→inbox | BROKEN on live 91958c23; **fixed on this branch** | NOT_CONNECTED until deploy |
| Independent renewal sender | DEAD on celery live; would DUPLICATE if in-process | neutralized on this branch |
| GSC | DISABLED | UNSET, no creds |
| HARNESS_SESSION_EVENTS | DISABLED | UNSET — do not arm |
| OmniRoute MCP (Cursor) | UNKNOWN | server discovery error this session |
| Google Sheets | NOT_CONNECTED | no credentials file |
| HubSpot | NOT_CONNECTED | API key not configured |
| SearXNG / ntfy containers | VERIFIED running | ntfy 21MB |

---

## 5. PLUGIN / INTEGRATION HEALTH

**A — Working E2E (VERIFIED or PARTIAL with live traffic):** Postgres via PgBouncer, Redis, Celery beat+worker, Caddy TLS, UPI store, paid_activations ledger, ntfy process, WAHA container, Postiz/Temporal containers, DSH worker process (armed, runs failing closed).

**B — Configured, gated, or incomplete:** Dunning (ON, recovery emails possible), UPI auto-activate (ON but allowlist-scoped), Coordination Hub (ON — not a 32nd STAFF), GSC (UNSET), daily video flags (not re-probed), Creative OS (policy OFF).

**C — Broken / unused / duplicate:** #365 `hot_queue_candidates` duplicate of live `reply_agent.hot_queue` (now merged in this branch); `send_renewal_reminders` duplicate of `dunning._renewal_reminders`; Stripe webhook fail-closed stub.

**D — Dead / obsolete:** Razorpay, Exotel, paid STT/TTS.

---

## 6. AI AGENT HEALTH (31 STAFF — last 24h events, capped 500)

Live `team.recent_events(limit=500, hours=24)` — **execution counts, not job descriptions**.

Highest volume: `rohan:95`, `flow_cron:79`, `manager:36`, `kavya:26`, `growth:26`, `isha:11`, then hermes/swara/arjun/nikhil/tara/neha/watchdog/aryan/sales_autopilot/reply_triage/product_one_health (~7–9).

Actions: `task_assigned:186`, `email_followup:73`, `growth_pulse:26`, `hier_step:14`, `email_sent:9`.

**Revenue close actions: none in this sample.** Agents are pulsing/drafting. Swara events exist (calling live under compliance) — voice code still FROZEN for ENG.

DSH Kavya: local governed MCP OK; prod child runs cancelled on missing cancellation store — **not** closing deals.

Boss Desktop spawn: owner-only. NOT_TESTED this session.

---

## 7. FUNNEL MAP (GREEN / AMBER / RED)

```
Lead magnet / /audit /demo     GREEN  HTTP 200
Pricing /start                 GREEN  re-probe 200 (earlier burst TLS PARTIAL)
Outreach email                 GREEN  AUTO_EMAIL_OUTREACH=1, sends in events
Reply triage drafts            GREEN  hourly beat succeeded
Hot Queue owner action         RED    owner token + 15–30 min missing
1-click WA human send          AMBER  path exists; cold auto OFF (correct)
Appointment/demo               AMBER  owner-driven
Offer /pricing                 GREEN
Payment submit UPI             GREEN  payments_ready=true
Owner Bind + Re-Approve        RED    1 stale approved-unbound
Bank confirm                   RED    none today
Provisioning / onboard         AMBER  AUTO_ONBOARD=1; queue UNSET (keep)
Delivery (Jiya)                AMBER  first_paid_delivery WARN
Retention dunning              AMBER  DUNNING_ENGINE=1 live; observe
Ledger paid_today              GREEN  honest 0
```

**First break:** Hot Queue owner action.
**Second break:** UPI bind/activate + bank confirm.
**Third break (code, undeployed):** calling_flagged not in inbox — patched here, needs deploy.

---

## 8. TOP P0 FIXES (max 5; this session shipped 3 CODE-safe)

1. **Owner inbox + UPI + bank** — cannot code-fake. Checklist already exists.
2. **Wire `calling_flagged` into `reply_agent.hot_queue`** — DONE on branch (tests).
3. **Neutralize #365 duplicate renewal** — DONE on branch (skip if dunning; day-key).
4. **Fail-closed `REPLY_AUTO_SEND_HARD_OFF` default + register `RENEWAL_REMINDER_ENABLED`** — DONE on branch.
5. **Deploy `origin/main` / this branch** — OWNER only. Runbook: `docs/gtm/OWNER_DEPLOY_920a3e62.md`.

Rollback for code: revert the 3 commits / leave undeployed. Prod stays `91958c23` until owner deploys. Prod rollback tag still `c4fc0087` via `deploy_vps.sh`.

---

## 9. 24-HOUR REVENUE RECOVERY PLAN

**Hour 0–1 (OWNER):** `/app/admin-login` → `/app/inbox` token → max 10 cards.
**Hour 0–1 (OWNER):** Admin UPI queue — Bind the unbound approved row → Re-Approve **only if bank credit real**.
**Hour 1–2 (OWNER):** Confirm bank. Scoreboard = Aaj naye paid.
**Hour 2–4 (OWNER, optional):** Deploy after reading kill-fence runbook — **not required to close today's UPI row** (that code is already live on `91958c23`). Deploy unlocks #365+#366+this P0 branch.
**Hour 4–8 (OWNER, optional):** `python scripts/buzz_start_harness.py --agent Boss` then `@Boss` ≥600s. Does not make paid_today.
**Do not in 24h:** cold WA, GSC without creds, HARNESS_SESSION_EVENTS, `DSH_AGENT_ALLOWLIST=*`, DLQ flush, WEB_CONCURRENCY raise, fake paid, Swara edits.

Success = `paid_today>=1` **or** UPI queue empty after honest reject **plus** ≥1 Hot Queue outcome logged. Anything else is motion.

---

## 10. DEFINITION OF DONE (this audit)

- [x] Live `/health` dual-probe, SHA vs `origin/main` vs VPS images
- [x] Activation named blocker re-probed via SSH `_PROBES`
- [x] `paid_today` ledger 0 honest
- [x] Funnel pages 200
- [x] DSH governed path used (supply-chain + Kavya plan); UPI refused 403
- [x] ≤3 CODE remediations + tests (no deploy, no .env, no fake paid)
- [ ] Owner inbox blitz — remaining
- [ ] Owner UPI bind/bank — remaining
- [ ] Deploy of this branch — remaining
- [ ] `paid_today>=1` — remaining (only real bank credit)

**Overall: WAIT (owner-gated). Technical rail GO. Code P0s ready for next deploy, not live.**
