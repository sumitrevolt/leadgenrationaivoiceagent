# Flow Runner — Executable Automation Builder (V1) — Design Spec

> **Status:** Approved (council-validated 2026-06-20) — ready for implementation plan.
> **Decision:** Build our OWN executable layer over the existing `process_engine`; **n8n self-host REJECTED**.
> **Scope discipline (council guardrail):** deliberately MINIMAL V1 — linear flows only, existing executor whitelist, flag-OFF default, admin-only, one-session time-box.

---

## 1. Why (problem)

The Architecture Explorer (`/app/explorer`) has a **"builder" view** (`currentView === 'custom'`): a visual node/edge canvas with a 10-item palette. Today it is **visual-only** — flows live in `localStorage` (`explorer_custom_flows`) and can be exported as JSON, but **nothing executes**. There is no way to actually *run* a composed automation.

Meanwhile the project already owns a complete deterministic execution engine:
- `app/agents/process_engine.py` — process-as-code, event-sourced JSONL journal (`data/process_runs/`), crash-safe replay/resume, deterministic code gates, enforced human-approval **breakpoints**, runs in Celery (`staff_jobs.process_tick`).
- `app/agents/process_library.py` — `PROCESSES` (static workflow defs) + `EXECUTORS` (9 real, draft-safe action fns: `scrape, harvest, rescore, sales_analysis, content_pack, social_drafts, cadence_run, optimizer, revenue_sweep`).

**Flow Runner = the thin bridge** that makes a visually-built flow run on this engine. The hard parts (determinism, journaling, resume, gates, breakpoints, Celery durability, draft-safe side-effects) already exist and are battle-tested in prod.

## 2. Goal / Non-goals

**Goal (V1):** An admin can compose a **linear** automation flow in the explorer builder, **save it to the server**, **run it**, watch **per-node live status** on the canvas, and **approve human breakpoints** — all executed by the existing `process_engine`, fully inside our journal / RBAC / flags / compliance gates.

**North-star:** FULL n8n-like features in the explorer (branching, triggers, data-passing, rich palette, run-history). That is a DAG platform — sequenced into the **§11 phased roadmap** so each step ships independently. V1 below = **Phase 1** (the foundation).

**Non-goals (V1 — YAGNI, sequenced into §11 roadmap, not dropped):**
- Branching / conditionals / loops / fan-out / parallel joins (engine is strictly linear — arbitrary DAG would force an engine rewrite).
- Event triggers (`outbound_webhooks`) and cron triggers (manual run only in V1).
- Client-facing / per-tenant flow builder (internal admin tool only).
- Arbitrary code nodes or new side-effecting actions (whitelist only).
- Retry-policy / typed-params editor UI (sane defaults only).

## 3. Architecture

```
[Explorer builder UI]                      [Server / app]                      [Celery worker]
 nodes+edges canvas  --save-->  POST /api/automation/flows  --> data/flow_runner/flows.jsonl
        |                                                              (shared ./data bind-mount)
        |  --run-->  POST .../flows/{id}/run                                    |
        |               -> process_engine.start_run("flow:"+id, inputs)         |
        |                  -> journal data/process_runs/<run_id>.jsonl          |
        |                                                          process_tick (beat) advances:
        |  poll GET .../runs/{run_id}  <-- process_engine.replay()  <-- get_process("flow:"+id)
        |     (status + steps_done -> animate per node)                -> flow_store.load + compile
        |  approve breakpoint --> POST .../runs/{run_id}/approve -> process_engine.approve()
```

**Key integration point:** `process_library.get_process(key)` is the single resolver used by both `start_run` (web) and `advance`/`process_tick` (worker). We extend it: if `key` starts with `flow:`, load the flow from the flow-store and compile it to a process dict; else fall back to the static `PROCESSES`. Because both processes read the same `./data` file, web and worker resolve identically — **no cross-process state, no new engine.**

## 4. Components (each isolated, testable)

