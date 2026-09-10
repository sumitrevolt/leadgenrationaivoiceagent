# PHASE 0 — BASELINE (24×7 headless migration)

**Compiled:** 2026-09-10 · **By:** team-lead (Qi) · **Sources:** architect audit + independent QA verification
**Method:** static code inspection + git commands + one read-only `GET https://leadsgenai.in/health`.
No files were created/changed outside this document. No commit / push / deploy performed.

Evidence labels used: **PRODUCTION-PROVEN** · **CODE-PRESENT** · **TEST-PROVEN** · **LOCAL-ONLY** · **PARTIAL** · **STALE** · **UNKNOWN**.

---

## 1. REPO / DEPLOY BASELINE

| Field | Value | Label |
|---|---|---|
| Local branch | `main` | — |
| Local HEAD | `d0183bf1` — *fix(smartflo): keep playback alive and persist cleanup metering*, 2026-09-08 21:49 IST | — |
| **Deployed commit (LIVE)** | `0b848b345dccfa4b59b556e2902252b12ae71136` — *fix(voice): Smartflo call-drop root cause — TTS silent failure + stream_sid validation*, 2026-09-09 14:01 IST | PRODUCTION-PROVEN |
| LIVE `/health` (2026-09-10 09:22Z, single curl) | `status=healthy`, `environment=production`, `uptime=8h34m44s`, `dsh_runtime_enabled=true`, `dsh_shadow_enabled=true`, `dsh_allowlist=["jiya_makeover"]` | PRODUCTION-PROVEN |
| Working tree | 14 changes — see §7 | LOCAL-ONLY |

### 🔴 LINEAGE — the single most important fact of this migration

```
git merge-base d0183bf1 0b848b34            -> 79291e2bb7183a423c9e43db6d0dc7e3c83e514f
git merge-base --is-ancestor 0b848b34 HEAD  -> exit 1   (NOT an ancestor)
git rev-list --count 79291e2b..HEAD         -> 30
git rev-list --count 79291e2b..0b848b34     -> 15
```

**Production and local HEAD have DIVERGED.** Both descend from `79291e2b`, but neither contains the other.

**Consequence:** any branch cut from local HEAD and deployed would **silently revert the 15 prod-only
commits**, including the Smartflo call-drop fix at the prod tip, on a live revenue system. The 30 local
commits are unreleased.

> **Rule for every subsequent phase: base migration work on `0b848b34`, NOT `d0183bf1`.**

### 🔴 STALE DOC vs LIVE

`AGENTS.md:137` (committed, file clean) records:

> `**Prod /health=5919c379** (2026-08-23T07:01Z live probe…)` … `DSH_RUNTIME_ENABLED=0 (runtime/shadow OFF, allowlist empty)`

Live reality: `0b848b34`, `dsh_runtime_enabled=true`, `dsh_shadow_enabled=true`, allowlist `["jiya_makeover"]`.
Ironically `AGENTS.md:138` is itself a "SHA discipline" warning telling agents to re-probe `/health` before
asserting any SHA. **Treat `AGENTS.md` §Current State as STALE until corrected.**

---

## 2. CONTROL PLANE TRUTH — FIVE competing task implementations

| # | Implementation | Storage | States | Label |
|---|---|---|---|---|
| 1 | **DevTask** `app/models/dev_task.py:10` | Postgres `dev_tasks` | 18 (`app/dev_control/service.py:10-28`) | CODE-PRESENT |
| 2 | AgentTask `app/platform/agent_task_queue.py` | Postgres `agent_tasks` | pending/claimed/running/… | CODE-PRESENT |
| 3 | CC ledger `command_center/data/tasks.json` | JSON, **44 tasks** | ad-hoc 7 (CLOSED 12 / RUNNING 12 / SUPERSEDED 8 / BLOCKED 5 / UPDATE 4 / STANDBY 2 / VERIFIED 1) | **LOCAL-ONLY** (gitignored, `.gitignore:347`) |
| 4 | `agent_runtime` `app/platform/agent_runtime.py` | JSON `data/agent_runtime_state.json` | 8 (`TaskStatus:74`) | CODE-PRESENT |
| 5 | Hermes `HERMES_CONTROL_PLANE.md:48` | **none** | BACKLOG→…→FAILED | **DOC-ONLY** |

