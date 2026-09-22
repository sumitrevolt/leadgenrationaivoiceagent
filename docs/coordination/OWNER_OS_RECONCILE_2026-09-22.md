# Owner OS — Local + VPS Reconciliation (Code-Level Recon Only)

**Date:** 2026-09-22
**Worktree:** `feat/smartflo-acceptance-framework` @ `f89aad42`
**Owner:** Sumit (via Root session `mvs_2c0a08d649f94de3af323f87e632debc`)
**Scope:** Reconcile the four existing coordination/task surfaces, document the 9-worker + 31-agent roster, the desktop registry, and the 14-mailbox / Telegram / TypeSafe consumer surfaces — **CODE-LEVEL ONLY**. No live VPS, no Remote Desktop access, no credentials provisioned.

> **Causal-claim discipline:** every claim below cites a file:line or external doc. Anything unverifiable from this worktree is marked **UNVERIFIED**.

---

## 1. Existing Task / Coordination Authority Topology

**FOUR parallel task-authority surfaces exist today.** This is the foundational finding; the directive asks for "one canonical task authority" — these four cannot all be canonical.

### 1.1 OCC legacy JSON ledger (the one the directive says to reuse)

| Field | Value |
|---|---|
| File | `app/api/bot_command_center.py` (`/app/bot-command-center` page, `/api/bot-command-center/state`) |
| Data dir | `command_center/data/` (env override `BOT_CC_DATA_DIR`) → in prod: `/app/data/command_center` (volume, survives redeploy) |
| Backing files | `tasks.json`, `bots.json`, `messages.jsonl`, `pinned.json` |
| Writers | `command_center/scripts/pilot_*.py` (LOCAL pilot), `command_center/patches/pilot_dispatch_*.py` (LOCAL pilot), dispatched via Hermes PILOT bot |
| Readers | `app/api/bot_command_center.py` (page + state), `frontend/bot_command_center.html` (Telegram-style feed) |
| Auth | Admin JWT (`require_admin`) |
| Model | Simple list[dict] — `id`, `objective`, `owner`, `priority` (P0/P1/P2), `status` (NEW/RUNNING/ASSIGNED/...), `started`, `last_update`, `blocker`, `evidence` |
| Status enums | NEW / ASSIGNED / RUNNING / REVIEW / DONE / BLOCKED |
| Cross-host sync | md5+size parity check between LOCAL and VPS (`command_center/patches/pilot_dispatch_0902_0200.py:32`) — keeps them aligned but the LOCAL pilot is the *active writer* |

**Verdict:** This is the surface that **most closely matches** the directive's "current task authority reuse karo". Keep it as the OCC public surface. It's the lowest-friction path to honor the directive without inventing a new DB.

### 1.2 Admin Task Ledger (simple Kanban for admin dashboard)

| Field | Value |
|---|---|
| File | `app/admin/services/task_ledger.py`, API `app/admin/routes/tasks.py` |
| Backing store | SQLite `data/admin_tasks.db` |
| Workers (hardcoded) | `board`, `claude`, `engineering`, `guardian`, `hunter`, `openclaw`, `operations`, `pilot`, `platform`, `sales`, `success`, `verdant`, `workbuddy` (13 — note: `claude` + `verdant` here are NOT in the 31-agent canonical set) |
| Status enums | `backlog` / `in_progress` / `review` / `done` (different from OCC!) |
| Auth | Router-level `Depends(require_admin)` (P0 fix 2026-09-14) |
| Features | Auto-assign (idle-worker-with-fewest-tasks), duplicate detection (difflib 0.75 threshold), Kanban grouping |
| Readers | `app/api/owner_command_center.py` (L1→L4 aggregator reads `get_kanban` + `get_worker_statuses`); `app/platform/runtime_data_manifest.py` + `runtime_data_allowlist_entries.py` (ratchet allowlist — knows the DB path) |

**Verdict:** This is a **separate, narrow Kanban** for the admin dashboard's manual task tracking. It's NOT the 31-agent control plane. **Conflicts** with OCC's status enum and with automation_orchestrator's `READY/RUNNING/REVIEW/DONE/FAILED/DUPLICATE_SKIPPED` enum.

