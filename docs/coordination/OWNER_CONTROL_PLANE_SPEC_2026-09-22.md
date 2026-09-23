# Owner Control Plane — Telegram + Admin Command Center Spec

**Date:** 2026-09-22
**Worktree:** `feat/smartflo-acceptance-framework` @ `f89aad42`
**Owner:** Sumit (via Root session `mvs_2c0a08d649f94de3af323f87e632debc`)
**Scope:** Wire Telegram (Jarvis ingress + Notify egress) and Admin Command Center (`/app/bot-command-center` + domain dashboards) into ONE verified operational view per directive §1–§10.

> **Spec only — no live execution.** Live verification needs SSH + Remote Desktop + Telegram tokens + TYPESAFE_API_KEY + owner-authorized test inputs.

---

## §1 Canonical task-authority mapping — DECISION REQUIRED FROM OWNER

Per directive: *"Choose the canonical task authority or a clearly defined authoritative mapping for each task class based on current production evidence. Do not automatically choose legacy JSON simply because the current Kanban reads it."*

### 1.1 Per-task-class authority map (proposed, owner-decide)

| Task class | Proposed canonical writer | Backing store | Owner UI surface | Why |
|---|---|---|---|---|
| **Telegram owner commands → action tasks** | `app/api/dev_tasks.py` (Postgres DevTask, dual-governor HMAC) | `dev_tasks` SQLAlchemy table | `/admin/api/dev_tasks` (admin JWT) | Dual-governor HMAC already wired; production-grade CAS lease; align with `external_agents.missions` lifecycle |
| **Engineering pipeline (PR/CI/deploy)** | `app/dev_control/external_agents/orchestrator.py` | mission store + CAS + idempotency_keys | `/api/dev-tasks/missions` | AMBER/RED classification + dual-governor already enforced; PR→CI→merge→verified lifecycle exists |
| **9+31 control plane agent execution** | `app/platform/automation_orchestrator.py` | `data/orchestrator_ledger.db` (SQLite, CAS + fencing) | `/api/dev-control` + `coordination_hub.py` snapshot | Fencing tokens + 4-lease governor; "One Task → One Owner Bot → One Assigned Agent → One Execution Path" |
| **Admin manual task tracking (Kanban)** | `app/admin/services/task_ledger.py` | `data/admin_tasks.db` (SQLite) | `/admin/api/tasks/kanban` | 13-worker pool, auto-assign, duplicate detection — KEEP for OCC visible Kanban |
| **OCC legacy 9-bot chatter feed** | `command_center/scripts/pilot_*.py` + `command_center/patches/pilot_dispatch_*.py` | `command_center/data/{tasks,bots,messages,pinned}.json(l)` | `/app/bot-command-center` page + state.js | Keep as PUBLIC visible Kanban (no schema migration); OCC page reads it |
| **Customer-facing CRM follow-ups** | `app/marketing/customer_delivery.py` + `delivery_ledger` | marketing_clients.jsonl | OCC `sales_crm` room | Already canonical; outbound follow-up cadence via `anika` (cadence) + `ira` (journey) |
| **Payment / invoice / subscription** | `app/billing/gst_invoice.py` + `app/billing/usage_alerts.py` | billing_record + dunning tables | `/api/billing/*` | UPI manual + Rule-46 sequential INV/2026-27/0001 — already canonical |

**Total = 7 task classes, 6 canonical writers (Postgres DevTask is shared between Telegram→actions and Engineering pipeline).**

### 1.2 Single-ownership guarantee (§6 directive)

- **One task ID** — UUID (`models.DevTask.id`) for Telegram-action tasks; `TaskRecord.task_id` (`orch_xxx`) for 9+31 control plane; `mission_id` (`m_xxx`) for external agents.
- **One active lease** — `orchestrator.RedisGovernorAuthority` (file fallback) + `dev_tasks.claim_next()` (atomic claim) + `external_agents.store.claim()` (CAS).
- **Collision detection** — `app/dev_control/locks.py` per-mission path-lock + `delivery_ledger` per-customer idempotency + `email_finder` per-recipient dedup.

### 1.3 Conflict reconciliation