### 4.1 Flow store — `app/automation/flow_store.py` (NEW)
Persistence for builder flows. Append/replace to `data/flow_runner/flows.jsonl` (project convention; shared bind-mount).
- `save_flow(flow: dict, by: str) -> dict` — validate shape, assign/keep `id`, stamp `updated_at`, upsert by id. Never-raise.
- `list_flows() -> list[dict]` — id, name, node/edge counts, updated_at.
- `get_flow(flow_id) -> dict | None`.
- `delete_flow(flow_id) -> bool`.

**Flow JSON shape (matches builder export):**
```json
{
  "id": "flow_ab12cd34",
  "name": "Daily lead campaign",
  "nodes": [{"id": "n1", "action": "scrape", "title": "Prospector", "args": {"batch": 3}},
            {"id": "n2", "action": "rescore", "title": "Re-score"},
            {"id": "n3", "kind": "breakpoint", "title": "Approve outreach", "question": "Drafts ready — send?"},
            {"id": "n4", "action": "cadence_run", "title": "Cadence"}],
  "edges": [{"f": "n1", "t": "n2"}, {"f": "n2", "t": "n3"}, {"f": "n3", "t": "n4"}],
  "created_by": "admin", "updated_at": "2026-06-20T..."
}
```

### 4.2 Compiler — `app/automation/flow_compiler.py` (NEW)
Pure function `compile_flow(flow) -> (process_dict | None, errors: list[str])`. **No side effects.**
Validation rules (all must pass, else return errors — deterministic, council guardrail):
1. **Non-empty:** ≥1 node.
2. **Edge integrity:** every `f`/`t` references a real node id (no dangling).
3. **Whitelist:** every task-node `action` ∈ `process_library.EXECUTORS`. Unknown action → error (no arbitrary code).
4. **Linear-only (V1):** each node has ≤1 outgoing and ≤1 incoming edge; exactly one source (indegree 0) and one sink. Reject branches/forks/joins with a clear message ("V1 linear only — node X has 2 outgoing"). Reject cycles.
5. **Topological order:** walk source→sink to produce ordered step list.
Output process dict (process_engine native shape):
```python
{"name": flow["name"], "steps": [
   {"id": "n1", "action": "scrape", "args": {...}, "max_retries": 1},
   {"kind": "breakpoint", "id": "n3", "question": "..."},
   {"id": "n4", "action": "cadence_run"},
]}
```
**Draft-safe note:** all whitelisted executors are already draft/gated. The builder also offers an explicit **Breakpoint node** (`kind:"breakpoint"`) so the admin places human-approval before any send/publish step. (Optional hardening: compiler auto-inserts a breakpoint before a configurable `SIDE_EFFECT_ACTIONS` set, e.g. `cadence_run` — V1 keeps it explicit for simplicity.)

### 4.3 Engine resolver hook — `app/agents/process_library.py` (EDIT, additive)
`get_process(key)` gains a `flow:` branch:
```python
def get_process(key):
    key = (key or "").strip()
    if key.lower().startswith("flow:"):
        from app.automation import flow_store, flow_compiler
        fl = flow_store.get_flow(key[5:])
        if not fl: return None
        proc, errs = flow_compiler.compile_flow(fl)
        return proc  # None if compile errors
    return PROCESSES.get(key.lower())
```
`list_keys()` unchanged (static only — flows listed via flow_store API). `start_run`/`advance`/`process_tick` need **no change** — they already go through `get_process`.
**Flag gate:** the `flow:` branch returns `None` when `FLOW_RUNNER` is unset → `start_run` fails cleanly → flows non-runnable until the flag is on.

### 4.4 API — reuse `growth_process.py`, add only flow-CRUD
**KEY REUSE:** `app/api/growth_process.py` ALREADY exposes the full run lifecycle for process-as-code, and `start_run` takes a process KEY. Once `get_process` resolves `flow:<id>` (§4.3), **running/approving/status of a flow needs NO new endpoint** — the existing routes work with key `flow:<id>`:
- **Run** = `POST /api/growth/process/start` `{ "process": "flow:<id>", "inputs": {...} }` → `start_run` + `process_tick.delay` (+ inline-advance fallback if worker down). *(already built)*
- **Status** = `GET /api/growth/process/run/{run_id}` → `{state: replay(), journal}`. *(already built)*
- **Approve** = `POST /api/growth/process/run/{run_id}/approve` · **Reject** = `.../reject`. *(already built)*
- **Recent runs** = `GET /api/growth/process/runs`. *(already built)*