### 1.3 Automation Orchestrator (the canonical 9+31 control plane)

| Field | Value |
|---|---|
| File | `app/platform/automation_orchestrator.py` |
| Backing store | SQLite `data/orchestrator_ledger.db` (same file as `dev_workers` table — `app/platform/dev_workers.py` lives there too) |
| Owner bot set (9) | `board`, `pilot`, `guardian`, `engineering`, `platform`, `sales`, `hunter`, `operations`, `success` |
| Agent roster (31) | `app/platform/agent_registry.py:_GOVERNANCE` (line 180+) — derive-not-duplicate from `app.platform.team.STAFF` |
| Status enums | `READY` / `RUNNING` / `BLOCKED` / `REVIEW` / `DONE` / `FAILED` / `DUPLICATE_SKIPPED` |
| Hard rule | "One Task → One Owner Bot → One Assigned Agent → One Execution Path" (docstring L9) |
| Concurrency | RedisGovernorAuthority (`data/orchestrator_leases.json`, max 4 leases, 60 s timeout, fencing tokens) — file-fallback only because Redis may be down |
| CAS | `version + 1` per state transition; stale-result rejection by fencing token |
| Router | OmniRoute `:20128` primary → Claude proxy `:22000` → DSH `:3080` |
| Kill switch | `AUTOMATION_STOP_NEW_CLAIMS` env across all processes |
| Readers | `app/platform/coordination_hub.py` (`_automation_orchestrator_slice()` → `get_kanban_board()` + `get_metrics()`), `app/platform/revenue_workflow.py`, `app/platform/owner_feed_bridge.py`, `app/integrations/telegram_bot.py` |

**Verdict:** This is the **execution control plane** for the 31-agent workforce. It owns: durable task ledger, runtime lease governance, fence-token invalidation, dev_workers execution proof.

### 1.4 External Agents Orchestrator (mission ledger for CLI executors)

| Field | Value |
|---|---|
| File | `app/dev_control/external_agents/orchestrator.py` (with `policy.py`, `store.py`, `schema.py`, `adapters.py`, `runner/`, `approval.py`, `cas.py`) |
| Backing store | Mission store (CAS-Mongo/Postgres; idempotency_keys in MongoDB-style store) |
| State machine | `create → preflight → claim → running → implemented → testing → review_required → (review_passed \| changes_requested) → pr_open → ci_running → merge_queued → merged → [deployment_pending → canary_running] → verified → complete` |
| Risk classes | GREEN (auto-progress) / AMBER (stop at OWNER_DECISION_REQUIRED, needs approval_decision_id) / RED (refused at create) |
| Executor set | Cursor, Claude, Goose, FreeBuff, Codex, Hermes (per `adapters.known_executors()`) |
| Reviewer | Independent reviewer (typically Claude) — implementer cannot self-approve |
| AMBER gate | `app/dev_control/external_agents/approval.assert_amber_approved()` + `Owner OS ledger` decision_id (no boolean-alone) |
| API | `/api/dev-tasks/missions` (per coordination_hub mutation_refused redirect) — this is the **proposed unified landing surface** |
| Readers | `coordination_hub.py` (`_missions_slice()` via `external_agents.orchestrator.summary()` + `dashboard_rows()`) |

**Verdict:** This is the **external CLI mission control plane**. It exists for Cursor / Claude / Goose missions that go through PR + CI + merge. Separate from automation_orchestrator because the lifecycle ends at MERGED+VERIFIED, not DONE.

### 1.5 Dev Tasks API (Postgres engineering pipeline — the FOURTH one)