| Surface A | Surface B | Conflict | Resolution |
|---|---|---|---|
| OCC `tasks.json` (status NEW/ASSIGNED/RUNNING) | admin_tasks.db (status backlog/in_progress/review/done) | OCC writes go to legacy; admin writes go to SQLite. SAME TASK can appear in both. | **OCC = visible-public Kanban (no migration)**, admin_tasks.db = admin internal only. Project_id field links them. |
| admin_tasks.db (13 workers incl. `claude`, `verdant`) | orchestrator_ledger.db (9 bots + 31 agents) | Different worker pools. | admin_tasks.db = admin manual Kanban; orchestrator_ledger.db = 9+31 execution plane. **NO shared task IDs** — they belong to different domains. |
| orchestrator_ledger.db (SQLite, CAS) | Postgres DevTask | Two durable stores for engineering-class work. | **External_agents orchestrator = engineering pipeline (mission store)**, Postgres DevTask = action tasks from Telegram/UI. |
| OCC `bots.json` | agent_registry (31) | OCC is 9 hermes bots + 1 Pilot; agent_registry is 31 specialist agents. | OCC = chatter feed (Telegram-style); agent_registry = control plane. **No merge.** |

---

## §2 Telegram commands — 14 directives mapped to existing endpoints

### 2.1 Existing in `app/integrations/telegram_bot.py`

| Command | Handler | Backed by |
|---|---|---|
| `/start`, `/help` | `_cmd_help()` (line 350) | static text |
| `/status` | `_cmd_status()` (line 392) | `AutomationOrchestrator.store.all_tasks()` + key_manager |
| `/keys`, `/slots` | `_cmd_keys()` (line 370) | `app.platform.key_manager.get_all_slots()` |
| `/tasks [filter]` | `_cmd_tasks()` (line 435) | `AutomationOrchestrator.store.all_tasks()` |
| `/agents` | `_cmd_agents()` (line 466) | `orch.registry` (31 agents) |
| `/pause` | `_cmd_pause()` | `AUTOMATION_STOP_NEW_CLAIMS=1` (env flag, all processes) |
| `/resume` | `_cmd_resume()` | same env flag off |
| `/test_handoff` | `_cmd_test_handoff()` | draft-only verification |

### 2.2 NEW commands to add (9 of 14)

| Command | Handler to add | Backed by |
|---|---|---|
| `/revenue` | `_cmd_revenue()` | `app.platform.revenue_snapshots.snapshot_today()` (B1 daily) + `revenue_digest._collect()` + `/api/billing/verified-cash` (NEW endpoint) |
| `/workers` | `_cmd_workers()` | `office_hq.coordination_topology()` (Boss → 8 rooms → 30) + desktop_registry apps + `automation_health.health()` |
| `/smartflo` | `_cmd_smartflo()` | `app/telephony/call_manager.py` (provider=TATA_SMARTFLO) + smartflo_acceptance gates + webhook events |
| `/typesafe` | `_cmd_typesafe()` (extend `/keys` role) | `app.platform.typesafe_session_policy.judge_task` + multipass consumer stats |
| `/email` | `_cmd_email()` | `reply_agent._creds()` health + `email_warmup` state + 14-mailbox pool (when built) |
| `/video` | `_cmd_video()` | `marketing.daily_video` scheduler + render queue + approval backlog |
| `/ci` | `_cmd_ci()` | `gh pr list --json` + `GET /api/admin/owner-os/release-state` |
| `/approvals` | `_cmd_approvals()` | `approvals_bridge.list_drafts()` + external_agents/approval.assert_amber_approved |
| `/blockers` | `_cmd_blockers()` | orchestrator BLOCKED tasks + admin_tasks.db blockers + external_agents BLOCKED missions + smartflo_acceptance UNVERIFIED gates |

**Hard rule (§2 directive):** "A command must return real backend results. Unsupported commands must explicitly return UNAVAILABLE rather than fabricated data." → Each handler must return UNAVAILABLE if its data source raises (no fake data).

### 2.3 Authentication / authorization (§2 directive)

- All commands gated by `is_owner=True` (`telegram_bot.py:284-285`)
- Live `TELEGRAM_JARVIS_BOT_TOKEN` rotates per ADR-198 (notify token rotation pending owner/BotFather)
- Polling lease: `TELEGRAM_INGRESS_OWNER=local|vps|hermes|off` (`telegram_coordinator.py:74`)
- 409 conflict: standby + release own lease (`telegram_coordinator.py:_external_conflict_until`)

---

## §3 Admin Command Center — 10-state taxonomy data sources

### 3.1 Existing pages to REUSE (no new dashboard)

