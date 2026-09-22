# Canonical Task Authority — Decision (Wave 7)

**Date:** 2026-09-22
**Worktree:** `feat/smartflo-acceptance-framework` @ `f89aad42`
**Owner:** Sumit (via Root session `mvs_2c0a08d649f94de3af323f87e632debc`)
**Authoritative by:** Graphify-style call-graph evidence + code reads (no migration performed)

> **Hard rule per §1 directive:** "Engineering tasks should continue to use the existing governed engineering pipeline unless current evidence justifies a compatible migration. Operational agent execution must retain its existing durable orchestration and fencing controls. … Do not perform a destructive ledger migration or rewrite production task history without independently verified backup, restore and rollback."

---

## 1. Evidence-based decision

I did NOT auto-accept the Wave 6 proposed 7-class mapping. I traced every `create_task` / `create_mission` / `submit_task` call-site in the repo:

### 1.1 The 4 task-authority surfaces — actual writers + consumers

| Authority (writer) | File:line of writer | Callers (consumers of writer) | What it actually owns |
|---|---|---|---|
| **`AutomationOrchestrator.submit_task`** | `app/platform/automation_orchestrator.py:544` | • `app/integrations/telegram_bot.py:512` (`/test_handoff`)  • `app/platform/automation_orchestrator.py:843` (internal auto-dispatch)  • `app/platform/revenue_workflow.py:236` (revenue tasks)  • `app/integrations/telegram_bot.py:100` (instantiated for every Telegram command read) | **9 Hermes bots + 31 agents — durable execution plane.** Fencing tokens, CAS versioning, 4-lease governor, dev_workers execution proof (same SQLite `data/orchestrator_ledger.db`). |
| **`external_agents.orchestrator.create_mission`** | `app/dev_control/external_agents/orchestrator.py:59` | • `app/integrations/openclaw/mission_commands.py:113`  • `app/api/dev_tasks.py:673` (POST `/dev-tasks/missions`)  • `app/platform/mission_control.py:287`  • `app/integrations/openclaw/external_agent_commands.py` | **Engineering mission lifecycle** (create → preflight → claim → running → implemented → testing → review_required → review_passed/changes_requested → pr_open → ci_running → merge_queued → merged → verified → complete). GREEN/AMBER/RED classification + dual-governor + idempotency_key CAS in `store.register_idempotency`. |
| **`api/dev_tasks.py` create_task** | `app/api/dev_tasks.py:158` (`POST /dev-tasks`) | Read consumers: `app/dev_control/{delivery,usage,service,runner,deploy,claims,reconcile}.py` | **Engineering pipeline SHELL** (Postgres `DevTask` SQLAlchemy table). Draft-safe `DEV_ORCHESTRATOR=1` gate; dual-governor HMAC (Claude + ChatGPT); atomic claim/heartbeat; staging→production deployment gate. |
| **`task_ledger.create_task`** | `app/admin/services/task_ledger.py:111` | `app/admin/routes/tasks.py:58` (admin UI) | **Admin manual Kanban.** 13 hardcoded workers incl. `claude`/`verdant`. NOT connected to agent execution. Auto-assign by idle-worker-fewest-tasks. |
| **`command_center/data/tasks.json`** (PILOT legacy) | `command_center/scripts/pilot_*.py` + `command_center/patches/pilot_dispatch_*.py` | `app/api/bot_command_center.py:85-91` (OCC public page + state.js) | **OCC visible-public Telegram-style feed.** md5+size parity sync between LOCAL and VPS `/opt/leadgen/command_center/data/tasks.json`. |

### 1.3 Overlap evidence — `api/dev_tasks.py` calls external_agents orchestrator

```
api/dev_tasks.py:634     from app.dev_control.external_agents import orchestrator, policy
api/dev_tasks.py:649     from app.dev_control.external_agents import orchestrator, policy
api/dev_tasks.py:673     out = orchestrator.create_mission(**body.model_dump())
```

**Reading this:** `POST /api/dev-tasks/missions` (the URL coordination_hub mutation_refused points at for `create_mission`) ALREADY delegates to `external_agents.orchestrator.create_mission`. The mission lifecycle (GREEN/AMBER/RED, dual-governor, AMBER approval_decision_id) is the actual authority. The Postgres DevTask row is a parallel durable shell used by `dev_control/{runner,deploy,delivery}.py` for production deployment.

**Conclusion:** **`/api/dev-tasks/missions` IS the unified engineering surface; it's a thin wrapper over `external_agents.orchestrator.create_mission`.** Both work together by design — mission lifecycle + Postgres durable shell + dual-governor HMAC.

---

## 2. DECISION — Canonical authority mapping (FINAL, evidence-based)

| Task class (per directive §1) | Canonical authority | Backing store | Endpoint / surface | Why |
|---|---|---|---|---|
| **Telegram owner-issued action tasks** | `external_agents.orchestrator.create_mission` (via `/api/dev-tasks/missions`) | mission store + CAS idempotency_keys | `POST /api/dev-tasks/missions` | Already wired as unified engineering surface; AMBER approval_decision_id gate exists |
| **Engineering pipeline (PR/CI/deploy)** | `external_agents.orchestrator.create_mission` + Postgres `DevTask` | mission store + Postgres `dev_tasks` table | `POST /api/dev-tasks` + `POST /api/dev-tasks/missions` | Mission lifecycle = authority; Postgres DevTask = durable deployment shell |
| **9 Hermes bots + 31 agents execution** | `AutomationOrchestrator.submit_task` | SQLite `data/orchestrator_ledger.db` (fencing tokens + CAS) | `app/platform/automation_orchestrator.py:submit_task` | Only writer of agent-execution tasks; fencing + lease + dev_workers execution proof |
| **Admin manual Kanban** | `task_ledger.create_task` | SQLite `data/admin_tasks.db` | `POST /admin/api/tasks` (admin JWT) | Internal admin UI; NOT execution plane |
| **OCC public visible Kanban** | `command_center/data/tasks.json` (PILOT scripts) | JSON files | `/app/bot-command-center` page | Telegram-style feed; NOT execution plane |
| **Customer follow-up / delivery** | `app/marketing/customer_delivery.py` | `marketing_clients.jsonl` + `delivery_ledger` | `/app/delivery` | Already canonical; `anika` + `ira` cadence + journey |
| **Payment / invoice / UPI** | `app/billing/gst_invoice.py` + invoice INV/2026-27/0001 | billing_records table | `/api/billing/*` | Manual UPI confirmation; already canonical |