**Only NEW endpoints = flow CRUD** (add to `app/api/growth_process.py` — same router, paths `/api/growth/flow/*`; or sibling `growth_flows.py` included the same way). All `require_admin` + gated `FLOW_RUNNER=1` (503 when off). Never-raise.
| Method | Path | Action |
|---|---|---|
| GET | `/api/growth/flows` | `flow_store.list_flows` |
| POST | `/api/growth/flow` | create/update (body = flow JSON) → validate via `compile_flow` → `flow_store.save_flow`; returns `{id, compile_errors}` |
| GET | `/api/growth/flow/{id}` | flow JSON + **compile preview** (`compile_flow` errors/steps) |
| DELETE | `/api/growth/flow/{id}` | `flow_store.delete_flow` |

Advance is **automatic** via existing `process_tick` (a Celery task that takes a `run_id` and self-requeues every 10s while RUNNING; kicked by `process/start`). No new worker job.

### 4.5 Builder UI — `frontend/explorer.html` (EDIT)
- **Save**: builder "Save" writes to server (`POST /api/automation/flows`) in addition to localStorage (localStorage = offline draft cache).
- **Run button**: in builder toolbar → `POST .../run` → returns `run_id` → start polling `GET .../runs/{run_id}` every ~2s.
- **Live status**: map `replay().steps_done` + current `step_index` → per-node state (pending/running/done/failed/waiting). Reuse existing node-animation + status colors (`.start-btn.running` style already present).
- **Breakpoint**: when status `waiting_approval`, show the `question` + Approve button → `POST .../approve` → resume polling.
- **Run history**: small panel listing recent runs (`GET .../runs?flow=`).
- Builder palette: ensure each template carries its `action` (maps to an EXECUTORS key) + add a **"Approval / Breakpoint"** palette item (`kind:"breakpoint"`).

### 4.6 Flag registry — `app/api/growth.py`
Add `"FLOW_RUNNER"` to `AUTOMATION_FLAGS` so it shows in `GET /api/growth/infra/flags`.

### 4.7 Explorer reflection — `frontend/explorer.html`
Add a `flow_runner` node (structural view) wired to `process` + `data` so the architecture map stays truthful and the reverse-sync gate documents it. `files:'flow_runner.py · flow_store.py · flow_compiler.py'`.

## 5. Data flow / lifecycle (happy path)
1. Admin builds flow → **Save** → `flows.jsonl`.
2. Admin clicks **Run** → `POST /api/growth/process/start {process:"flow:<id>"}` → `start_run` writes `run_started` to `data/process_runs/<run_id>.jsonl` + `index.jsonl` → `process_tick.delay(run_id)`.
3. `process_tick` (Celery beat) picks up active runs → `advance()` → `get_process("flow:<id>")` compiles flow → executes each task via `EXECUTORS`, writes `step_completed`/`gate_failed`.
4. At a breakpoint node → journal `breakpoint_waiting`, run pauses.
5. UI poll sees `waiting_approval` → admin **Approve** → `approve()` writes `breakpoint_approved` → next `process_tick` resumes.
6. Sink reached → `run_completed`. UI shows all nodes done.

## 6. Safety & compliance
- **Flag-gated** `FLOW_RUNNER=1` (default OFF → all routes 503, zero behaviour change).
- **Admin-only** (`require_admin` dep on every route).
- **Whitelist executors only** — no arbitrary code/HTTP; unknown action rejected at compile.
- **Draft-safe** — all 9 executors are draft/gated; side-effecting steps require an explicit human **breakpoint** (TRAI/DLT/DND/WhatsApp-ban gates remain server-side in the engines themselves, untouched).
- **Never-raise** everywhere (store/compiler/API/engine hook) — import-safe.
- **No new deps, no new container, no new DB** — reuses Postgres-less `./data` jsonl + existing Celery.