| Field | Value |
|---|---|
| File | `app/api/dev_tasks.py` (`/dev-tasks/*`); models `app/models/dev_task.py` + `dev_task_event.py` + `dev_usage.py` |
| Backing store | **Postgres** via SQLAlchemy `get_async_db` (NOT SQLite) |
| State machine | `PROPOSED → QUEUED → TESTS_RUNNING → STAGING_READY → STAGING_DEPLOYED → PRODUCTION_APPROVAL_REQUIRED → PRODUCTION_DEPLOYED → DELIVERY_VERIFICATION → COMPLETED` (+ `BLOCKED`, `FAILED`, `REVIEW_REQUIRED`, `CHANGES_REQUESTED`) |
| Gate | `DEV_ORCHESTRATOR=1` env (currently OFF; `503` if missing) |
| Governance | **Dual-governor HMAC**: Claude + ChatGPT attestations (`app/dev_control/governor_auth.py`) — both required for `_DUAL_REVIEW_GATED_STATES` |
| Idempotency | `idempotency_key UNIQUE` (Postgres) |
| Lease | atomic claim/heartbeat (`app/dev_control/claims.py`) |
| Wire-up | Worker pool: `app/tasks/dev_worker.py` Celery task; runner flag `DEV_WORKER_ENABLED` (separate gate) |
| Deploy | `app/dev_control/deploy.py` (promote_to_staging, request_production_approval) — gated by approval token |
| Reconcile | `app/dev_control/reconcile.py` |

**Verdict:** This is the **engineering-task pipeline** for production deployments — draft-safe, dual-governor attested, Postgres-backed. Not the same as external_agents orchestrator (different states, different gate). The relationship between this and external_agents orchestrator is **UNVERIFIED from this worktree** — they appear to be parallel implementations of similar concepts, possibly merged or competing.

### 1.6 Topology diagram (writer/reader)

```
                  ┌──────────────────────────────────────┐
                  │ OCC /app/bot-command-center          │
                  │ (Telegram-style feed, 9-bot chatter)│
                  └──────────────┬───────────────────────┘
                                 │ reads
                                 ▼
   PILOT (LOCAL scripts) ─writes─► command_center/data/tasks.json
                                       (+bots.json +messages.jsonl +pinned.json)
                                       ▲
                                       │ md5/size parity check
                                       │
   PILOT (VPS scripts)  ─writes──────► /opt/leadgen/command_center/data/tasks.json


   ┌─ Admin Task Ledger ───────────────────────────────┐
   │ /admin/api/tasks/{list,kanban,create,...}        │
   │ writers: app/admin/routes/tasks.py               │
   │ backing: data/admin_tasks.db  (SQLite)           │
   │ readers: app/api/owner_command_center.py (L1-L4) │
   │ workers: 13 hardcoded (claude, verdant present)  │
   └───────────────────────────────────────────────────┘

   ┌─ Automation Orchestrator (9+31 control plane) ──┐
   │ writers: app/platform/automation_orchestrator.py│
   │ backing: data/orchestrator_ledger.db (SQLite)   │
   │ readers:  coordination_hub.py, owner_feed_     │
   │           bridge.py, telegram_bot.py            │
   │ workers: 9 hermes bots + 31 agents              │
   └──────────────────────────────────────────────────┘

   ┌─ External Agents Orchestrator (mission ledger) ────┐
   │ writers: app/dev_control/external_agents/        │
   │          orchestrator.py                          │
   │ backing: mission store (CAS, idempotency_keys)   │
   │ readers: coordination_hub.py (missions slice)    │
   │ executors: Cursor/Claude/Goose/FreeBuff/Codex/   │
   │            Hermes (compatible adapters)          │
   └───────────────────────────────────────────────────┘

   ┌─ Dev Tasks API (Postgres engineering pipeline) ───┐
   │ writers: app/api/dev_tasks.py                    │
   │ backing: Postgres (SQLAlchemy get_async_db)       │
   │ readers: app/dev_control/{reconcile,delivery,   │
   │           deploy}.py                             │
   │ gate: DEV_ORCHESTRATOR=1 + DEV_WORKER_ENABLED    │
   └──────────────────────────────────────────────────┘
```

### 1.7 Recommended reconciliation

**Keep all four** but bind them through **one canonical reader** (coordination_hub.py is already that, *partially* — it does NOT read `admin_tasks.db` or the Postgres `DevTask` table):