**Plus a sixth, worse problem:** `command_center/state.js` is **committed in HEAD** and serves a
**frozen hardcoded snapshot** to the dashboard — 9 tasks, every `started`/`last_update` = `2026-09-02`,
messages dated 08-24 and 09-02. So the only task view a UI renders is committed-and-frozen (~8 days
stale), while the live 44-task store is **untracked and unversioned**.

### Capability matrix

| Capability | 1 DevTask | 2 AgentTask | 3 CC ledger | 4 agent_runtime |
|---|---|---|---|---|
| claim | ✅ `claims.py:31`, `claim_next:82` (atomic conditional UPDATE) | ✅ `:197` optimistic `checkout_version` | ❌ | n/a |
| heartbeat | ✅ `claims.py:57` | ❌ (uses `claimed_at`) | ❌ | ✅ `:619` |
| lease + expiry | ✅ `dev_task.py:34-35`, 600 s `claims.py:27` | ✅ `stale_tasks:517`, `reap_stale_leases:750` | ❌ | ⚠️ in-process only `:1010` |
| result write-back | ✅ `dev_tasks.py:291` | ✅ `:302`, `:340` | ⚠️ free-text notes | ✅ |
| stale requeue | ✅ `reconcile.py:56` | ❌ **terminal by design** `:750-765` "NEVER requeues" | ❌ | n/a |
| retry / backoff | ⚠️ counter only, `max_retries=3` `reconcile.py:32,52` — **no delay** | ❌ | ❌ | ✅ `_BACKOFF_BASE_S:117` + DLQ `:114` |
| reconcile-on-start | ❌ **MISSING** — admin POST only `dev_tasks.py:392` | ❌ beat hourly :05, flag-gated `scheduler_config.py:224` | ❌ | ❌ |
| idempotency | ⚠️ unique column `dev_task.py:14` BUT `service._IDEMPOTENCY` is a **process-local dict** `service.py:72` → lost on restart | ✅ Redis fail-closed `agent_runtime.py:197-230` | ❌ | ✅ |
| parent/child + deps | ⚠️ `dependencies` column `dev_task.py:31` stored + serialized `:106,:154` — **no enforcement, no `parent_id`** | ❌ | ❌ (supersede-by-text) | ❌ |
| audit history | ❌ **MISSING** (no event table; grep `DevTaskEvent` = 0) | ⚠️ `_log_event` → `agent_events` | ⚠️ `messages.jsonl` | ⚠️ |

---

## 3. WORKER / BOT / AGENT ROSTER

- **31 specialist agents = REAL CODE** — `app/platform/team.py:48` `STAFF` + `agent_registry.py:171`
  governance table, `CANONICAL_COUNT=31`. Not aspirational.
- **Executable = 12** — `PILOT_AGENTS` frozenset `app/platform/agent_runtime.py:90-108`:
  kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil.
  **Delta vs 31 = 19 non-dispatchable.** Matches ADR-164 "12 / 17 / 2".
- **swara + ananya = RED-lane permanently blocked** (`agent_runtime.py:44`). Note: **swara is FROZEN
  (voice), modification permission NONE** — must remain non-dispatchable.
- **Bots = 9** — `command_center/data/bots.json`: Pilot, hunter, sales, platform, engineering,
  success, guardian, operations, board. `HERMES_CONTROL_PLANE.md:5` "8 department bots" is consistent
  (Pilot = Boss surface).
- **Registry entries with NO code** (do not count as availability): Claude, Verdant, Buzz, Comb,
  FreeBuff, Android. `WORKER_ROSTER.md:24-26` confirms no agent process.

---

## 4. OMNIROUTE + COMBOS

- Canonical code: `app/platform/omniroute_client.py:106` `_TASK_ROUTES` = **12 routes**, referencing all
  **14** `leadsgen combo N` (1–14). Seed: `scripts/seed_omniroute_14combos.py` (14 × 42 providers).
  Contract test: `tests/test_omniroute_canonical_combos.py:22-49`.
- **3-way naming conflict:**
  1. numeric canonical in code — `leadsgen combo N`;
  2. `config/desktop_apps/combo_distribution.yaml:20+` uses **legacy aliases** (leadgen-free-first,
     hermes-sales, kimi-coding…) which the same test `:6-8` explicitly demotes as *"NOT the routing authority"*;
  3. gateway exports **18**, manifest picks 14 (`yaml:11-14`).
- **⚠️ Owner spec says 14 combos; `docs/OMNIROUTE_12_COMBOS_HARNESS_RUNBOOK.md` says 12.** Reconciled:
  14 combo *definitions* exist, only 12 *task routes* are mapped. Not a contradiction — but the doc title
  is misleading and must be renamed.