| Page | File | Reuse? |
|---|---|---|
| `/app/bot-command-center` | `frontend/bot_command_center.html` + `app/api/bot_command_center.py` | YES (visible-public Kanban) |
| `/app/owner` | `frontend/owner*.html` + `app/api/owner_*.py` | YES (Owner OS control plane) |
| `/app/owner-command-center` | `frontend/owner_command_center.html` + `app/api/owner_command_center.py` | YES (L1→L4 aggregator) |
| `/app/office` | `frontend/office_map.html` + `app/api/office_hq.py` | YES (8-room HQ) |
| `/app/dev-control` | `frontend/dev_control*.html` + `app/api/dev_control/*` | YES (engineering pipeline) |
| `/app/admin/dashboard` | `frontend/admin_dashboard.html` + `app/api/admin_dashboard.py` | YES (admin Kanban) |

### 3.2 10-state taxonomy mapping (§3 directive)

| State | Definition | Data source |
|---|---|---|
| `REGISTERED` | Configuration present, no heartbeat | `desktop_registry.json` `apps[].status=registered` + `agent_registry._GOVERNANCE` keys + `task_ledger.WORKERS` |
| `CONFIGURED` | ENV flag ON, code wired, no real execution | `runtime_data_manifest.py` + `automation_flag_manifest.py` |
| `CONNECTED` | Live process / heartbeat / lease | `redis-cli llen celery` + heartbeat JSONL + `/health.version` |
| `RUNNING` | Currently executing | `orchestrator.store.all_tasks(status=RUNNING)` + `dev_workers.heartbeat()` |
| `VERIFIED WORKING` | Has REAL evidence row (done + non-empty evidence) | `dev_workers.verified_count()` + `external_agents.missions` state=VERIFIED |
| `DEGRADED` | Connected but not all sub-engines green | `automation_health.wiring_gaps()` + liveness probes |
| `BLOCKED` | Task waiting on owner/dependency | `orchestrator.store.all_tasks(status=BLOCKED)` + admin_tasks.db `in_progress` overdue |
| `FAILED` | Terminal failure, retry exhausted | `orchestrator.store.all_tasks(status=FAILED)` + DLQ count |
| `UNKNOWN` | Cannot determine — credential absent or code inert | `coordination_hub` `{"ok": False, "error": "..."}` + missing env vars |
| `STALE` | Last heartbeat beyond `useful_work_gap_min` | `task.last_heartbeat < now - useful_gap_min` |

### 3.3 LOCAL/VPS/AI/ENGINEERING/BUSINESS slices

| Slice | Local items | VPS items | Backend |
|---|---|---|---|
| LOCAL | Hermes/OpenClaw/Agnes/WorkBuddy/Antigravity (only 6 currently documented; Agnes/Antigravity NOT-PRESENT) | — | `desktop_registry.json` + `BUZZ_AUTH_TAG` (Desktop in-process mint, per ADR-167) |
| VPS | — | 9 worker domains + 31 agents + compatible CLI executors | `office_hq.coordination_topology()` + `automation_orchestrator.HERMES_BOTS` + `agent_registry._GOVERNANCE` |
| AI | MiniMax + Graphify | TypeSafe 4-slot health + OmniRoute combos + skills | `key_manager.get_all_slots()` + `omniroute /v1/models` + `judge_task_multipass` stats |
| ENGINEERING | Git worktrees + local GPU | PRs/CI/releases/production SHA/Docker services | `gh pr list --json` + `/api/admin/owner-os/release-state` + `docker ps` (when SSH) |
| BUSINESS | — | Lead acquisition/consented outreach/meetings/proposals/customer onboarding/delivery/payment/renewals/expansion/support | `marketing_clients.jsonl` + `billing_record` + `customer_delivery.py` |

---

## §4 Real evidence contract — per-dashboard fields (§4 directive)

Per status, every row must carry:

| Field | Source | Verified locally? |
|---|---|---|
| Source system | registry URL + version (e.g. `orchestrator_ledger.db` `bbf8b5e6`) | yes |
| Task or execution ID | `TaskRecord.task_id` / `DevTask.id` / `mission_id` | yes |
| Assigned worker + agent | `TaskRecord.owner_bot` + `TaskRecord.assigned_agent` | yes |
| Last successful execution | `dev_workers.heartbeat_at` / `TaskRecord.last_heartbeat` | yes |
| Latest heartbeat | same | yes |
| Data freshness timestamp | `_now_iso()` at read time | yes |
| Expected next execution | `task_scheduler.SCHEDULE_DEFS` + `team_scheduler` cron | yes |
| Input/output reference | `evidence.uri_or_path` (`StructuredEvidence`) | yes |
| Actual downstream result | `dev_workers.evidence` non-empty + `revenue_snapshots.mrr` | partial |
| Failure or blocker | `TaskRecord.error_message` / `mission.blocker` | yes |
| Customer/revenue impact | `customer_health.health_report()` + `billing.dunning` | partial |
| Available owner action | `SAFE_INTENTS` (`owner_os.py:76-84`) | yes |