**Mapping = 7 task classes, 6 canonical writers (Postgres DevTask + external_agents orchestrator are co-canonical for engineering). NO destructive migration performed.**

---

## 3. What this means concretely

### 3.1 For Telegram owner commands (§2 directive)

- Telegram MUST call `POST /api/dev-tasks/missions` (admin JWT) — NOT write to `task_ledger` or `OCC JSON` directly.
- Telegram reads MUST come from the same store the writer used: for engineering = mission store; for agent execution = `orchestrator_ledger.db`; for OCC visible feed = `command_center/data/tasks.json`.
- New `/revenue` `/workers` `/smartflo` `/typesafe` `/email` `/video` `/ci` `/approvals` `/blockers` commands read these canonical stores — no new DB.

### 3.2 For OCC Kanban (§6 directive)

- OCC JSON is the **public visible** Kanban (no migration). PILOT scripts continue to write there.
- **Bounded reconciliation:** `sync_drift.jsonl` emitted if OCC JSON ↔ `orchestrator_ledger.db` ↔ mission store diverge.
- Each task shown in OCC Kanban carries `external_task_id` field referencing the canonical task (engineered; deferred to a follow-up PR — no migration today).

### 3.3 For Admin Command Center (§3 directive)

- `/app/owner-command-center` aggregator (already built in `app/api/owner_command_center.py`) reads from each canonical store independently. NO new task database created.
- 10-state taxonomy (REGISTERED / CONFIGURED / CONNECTED / RUNNING / VERIFIED_WORKING / DEGRADED / BLOCKED / FAILED / UNKNOWN / STALE) implemented in `app/platform/operational_state.py` (Wave 7 deliverable).
- MRR/cash separation: `app/billing/verified_cash.py` reads `billing_records` + `marketing_clients.jsonl` (Wave 7 deliverable).

### 3.4 For TypeSafe (§4 directive)

- TypeSafe consumer wiring is ADDITIVE — does not change canonical writers.
- 7 stage methods (intake/plan/output/revision/final/outcome/session_summary) wired as decorators/wrappers at the canonical write/read sites. NO parallel client, NO second key pool.
- Deterministic-mock by default (no `TYPESAFE_API_KEY` in env). Live wiring activates when key present.

### 3.5 For desktop / CLI workforce (§5 directive)

- Hermes/OpenClaw/WorkBuddy/OpenCode/Cursor/FreeBuff/Codex = **compatible execution adapters** mapped to existing 31-agent identities (`engineering` HERMES_BOT primarily).
- Agnes + Antigravity = **NOT-PRESENT** in repo. Do not invent agent IDs. Real enrollment requires Remote Desktop.

### 3.6 For 14-mailbox email hub (§6 directive)

- Inventory first: `reply_agent._creds()` is single-account today; need 14 OUTREACH mailboxes (separate from 14 OmniRoute AI-provider accounts).
- Sender selection: per-mailbox key_manager slot; thread continuity via `_safe_thread_headers` (already wired).
- Health check failure = `BLOCKED` state, never `HEALTHY`.

### 3.7 For SmartFlo + Swara + VPS (§7 directive)

- P0 unchanged. No blind PID kill. Single-channel acceptance run before 5-channel rollout.

### 3.8 For CI + release safety (§8 directive)

- PR #554 prod_check ratchet fix = **active work**, not deferred.
- Fix root causes; no blanket `xfail`; no `git add -A`; review each change.

---

## 4. Acceptance gate

Per §9 directive: "MiniMax ka next report tab meaningful hoga jab kam se kam ek real Telegram → canonical task → worker execution → Admin Command Center workflow chale."

**This Wave 7 session** delivers the following VERIFIED local-code changes (all additive, all reversible):

1. ✅ Canonical authority decision (this file)
2. ✅ TypeSafe `intake_judge` consumer wired in `automation_orchestrator.submit_task` (additive, deterministic-mock by default)
3. ✅ 9 new Telegram owner commands implemented in `app/integrations/telegram_owner_commands.py` (additive dispatcher; UNKNOWN/UNAVAILABLE fallbacks)
4. ✅ 10-state operational taxonomy module `app/platform/operational_state.py` + tests
5. ✅ `/verified-revenue` + `/verified-cash` Telegram commands (honest baseline — NOT carry-forward ₹5,999)
6. ✅ CI repair: `scripts/prod_check.py` investigation + targeted runtime-data fix for PR #554 ratchet

Each deliverable: targeted pytest + py_compile + prod_check evidence.

---

## 5. Rollback

Every change above is additive. To rollback: `git revert` of the Wave 7 PR restores the prior state. NO production task history rewritten, NO destructive migration, NO ledger merge.

---

🐦 pelican