- **Health fields:** latency ✅ (`omniroute_client.py:80,482`). **last_success / failure_count /
  per-combo circuit-breaker / quota / cost = ❌ MISSING.** Only a generic
  `app/infrastructure/circuit_breaker.py` exists (Vobiz / SMTP / Maps — not combo-scoped).
- Declared source-of-truth `.omniroute-cutover/combos.json` is **ABSENT** (gitignored, `.gitignore:344`)
  → combo registry is unreviewable locally.
- Container `leadgen_omniroute` @ `127.0.0.1:20128`; double-gated `OMNIROUTE_ENABLED` + `OMNIROUTE_API_KEY`,
  **INERT by default** (`:176-199`).

---

## 5. DESKTOP DEPENDENCIES (severity order)

| # | Severity | Dependency |
|---|---|---|
| 1 | **BLOCKER** | `coordination_hub_auth.py:23` `_KNOWN_TOOLS` lacks openclaw / workbuddy / codex; `:169` rejects ⇒ headless bots can never reach `buzzlock_enrolled: true`. **Owner-gated code change.** |
| 2 | **BLOCKER** | `combo_distribution.yaml:72,82`: openclaw + verdant = `project_only` ⇒ 2 of 5 combo lanes cannot go headless as-is. |
| 3 | HIGH | Buzz / Comb: `BUZZ_AUTH_TAG` minted **only inside the Desktop process** (`AGENTS.md:122`); harness not started. |
| 4 | HIGH | Hermes Desktop = owner cockpit (54 MCP tools, `HERMES_CONTROL_PLANE.md:171`) **and the sole Telegram `getUpdates` consumer** (`:65`). Closed ⇒ no owner Telegram ingress. Acceptable under "owner-manual only" — but the ingress must be re-homed or declared egress-only. |
| 5 | MED | Hermes GUI child-backend exits(1) ~3.5 min (root-cause doc §2.2); mitigated by the 9119 machine backend. |
| 6 | MED | `.venv` missing ⇒ 5 of 6 MCP servers fail. Owner gate. |

---

## 6. AUTOMATION DOMAIN MAP

| Domain | Canonical module | State |
|---|---|---|
| Voice / telephony | `app/telephony/vobiz_stream.py`, `app/voice_agent/free_ai.py` | **PRODUCTION-PROVEN** (compliance-gated) |
| WhatsApp | `app/integrations/whatsapp.py`, `whatsapp_selfhost.py` | **PRODUCTION-PROVEN** (cold/bulk OFF by design) |
| Email | `app/integrations/email_sender.py`, `app/platform/email_warmup.py` | **PRODUCTION-PROVEN** (25/day cap) |
| Video | `app/marketing/video_ad_cycle.py` | **PARTIAL** |
| Social | `app/integrations/postiz.py`, `meta_graph.py`, `app/social_engine/` | **PARTIAL** (own-brand live; customer pages Meta-review blocked) |
| Leadgen | `app/platform/prospector.py`, `lead_harvester.py`, `app/lead_scraper/` | **PARTIAL** (scrape-blocked → manual CSV) |
| CRM / follow-up | `app/platform/crm_sync.py`, `app/integrations/hubspot.py` | **PRODUCTION-PROVEN** |
| Billing | `app/marketing/packages.py`, `app/billing/{subscription,gst_invoice}.py` | **PRODUCTION-PROVEN** (manual UPI only) |
| Flow automation | `app/automation/` | **CODE-PRESENT, UNVERIFIED** |

---

## 7. WORKING TREE (14 changes)

**Modified (5):** `HERMES_CONTROL_PLANE.md` · `docs/HERMES_DESKTOP_ROOT_CAUSE_2026-09-03.md` ·
`docs/context/SESSION_HANDOFF.md` · `docs/coordination/desktop_registry.json` · `progress.md`

**Untracked (9):** `.agents/` · `new-clone/` · `app/utils/owner_feed.py` · `tests/test_owner_feed.py` ·
`cleanup_check.ps1` · `getprocs.ps1` · `docs/context/{COORDINATION_BROADCAST,OWNER_TELEGRAM_FEED_DESIGN,WORKER_ROSTER}.md`

---

## 8. 🔴 TRUTH GATE — sources BANNED from any dashboard tile