## 7. Testing plan
- `tests/test_flow_compiler.py` — unit: empty flow, dangling edge, unknown action, branch rejected, cycle rejected, valid linear → correct ordered steps, breakpoint node preserved.
- `tests/test_flow_store.py` — save/get/list/delete round-trip + bad-shape rejected (isolated tmp `data/` dir).
- `tests/test_flow_runner_api.py` — flag-off → 503; admin-required; create→run→replay (stub one EXECUTOR to avoid network); approve flow.
- Regression: `scripts/explorer_sync.py --check` green (new node + files resolve); `scripts/prod_check.py` ALL PASSED.

## 8. Rollout
1. Ship code with `FLOW_RUNNER` **OFF** → deploy (recreate app **+ worker** — process_tick runs in worker).
2. Set `FLOW_RUNNER=1` in VPS `.env` → recreate app + worker.
3. Smoke: build a 2-node `growth_audit`-style flow (optimizer→revenue_sweep, no breakpoint) → Run → confirm `completed`.
4. Then a flow with a breakpoint → confirm pause/approve/resume.
**Rollback:** unset `FLOW_RUNNER` → routes 503, no other surface touched.

## 9. File touch-list
**New:** `app/automation/flow_store.py` · `app/automation/flow_compiler.py` · `tests/test_flow_compiler.py` · `tests/test_flow_store.py` · `tests/test_flow_runner_api.py` *(`app/automation/` package already exists — no `__init__` needed)*
**Edit (additive):** `app/agents/process_library.py` (get_process `flow:` branch + flag gate) · `app/api/growth_process.py` (4 flow-CRUD routes — run/approve/status REUSED, not re-added) · `app/api/growth.py` (`FLOW_RUNNER` in `AUTOMATION_FLAGS`) · `frontend/explorer.html` (save-to-server + Run via `process/start` + live status poll + breakpoint palette item + explorer node)
**No new:** router-mount (extends existing `growth_process.py`), worker job (reuses `process_tick`), container, DB, or dependency.

## 10. Resolved during spec-grounding (no open questions)
- `app/automation/` package **exists** (`__init__.py`, agent_pool, orchestrator_pipeline, campaign_manager, scheduler) — new modules drop in there.
- `process_tick(run_id)` **takes a specific run_id and self-requeues** (countdown 10s) while RUNNING — kicked by `process/start` (`process_tick.delay`), resumed by `approve`. Confirmed in `app/api/growth_process.py:36-42,88` (+ inline-advance fallback if worker down). Flow runs advance via the **same** path.
- Full run/approve/reject/status/journal API **already exists** in `growth_process.py` — flow runs reuse it via key `flow:<id>`. Only flow-CRUD is net-new.

## 11. Road to full n8n-parity (north-star: full features in the explorer)

User goal = full n8n-like features in the explorer. That is a DAG / data-flow platform — bigger than today's LINEAR engine. Sequenced so **each phase ships independently** (council guardrail: no single ballooning plan). Each phase = its own spec → plan → ship.

| Phase | Feature | Engine lift |
|---|---|---|
| **1 (this spec, NOW)** | Linear Flow Runner — persist + run whitelisted engine-actions, human-breakpoints, live status | None (reuse process_engine) |
| **2** | **Branching / Switch / parallel / merge (DAG)** — the n8n-parity CORE | **Big** — extend engine from `step_index` to per-node DAG state |
| **3** | Triggers: manual (done) + **cron** (team_scheduler) + **event** (outbound_webhooks: lead.created/qualified, call.completed, payment.received) | Small |
| **4** | **Data-passing**: node output → downstream input (key-map / light expressions) + per-node param editor in builder | Medium |
| **5** | Richer palette: more engines as nodes (email/whatsapp/telegram/CRM — all THROUGH gated endpoints, draft-safe) + allowlisted "HTTP request" node (no compliance foot-gun) | Medium |
| **6** | Execution UX: run-history timeline, per-node log/output inspector, retry / error-routing, version/duplicate, sub-flows | Medium |
| **7 (product moat)** | Per-client flow builder in customer portal → clients build their own automations (GoHighLevel-parity) | Demand-funded |

**Why phase 1 first:** it's tiny, proves the visual→executable bridge end-to-end, and de-risks the Phase-2 DAG lift (the real engineering). Branching before the foundation works = building on sand. Full parity = destination; each phase = a shippable, reversible step toward it.