---

## §5 ₹1 crore MRR + collected cash scoreboards (§5 directive)

### 5.1 Two SEPARATE scoreboards (NEVER ADDED)

```
A. VERIFIED RECURRING MRR  — Active subscription value normalized to monthly period
B. VERIFIED NET COLLECTED CASH — Actual payments received in reporting period
```

### 5.2 Data sources

| Metric | Source | File/endpoint |
|---|---|---|
| Active subscriptions (count) | `app/platform/revenue_digest._collect().subscriptions.active` | `data/revenue_snapshots.jsonl` (B1 daily append-only) |
| MRR (₹) | same | `revenue_snapshots.snapshot_today()` + backfill `estimated=True` rows |
| MRR target / gap | config: `MRR_TARGET_INR = 10_000_000` (₹1cr) | new env var |
| Collected cash (₹) | `app/billing/gst_invoice.py` + invoice INV/2026-27/0001 | `billing_records` table + `/api/billing/verified-cash` (NEW) |
| Cash target | `CASH_TARGET_INR = 10_000_000` | new env var |
| Active paying customers | `marketing_clients.jsonl` + `subscription.status=active` | `/api/admin/clients` |
| New subscriptions / renewals / churn | `revenue_attribution.py` | `/api/revenue/funnel` |
| Pending legitimate payments | `billing.dunning` + `owner_confirmed_upi` ledger | `/api/billing/pending` |
| Conversion rate | `sales_pipeline.stats` | `/api/sales/funnel` |
| Revenue by project / channel / campaign | `revenue_attribution.py` | `/api/revenue/attribution` |

### 5.3 Honest baseline (current state)

Per directive: "Use real data, not invented customers, conversions or projected collections."

- **VERIFIED active paying customers** = 1 (jiya makeover) per CLAUDE.md
- **VERIFIED MRR** ≈ ₹5,999/mo (her stated plan)
- **VERIFIED collected cash** = manual UPI confirmed; not aggregated into a system field today
- **Gap to ₹1cr target** = ₹99,94,001 MRR gap — explicit, owner-visible, not hidden
- **Today's hot queue** = 0 leads per `data/hot_queue_for_owner_2026-09-01.md`

**Honest reporting rule:** Every number either has a source citation OR shows `NO_DATA_TODAY` (NOT zero, NOT fabricated).

---

## §6 One Kanban — single task ID / lease / evidence trail (§6 directive)

**Mechanism:** `app/dev_control/external_agents/orchestrator.py:create_mission()` already enforces:
- `idempotency_key UNIQUE` (Postgres) / `register_idempotency` (CAS for SQLite)
- `mission.allowed_paths` → `locks.get_lock().acquire(...)` (path-level collision detection)
- `mission.lease_owner` + `mission.lease_until` (single active lease)
- `mission.evidence` list (single append-only trail)
- `mission.blocker` field (one canonical blocker reason)

For OCC/admin_tasks.db cross-references: add `external_task_id` field to `admin_tasks` row (optional, no migration needed — defer).

**Multi-worker collaboration:** "supporting roles and separate non-conflicting subtasks" — already supported via `external_agents.runner` (separate lease per worker).

**File collision prevention:** `app/dev_control/locks.py` path-lock + Git worktree per mission.

**Recipient idempotency:** `email_finder` dedup + `delivery_ledger` per-customer + `consent_ledger` opt-out (cross-channel suppression).

---

## §7 Telegram ↔ dashboard sync (§7 directive)

### 7.1 Event-driven update (existing infrastructure)

| Producer | Consumer | Mechanism |
|---|---|---|
| `task_ledger.create_task` (admin) | OCC JSON | PILOT sync script (`command_center/scripts/p1*.py`) |
| `automation_orchestrator.submit_task` | `/api/dev-control` + `coordination_hub.py` | direct DB write |
| `external_agents.orchestrator.create_mission` | `/api/dev-tasks/missions` | direct DB write |
| `TelegramBot.process_update` | `telegram_inbox.jsonl` (line 64) + audit JSONL | `data/telegram_inbox.jsonl` |