| Surface | Role | Add to hub? |
|---|---|---|
| OCC legacy JSON (`tasks.json`) | Owner-facing Telegram-style feed, OCC page only | Keep as-is — it's the public surface |
| Admin Task Ledger (`admin_tasks.db`) | Admin dashboard manual Kanban | **Yes** — add as `admin_kanban` slice (read-only) |
| Automation Orchestrator (`orchestrator_ledger.db`) | 9+31 control plane, lease + CAS | Already in hub |
| External Agents Orchestrator (mission store) | CLI mission ledger | Already in hub |
| Dev Tasks API (Postgres `DevTask`) | Engineering pipeline, dual-governor | **Yes** — add as `dev_pipeline` slice (read-only) |

**Rule:** Each surface continues to write its own store. The hub is the **reader** that fans them into one owner view. No surface is "deleted". No new DB.

---

## 2. Desktop Apps Registry — 9 entries (no Agnes / Antigravity)

**File:** `docs/coordination/desktop_registry.json` (version 1, updated 2026-08-13)
**Loader:** `app/platform/coordination_desktop_registry.py` (2.9 KB) — `load_registry()` + `registry_slice()`, requires `_REQUIRED_APP_KEYS` (id/name/project/worktree/channel/buzzlock_tool/harness/headless_cli/heartbeat/status)
**Consumers:** `coordination_hub.py:snapshot()` → `registry_slice()`

| id | name | status | buzzlock | headless_cli | heartbeat | CLI adapter |
|---|---|---|---|---|---|---|
| `freebuff` | FreeBuff Desktop | registered | FREEBUFF | no | manual/desktop presence | GUI only |
| `android` | Android Studio | documented | none | no | none today | GUI only |
| `opencode` | OpenCode Desktop | registered | OPENCODE | yes | hub HMAC | `opencode run --format json --dir <ws>` |
| `cursor` | Cursor Desktop | registered | CURSOR | yes | hub HMAC | `cursor-agent -p` |
| `hermes` | Hermes Desktop | registered | HERMES | yes | hub HMAC | desktop GUI + headless CLI (MCP-coordinated) |
| `buzz` | Buzz Desktop | registered | none | no | hub buzz webhook (HMAC) | GUI + local relay (bus transport) |
| `openclaw` | OpenClaw Desktop | **observed-not-attested** | OPENCLAW | yes | process observed; hub HMAC enrollment **pending** | OpenClaw Tray GUI + local gateway |
| `workbuddy` | WorkBuddy Desktop | **observed-not-attested** | WORKBUDDY | yes | process observed; hub HMAC enrollment **pending** | WorkBuddyAI GUI + codebuddy sidecar |
| `chatgpt-desktop` | ChatGPT Desktop / Codex | **observed-not-attested** | CODEX | no | desktop process observed; hub HMAC enrollment **pending** | ChatGPT desktop task UI + Codex app-server |

**Total: 9 apps — 6 registered, 3 observed-not-attested, 0 absent-but-mapped.**

### 2.1 Agnes + Antigravity — NOT in repo