`data/workforce_live_status.json` (gitignored, untracked, ts 2026-09-10T02:05:20Z, cycle 709) is
**self-refuting**:

```
status = RUNNING_24_7_PARALLEL     actions_today = 592
active_workers = 0                 working_members = 0        active_members = 0
task_execution_verified = false    evidence_kind = inference_probe_only
desktop_apps: hermes / claude / workbuddy / openclaw / verdant / buzz  -> 6/6 "UNVERIFIED (no desktop execution probe)"
```

**Verdict: no dashboard may render this as live worker activity.** Any "592 actions today" tile is
fabricated activity. It must be labelled probe-only inference or removed.

Also banned until rewired: `command_center/state.js` (frozen 08-24 / 09-02 snapshot).

---

## 9. TOP GAPS (Phase 2+)

1. **One task truth** → `app/dev_control/reconcile.py` (startup reconcile + real backoff + `dev_task_events`
   audit); retire CC ledger + `state.js`.
2. **Enrolment allowlist** → `app/platform/coordination_hub_auth.py:23` *(owner approval required)*.
3. **Per-combo health table** → `app/platform/omniroute_client.py` (last_success / failure_count / quota /
   latency / cost / breaker) — prerequisite for 24×7 routing.
4. **Kill view drift** → `command_center/state.js`.
5. **Truth gate** → producer of `data/workforce_live_status.json`.

---

## 10. RISKS / BLOCKERS

- **Prod ≠ HEAD** (+30 / +15 divergent). Migration must base off `0b848b34`.
- ~~**Orchestration is INERT today**: ... Today's "24×7" = Celery beat only.~~
  **🔴 CORRECTED 2026-09-10 (team-lead verified with Bash):** that statement was **WRONG**. See §12.
  `AGENT_RUNTIME`, `AGENT_TASK_LEASE_REAP`, `OMNIROUTE_ENABLED` **are** unset (agent orchestration genuinely
  inert) — **but job scheduling is NOT**: `docker-compose.vps.yml:59` sets
  `RUN_IN_PROCESS_SCHEDULER: ${RUN_IN_PROCESS_SCHEDULER:-1}` (default **ON**), while `worker`, `worker-heavy`,
  `worker-video` and `scheduler` are all `profiles: ["celery"]` (`:318, 383, 436, 540`) → **off unless
  `--profile celery`**. So **prod's jobs run in the in-process asyncio scheduler inside the app container**,
  and the ~55 `staff-*` Celery beat entries are **DORMANT**. Anyone reading `app/worker.py` alone will
  wrongly conclude that Celery beat drives production.
- **Competing orchestrator**: `HERMES_CONTROL_PLANE.md` specifies a Dsh/Cordis plugin orchestrator with its
  own Redis event bus + 8 bots. Doc-only today, but it is a second control-plane design — must be
  explicitly subordinated or deleted.
- **Owner gates (hard, not ours to flip):** combo-agent enrolment · agent rollout 12→31 · `.venv` rebuild ·
  DSH arm · any commit / push / deploy.
- **Compliance — never weaken:** DND fail-closed · TRAI 09:00–19:00 window · AI-disclosure · consent ledger ·
  cold-WhatsApp ban-safety · manual-UPI billing truth · `VOICE_LAUNCH_KILL` deploy gate · tenant isolation.

---

## 11. AUTOMATION HEALTH INVENTORY (added 2026-09-10)

> Source: QA static inspection of local HEAD `d0183bf1`. **Could NOT diff against deployed `0b848b34`**
> (agent tooling failure) — "same in both" is **UNVERIFIED** for every row.

### 🎯 The Automation Health module ALREADY EXISTS — do not rebuild it

`app/platform/automation_health.py` is a mature Cronitor-style dead-man:
`record_run()` `:334` → `data/job_runs.jsonl` + `data/job_heartbeats.json` · `EXPECTED_GAP_MIN` `:56`
(~55 jobs) · `health()` `:698` emits per-job `last_run / last_ok / duration_s / status / overdue` ·
`stale_outputs()` `:173` watches **OUTPUT**, not just runs · `wiring_gaps()` `:575` · `run_watch()` `:904`
wired to an hourly watchdog (`infra_handler.py:13`, gated `AUTOMATION_HEALTH_ALERTS`).
`scheduler_config.py:333 list_jobs()` already merges registry + toggle + health → **that is the honest merge point.**