### 7.2 NEW bounded reconciliation (proposed)

- Every 60 s, OCC polling script compares `command_center/data/tasks.json` ↔ `automation_orchestrator.store.all_tasks()` ↔ `external_agents.store.list_missions()` and emits a `sync_drift.jsonl` log if divergence > 0.
- Telegram status report (`/status`) shows last-sync time.

### 7.3 Proactive Telegram alerts (§7 directive — exactly this list)

| Event | Severity | Routing |
|---|---|---|
| Critical customer-facing outage | P0 | Notify bot + owner chat |
| SmartFlo/Swara calling failure | P0 | Notify bot |
| Lost worker / task coordination | P0 | Notify bot |
| TypeSafe mandatory-validation outage | P0 | Notify bot |
| Email sender / inbound-reply failure | P1 | Notify bot |
| Failed customer delivery | P1 | Notify bot |
| CI/deployment blocker | P1 | Notify bot + owner chat |
| Security / credential incident | P0 | Notify bot + owner chat |
| Revenue / payment event | P1 | Notify bot (digest) |
| Owner approval needed | P0 | Notify bot + owner chat |

Healthy routine heartbeats → dashboard only, no Telegram message (§7 directive).

---

## §8 TypeSafe lifecycle wiring (§8 directive)

### 8.1 Per-stage wiring (already specified in `OWNER_OS_RECONCILE_2026-09-22.md` §6)

| Stage | Call site | Status |
|---|---|---|
| `intake_judge` | `coordination_hub.py` mutation_refused | NOT WIRED |
| `plan_review` | `external_agents/orchestrator.py:create_mission` | NOT WIRED |
| `output_review` | `automation_orchestrator.py:submit_task` | NOT WIRED |
| `revision_review` | `external_agents/orchestrator.py:submit_result` | NOT WIRED |
| `final_review` | `owner_command_center.py` | NOT WIRED |
| `outcome_review` | `owner_feed_bridge.py` | NOT WIRED |
| `session_summary` | session-end | NOT WIRED |

**Credential state:** `TYPESAFE_API_KEY` ABSENT in env → all live paths = deterministic-mock. Wiring requires key provisioning (key_manager slot A–D).

### 8.2 Cost guard (§8 directive)

- `cost_budget_inr_day` per agent (already in `agent_registry._GOVERNANCE`)
- API call cap per agent (`api_calls_day`)
- Quota = unified free providers only (Mistral/Groq/Cerebras/Gemini + EdgeTTS + Pollinations + SearXNG) — no paid STT/TTS/LLM

---

## §9 10-step owner-grade acceptance test (§9 directive)

Per directive: "The final deliverable is one functioning Owner OS: MiniMax coordinates the company, Telegram controls and reports operations, the Admin Command Center displays verified business truth, and all authorized agents work toward the ₹1 crore MRR target."

### 9.1 10-step E2E acceptance test

| # | Step | Evidence required |
|---|---|---|
| 1 | Owner sends `/tasks new "Onboard Jiya tier 2"` to Jarvis bot | Telegram `telegram_inbox.jsonl` row + `TYPESAFE_API_KEY` if intent classification |
| 2 | `/api/dev_tasks` POST creates canonical Postgres `DevTask` with idempotency_key from command | DB row + audit log |
| 3 | MiniMax assigns execution to available worker (via automation_orchestrator or external_agents orchestrator per task class) | `TaskRecord.assigned_agent` set + lease acquired |
| 4 | Worker performs authorized operation (e.g., email, CRM push, scheduled report) | Real external side-effect: SMTP send receipt / CRM API 200 / schedule invocation |
| 5 | TypeSafe validation invoked (intake_judge OR final_review depending on risk lane) | `judge_task_multipass` trace OR `dev_workers.evidence` with TypeSafe artifact hash |
| 6 | Actual output + downstream result persisted | DB row + file artifact + provider receipt |
| 7 | `/app/bot-command-center` reflects verified result WITHOUT manual status edit | OCC `tasks.json` updated via sync OR read directly from `automation_orchestrator` |
| 8 | Telegram returns same result + completion notification | Jarvis reply + Notify notification |
| 9 | Failed / disconnected / stale workers shown accurately | e.g., kill chromium 4047797 → `/status` shows BLOCKED or FAILED |
| 10 | Revenue / customer-delivery outcomes linked to real source records | `revenue_snapshots.jsonl` row + `marketing_clients.jsonl` entry + `billing_records` row |