**VERIFIED absent.** Neither appears anywhere in:
- `docs/coordination/desktop_registry.json` (9 apps, none of which are Agnes or Antigravity)
- `app/platform/coordination_desktop_registry.py:_REQUIRED_APP_KEYS` (only schema; doesn't enumerate apps)
- 31-agent registry (none of `ananya/.../tara` match)
- 9-worker Hermes bot set
- `_MUTATION_POINTERS` in coordination_hub.py

The directive's directive "Aapke Hermes, OpenClaw, Agnes, WorkBuddy aur Antigravity desktop apps ko ek hi coordinated local workforce mein lana hai" lists Agnes and Antigravity — but the **registry has no record of them**. Without Remote Desktop connectivity I cannot enroll or verify them.

**Decision (code-level):** Treat Agnes and Antigravity as **NOT-PRESENT** until a remote desktop proves otherwise. Do not invent registry rows.

---

## 3. 9 Worker + 31 Agent Roster — Verified Canonical

### 3.1 9 Hermes bots (automation_orchestrator.HERMES_BOTS, line 470)

| bot | role |
|---|---|
| `board` | Executive Strategy & Prioritization |
| `pilot` | Operational Orchestration & Task Dispatch |
| `guardian` | Security, Compliance & Policy Verification |
| `engineering` | Code, Tools & Skill Pack Build |
| `platform` | SRE, DBRE & Health Infrastructure |
| `sales` | Growth Pipeline & Lead Scoring |
| `hunter` | Prospecting & Cold Outreach |
| `operations` | Content Generation, CRM & Customer Delivery |
| `success` | Delivery Assurance & Quality Check |

### 3.2 31 agents (agent_registry._GOVERNANCE keys + Boss = `manager`)

| # | id | team (office_hq room) | lane | default_mode | key capability |
|---|---|---|---|---|---|
| 1 | `manager` | coordinator | GREEN | LIVE | Boss — coordinator, dispatch, escalation to owner |
| 2 | `kavya` | platform_engineering | GREEN | LIVE | Ops health watchdog |
| 3 | `hermes` | platform_engineering | GREEN | PROPOSAL | Infra handler (proposal-only, no destructive) |
| 4 | `nikhil` | admin_finance | GREEN | LIVE | Delivery assurance (read-only delivery scan) |
| 5 | `vikram` | platform_engineering | GREEN | PROPOSAL | Code upgrader (no merge/deploy) |
| 6 | `guru` | platform_engineering | GREEN | — | Skill pack |
| 7 | `pranav` | platform_engineering | GREEN | — | SRE |
| 8 | `vidya` | admin_finance | GREEN | — | FinOps |
| 9 | `arnav` | platform_engineering | GREEN | — | Security |
| 10 | `kabir` | platform_engineering | GREEN | — | DBRE |
| 11 | `diya` | lead_lab | GREEN | — | Data integrity |
| 12 | `aryan` | platform_engineering | GREEN | — | Deps CVE audit |
| 13 | `arya` | platform_engineering | GREEN | — | MCP engineer |
| 14 | `dev` | marketing_team | — | — | SEO blog |
| 15 | `rohan` | sales_crm | — | — | Lead prospecting |
| 16 | `isha` | marketing_team | — | — | Content generation |
| 17 | `ravi` | marketing_team | — | — | (marketing) |
| 18 | `neha` | lead_lab | — | — | Pipeline rescore |
| 19 | `kiran` | marketing_team | — | — | Campaign optimizer |
| 20 | `priya` | sales_crm | — | — | CRM sync |
| 21 | `zara` | marketing_team | — | — | Social engine |
| 22 | `anika` | sales_crm | — | — | Cadence engine |
| 23 | `ira` | sales_crm | — | — | Journey engine |
| 24 | `swara` | voice_team | RED | HARD_OFF | Main telecaller (RED lane — dispatch-blocked per `_GOVERNANCE` L521) |
| 25 | `ananya` | voice_team | — | — | Voice |
| 26 | `riya` | voice_team | — | — | Voice |
| 27 | `arjun` | qa_audit | — | — | Voice QA |
| 28 | `meera` | qa_audit | — | — | Trainer + ML |
| 29 | `lekha` | voice_team | — | — | Call KPI digest |
| 30 | `raksha` | voice_team | — | — | Call transfer |
| 31 | `tara` | platform_engineering | — | — | Platform |

**Count = 31** (matches `owner_os.py` "canonical workforce = app.platform.team.STAFF (31)" and `agent_registry.py` docstring "CANONICAL COUNT = 31").

### 3.3 Mapping desktop apps → existing agent IDs (compatible adapters)

Per directive "Hermes/OpenClaw/Agnes/Antigravity CLI ko compatible execution adapters ki tarah use kare, naye duplicate agents ki tarah nahi":

| Desktop app | Adapter role | Existing canonical identity |
|---|---|---|
| Hermes | infra handler (proposal-only) | `hermes` (platform_engineering, lane GREEN) — registry already says `primary_flag="INFRA_HANDLER"` |
| OpenClaw | worktree-based code edits | `engineering` (HERMES_BOT) or `vikram` (code_upgrader, GREEN PROPOSAL) |
| Agnes | **NOT-PRESENT** — requires remote desktop to confirm | TBD pending enrollment; possible mapping to existing content/marketing agent |
| Antigravity | **NOT-PRESENT** — requires remote desktop to confirm | TBD |
| WorkBuddy | local codebuddy sidecar | `engineering` (HERMES_BOT) — registry allows `headless_cli=true` for it |
| OpenCode | `opencode run --format json --dir <ws>` CLI | `engineering` (HERMES_BOT) |
| Cursor | `cursor-agent -p` CLI | `engineering` (HERMES_BOT) — external_agents.adapters.CURSOR is the executor |
| FreeBuff | in-process agent GUI | `engineering` (HERMES_BOT) — adapter: external_agents FreeBuff (per registry) |
| Codex/ChatGPT | Codex app-server | `engineering` (HERMES_BOT) — adapter: external_agents CODEX |

**Hard rule:** desktop apps are CLIs/agents that produce **task results** for the canonical 31-agent workforce; they are **NOT themselves 32nd–40th agents**. The Boss coordinates; the 31 agents own the work; the desktop apps are the execution adapters that the agents use.

---

## 4. Telegram Command/Alert Surface

**File:** `app/platform/telegram_coordinator.py`
**Architecture:** Dual-bot (decisive via TypeSafe 2026-09-20)

| Bot | Token env | Role | Polls getUpdates? |
|---|---|---|---|
| Jarvis | `TELEGRAM_JARVIS_BOT_TOKEN` | Ingress command bot (`@Sumits_jarvis_bot`) — `/status`, `/tasks`, `/agents`, `/pause`, `/resume` | yes (with lease) |
| Notify | `TELEGRAM_NOTIFY_BOT_TOKEN` | Broadcast-only egress (`@Leadsgenai1_bot`) | NO (409-conflict prevention) |
| Fallback | `TELEGRAM_BOT_TOKEN` | Legacy fallback | per slot config |

**Polling coordination** (`telegram_coordinator.py:74`): `TELEGRAM_INGRESS_OWNER = auto|local|vps|hermes|off` — only one role polls at a time. Real 409 = standby with backoff, **release own lease** instead of fighting. Lease: Redis primary → file fallback (`data/telegram_poll_lease.json`).

**Setup spec:** `config/telegram/setup_spec.yaml` (13 entities, single source of truth).
**Egress routing:** `config/telegram/owner_notify_routing.yaml` (severity-based).
**Webhook:** `/api/webhooks/telegram` (secret-token fail-closed).
**State file:** `data/telegram_jarvis_state.json` (heartbeat).
**Verify helper:** `scripts/telegram_verify_setup.py` (read-only truth table — never prints tokens).

**Token-fingerprint handling:** keyed by SHA-256 fingerprint, not raw token — `_dead_egress_tokens: set[str]` and `_token_cache: dict[str, tuple[float, dict]]`.

**Telegram = INTERFACE, NOT ORCHESTRATOR.** Per directive: "Telegram command aur alert interface hoga, doosra orchestrator nahi." Confirmed in code: `telegram_coordinator.py` exposes commands but delegates to `task_ledger` / `automation_orchestrator` / `owner_os` for state.

---

## 5. Email Hub — single-account today, 14-mailbox is PLANNED, not implemented

**Current state:** single SMTP/IMAP account only.
- `app/config.py:197` — `smtp_user: str = ""` (single user)
- `app/integrations/email_sender.py:70-72` — `self.user = settings.smtp_user`; `self.from_email = settings.email_from or settings.smtp_user`
- `app/platform/reply_agent.py:480-500` — `_creds()` returns ONE tuple (host, user, password)
- IMAP host derived from SMTP host (`smtp.` → `imap.`), fallback `imap.hostinger.com`

**Planned-but-not-implemented (14-mailbox pool):** `docs/AUTONOMOUS_EXECUTION_MASTER_PLAN_v2.md:115` "All 14 mailboxes have SMTP/IMAP health = GREEN" + line 572 "Email sender pool audited (14 mailboxes)". **VERIFIED: the 14-mailbox pool is documented as a goal, not present in code.**

**Per directive "Saare authorized mailboxes ki ek common inbound/outbound interface ho. MiniMax eligible recipient ke liye appropriate sender select kare; har response CRM, canonical task aur original email thread se linked rahe. Credentials sirf scoped key manager ke paas hon."** — this is a build directive, not a re-use. SPEC, not code:
- Backing store: key_manager-managed (`app/platform/key_manager.py`, 4-slot Fernet vault → `/opt/leadgen/secrets/keys.json`)
- Sender selection: round-robin / warmup-aware (already partly built in `app/platform/email_warmup.py`)
- Response threading: `reply_agent.py:_safe_thread_headers` already returns `(message_id, references)` (L541-549)
- CRM link: prospects/clients via `app/marketing/customer_delivery.py` (already wired)

---

## 6. TypeSafe Multi-Pass Consumer Wiring (per stage)

**Module:** `app/platform/typesafe_multipass.py` (606 lines, PR #553 — local-code-verified, no live key in env)
**Session policy:** `app/platform/typesafe_session_policy.py` — legacy `judge_task` (1-call gate, AUTHORITY) + new `judge_task_multipass` (ADDITIVE — short-circuits to `consumed_calls=0` when legacy returns `route=review`)

**Five stage methods** in `MultipassConsumer`:
1. `intake_judge` — semantic evaluation of input
2. `plan_review` — review of generated plan
3. `output_review` — review of generated output (post-LLM)
4. `revision_review` — review of revision attempt
5. `final_review` — final QA before dispatch
**Plus 2 outcomes:**
6. `outcome_review` — post-execution evaluation
7. `session_summary` — end-of-session summary

**Consumers** (where to wire per stage):
| Stage | Where it should be called | Current wiring |
|---|---|---|
| `intake_judge` | `app/platform/coordination_hub.py` mutation_refused → before any high-risk action | NOT WIRED |
| `plan_review` | `app/dev_control/external_agents/orchestrator.py:create_mission` → after `policy.classify_mission_request` | NOT WIRED |
| `output_review` | `automation_orchestrator.py:submit_task` → after CAS-ready, before final DONE | NOT WIRED |
| `revision_review` | `external_agents/orchestrator.py:submit_result` → when verdict is BLOCKED | NOT WIRED |
| `final_review` | `owner_command_center.py:_get_task_ledger_summary` → before publishing to /api/owner-command-center/overview | NOT WIRED |
| `outcome_review` | `app/platform/owner_feed_bridge.py` after each execution proof row | NOT WIRED |
| `session_summary` | session-end in MiniMax Root session | NOT WIRED |

**Credential state:** `TYPESAFE_API_KEY` is **ABSENT** in this env (per worktree inspection). All live paths go through `_ts.typesafe_system_one` with deterministic-mock fallback. **No live TypeSafe call has been verified.** Per directive "If no usable credential exists in an authorized environment, implement and test the consumer wiring without fabricated live results" — done at PR #553 (unit tests pass on deterministic mock).

---

## 7. Docker Consolidation Spec (no execution)

Per directive: "Identify which workloads belong to LeadGen AI and which are unrelated. Verify actual ownership and dependencies. … Consolidate genuinely redundant LeadGen images and duplicate executors without merging distinct required services or losing persistent state."

**UNVERIFIED from this worktree — needs VPS SSH (currently flapping between TCP-reachable and command-timeout).** Spec for the repair, **to be executed only on owner authorize**:

| Action | Evidence needed first | Reversibility |
|---|---|---|
| Inventory all `docker ps -a` output on VPS | SSH + `docker ps -a --format json` | reversible |
| List images with `docker images --format json` and grep `leadgen` / `leadsgenai` / `swara` / `vobiz` / `smartflo` | SSH | reversible |
| Identify duplicate image tags (`:latest` of same name) | SSH | reversible |
| Confirm which Compose file each container came from (`docker inspect CONTAINER --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}'`) | SSH | reversible |
| Detect containers NOT in `docker-compose.vps.yml` (the canonical 2026-07-18 lesson — default compose was wrong stack) | SSH | reversible |
| Identify orphaned volumes (`docker volume ls --filter dangling=true`) | SSH | reversible |
| Stop + quarantine (rename + tag) duplicate worker containers one at a time; **never delete** | SSH + owner authorize | reversible (rollback via tag) |
| After confirmed duplicates cleared, prune images: `docker image prune` (only images with NO container using them) | SSH | irreversible for images |

**Hard rule:** **NO `docker system prune -a`, NO `--reset --hard`, NO `rm -rf` of volumes.** All actions reversible until owner approves.

---

## 8. Recommended Action Plan (after owner authorize)

1. **Reuse OCC legacy JSON** (`command_center/data/tasks.json`) as the public owner-facing Kanban — already wired in `app/api/bot_command_center.py`.
2. **Add 2 read-only slices to coordination_hub.py:** `admin_kanban` (from `admin_tasks.db`) + `dev_pipeline` (from Postgres `DevTask`). Both read-only, fan-IN only — no new DB, no overwrite.
3. **Treat Agnes + Antigravity as NOT-PRESENT** until Remote Desktop access verifies their installation. Do not invent registry rows.
4. **Wire TypeSafe multipass consumer at the 7 stage call-sites** listed in §6 — code-only, deterministic-mock by default (`TYPESAFE_API_KEY` absent). Live wiring requires key provisioning.
5. **14-mailbox email hub** is a build directive — write spec (sender pool, round-robin, warmup, threading) before code. No execution without owner approve.
6. **Docker consolidation** needs SSH (currently flapping) — execute only after SSH restore + owner authorize.

---

## 9. Local-code VERIFIED vs UNVERIFIED

| Component | VERIFIED (local-code) | UNVERIFIED (live-access-blocked) |
|---|---|---|
| OCC JSON ledger surface | yes — full read of `bot_command_center.py`, scripts, data layout | live contents of `command_center/data/*.json` on VPS — needs SSH |
| Admin task ledger surface | yes — `admin_tasks.db`, 13 workers, all CRUD endpoints | live contents — needs DB read |
| Automation orchestrator | yes — `orchestrator_ledger.db`, 9+31, fencing tokens, CAS | live ledger contents, live concurrency, live dev_workers count |
| External agents orchestrator | yes — mission lifecycle, GREEN/AMBER/RED, approval gate | live mission store contents, live cursor/claude runs |
| Dev Tasks API (Postgres) | yes — all endpoints, dual-governor, HMAC | live Postgres contents — needs DB read |
| Desktop registry | yes — 9 apps, schema, loader | Agnes/Antigravity actual installation |
| 9 worker + 31 agent roster | yes — full enumeration | live runtime rollout_state (which agents are currently LIVE vs DRAFT vs HARD_OFF) |
| Telegram | yes — dual-bot architecture, polling lease, token-fingerprint vault | live token validity (rotate per ADR-198 plan) |
| Email hub | yes — single-account code, 14-mailbox documented intent | live SMTP/IMAP credentials, live 14-mailbox build state |
| TypeSafe multi-pass module | yes — 606-line module, 5 stages, deterministic mock | live TypeSafe API (no `TYPESAFE_API_KEY` in env) |
| VPS resource state | partial — code-level inventory only | live CPU/RAM/disk — needs SSH (currently flapping) |

---

**Owner next-step:** review this report and authorize any of:
- Bounded repair steps in §7 (Docker consolidation, requires SSH + owner sign-off)
- 14-mailbox email hub build (requires key_manager slot allocation + sender-pool spec)
- Agnes + Antigravity remote-desktop enrollment (requires desktop access)
- TypeSafe live key provisioning (requires `TYPESAFE_API_KEY` in `/opt/leadgen/secrets/keys.json` slot A–D)
- Reuse OCC legacy JSON as canonical — confirm and lock other three task surfaces as `coordination_hub.py` reader-only slices (no schema merge)

**Rollback for every step above:** all proposed changes are additive + reversible.

🐦 pelican