**It is consumed today** by `agent_status.py:115`, `api/growth.py:899`, `office_briefing.py:157/448`,
`infra_handler.py:125`, `code_upgrader.py:145`, `sprint_actions.py:235`, `product_one_delivery.py:2457`.

### Two gates decide what actually fires
- `app/worker.py:884` — `ENABLE_LEGACY_BEAT` default **"0"** → **deletes every beat key not starting
  `staff-`**. The 15 legacy jobs (lead-scrape 06:00, process-call-queue :00, crm-sync */15, reports,
  brain-training, vertex-*) are **declared-then-removed**.
- `docker-compose.vps.yml` — `scheduler`/`worker*` are `profiles: ["celery"]` (`:318, 383, 436, 540`) →
  **off by default**; `RUN_IN_PROCESS_SCHEDULER` defaults to **1** (`:59`).
  ⇒ **Effective prod schedule ≠ the literal beat dict.** Any tile must render the *post-filter, effective* schedule.

### Evidence gaps (honest)
| Signal | Status |
|---|---|
| last-run | **RECORDED** — `automation_health.record_run():334` → `data/job_runs.jsonl`, snapshot `data/job_heartbeats.json`. Single choke point `team_scheduler._run_job_direct:306` covers in-process **and** Celery. |
| **next-run** | **NOT RECORDED ANYWHERE** — no table/key/field. `health()` re-derives due-ness from `EXPECTED_GAP_MIN`. Any "next run" tile must be **computed from the crontab**, not read. |
| duration / failure reason / overdue | **REAL on day one** (`error_class`, `error_message`, overdue at `:797`). |
| 15 legacy + 3 `content_os.*` jobs | **NOT RECORDED** — absent from `EXPECTED_GAP_MIN`, so they **cannot ever appear as overdue**. |
| local execution evidence | **NONE** — `data/job_runs.jsonl` and `data/job_heartbeats.json` do not exist locally (verified). Prod filesystem not readable from here. |

### Corrections to the PHASE 0 audit
- `reap_stale_leases` is in **`app/platform/agent_task_queue.py:750`**, *not* `agent_runtime.py` — and it **IS
  consumed**: `team_scheduler.py:1504` calls it with `dry_run=False`.
- DLQ push is `agent_runtime.py:675 _dlq_push` (bounded 500); DLQ path line is `:116`, not `:114`.

### The 21 WORKING_BUT_INERT — split by *why* they are inert
- **Has a real scheduler (would fire if armed):** sales-autopilot — `SALES_AUTOPILOT_ENABLED`
  (`automation_flags.py:470`) + `SALES_AUTOPILOT_WHATSAPP_ENABLED` (:471), beat `staff-sales-autopilot-hourly`
  (`worker.py:750`); harness audit/replay + content-hash binding — `HARNESS_SESSION_EVENTS` (:227);
  OTel tracing — `ENABLE_OTEL` (:104); onboarding — `ONBOARDING_PIPELINE` (:137).
- **No scheduler — a flag alone would NOT fire them** (missing human/channel, not missing config):
  Hot Queue, `/app/inbox`, Inbox, Boss governed release (agents UNARMED 30/30), combo router,
  LinkedIn (Postiz channel not connected), web push VAPID.
- **None of the 21** have their arm flag set in `docker-compose.vps.yml`.

### Overdue-detection feasibility
**YES** for ~55 jobs with an `EXPECTED_GAP_MIN` entry · **NO** for the 15 legacy + 3 `content_os` jobs.
**Smallest fix:** add the missing 18 to `EXPECTED_GAP_MIN` (`automation_health.py:56`) — **no schema change**,
the store already exists.

### TOP 3 changes that would make Automation Health honest
1. `app/platform/automation_health.py:56` — register the 18 unregistered jobs so overdue covers ~73/73, not ~55/73.
2. `app/worker.py:884` — render the **effective** schedule (post-`ENABLE_LEGACY_BEAT` filter, dormant when
   `--profile celery` is off), not the literal dict.
3. `app/platform/scheduler_config.py:333` — wire the tile to `list_jobs()` and **compute** `next_run` from
   the crontab, since no next-run is stored anywhere.

---

## 12. STATUS

- [x] PHASE 0 — baseline + independent verification
- [ ] PHASE 0b — feature inventory / no-loss preservation matrix *(in progress)*
- [ ] PHASE 1 — architecture freeze
- [ ] PHASE 2–7 — control plane, headless migration, Owner Command Center, E2E, harden, handoff