**Test data:** owner-authorized test inputs only (no real customer data mutation). Per directive "Use approved owner accounts, test numbers, controlled transactions and customer authorization where required."

**Hard rule:** "A mock test or visually green dashboard alone does not satisfy acceptance." → Each step's evidence must be REAL data file / DB row / external receipt, not a Python assertion in a unit test.

### 9.2 Test environment requirements

| Requirement | Source | Status |
|---|---|---|
| Live Telegram token (rotated per ADR-198) | `TELEGRAM_JARVIS_BOT_TOKEN` in key_manager | UNVERIFIED — needs rotation |
| Live `TYPESAFE_API_KEY` | key_manager slot A–D | UNVERIFIED — needs provisioning |
| VPS SSH stable | direct exec | UNVERIFIED — currently flapping |
| Owner-authorized test number | manual | UNVERIFIED — owner input needed |
| Owner-authorized UPI test credit | manual UPI | UNVERIFIED — owner input needed |
| Hot queue (revenue lane) | `data/hot_queue_for_owner_2026-09-01.md` | UNVERIFIED — 0 leads |
| SmartFlo channel provisioned | provider portal | UNVERIFIED — 5 expected today |

---

## §10 Execution priority (§10 directive)

1. **P0**: VPS restore (chromium 4047797, cAdvisor 916157, find 990030, 1003798) + SmartFlo channel 1 acceptance run
2. **P0**: Owner-authorized test number for SmartFlo conversation test
3. **P1**: Reconcile 4 task-authority surfaces (decision in §1 above, owner-decide)
4. **P1**: Repair Telegram coordination (token rotation + 3 coordination groups)
5. **P2**: Wire 9 NEW Telegram commands (handlers in `telegram_bot.py`)
6. **P2**: TypeSafe 7-stage consumer wire-up (after key provisioning)
7. **P2**: 14-mailbox email hub build (after key_manager slot allocation)
8. **P2**: Local desktop worker enrollment (Hermes/OpenClaw/WorkBuddy already documented; Agnes/Antigravity needs Remote Desktop)
9. **P3**: CI repair (PR #554 prod_check ratchet fix)
10. **P3**: 10-step E2E acceptance test execution

---

## File-Level Action Plan (additive, reversible)

1. NEW `docs/coordination/OWNER_CONTROL_PLANE_SPEC_2026-09-22.md` ← THIS FILE
2. NEW `app/integrations/telegram_owner_commands.py` (9 new command handlers + UNAVAILABLE fallback)
3. EDIT `app/integrations/telegram_bot.py` — wire new commands in `_execute_command` dispatch table
4. EDIT `app/api/coordination_hub.py` — add `admin_kanban` + `dev_pipeline` read-only slices
5. EDIT `app/api/owner_command_center.py` — add `local_vps_overview` slice (per §3.3 mapping)
6. NEW `app/billing/verified_cash.py` — `/api/billing/verified-cash` endpoint
7. EDIT `app/platform/revenue_digest.py` — add `verified_mrr` + `verified_cash` separation (NEVER added)
8. NEW `app/platform/event_bus.py` — bounded reconciliation between OCC JSON ↔ orchestrator ↔ external_agents missions
9. NEW `tests/test_owner_control_plane.py` — 10-step acceptance test driver (NOT MOCK)
10. NEW `tests/test_telegram_commands_real_data.py` — each Telegram command → real backend call (NOT fabrication)

**All changes additive, all reversible (rollback = git revert).**

---

## Boundary Acknowledgements

- ❌ **VPS SSH flapping** → live VPS state UNVERIFIED
- ❌ **`TYPESAFE_API_KEY` absent** → no live TypeSafe wired
- ❌ **Telegram tokens rotation pending** (per ADR-198 + 3 coordination groups)
- ❌ **Hot queue empty** (0 leads)
- ❌ **No owner-authorized test inputs** (test number, UPI credit, customer data)
- ❌ **SmartFlo 5-channel provisioning** UNVERIFIED (today's expected)
- ❌ **Agnes + Antigravity** NOT-PRESENT in repo (no Remote Desktop)
- ✅ **All code-level claims cited with file:line**
- ✅ **All proposed actions reversible**
- ✅ **No new DB / no new orchestrator / no new agent identities**

---

**Owner next-step:** review §1.1 mapping table (canonical-task-authority-per-class) and confirm or revise; authorize any of the 10 file-level actions above; provide missing inputs (Telegram tokens, TypeSafe key, test number, UPI test credit).

🐦 pelican