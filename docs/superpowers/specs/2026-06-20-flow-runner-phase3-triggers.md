# Flow Runner — Phase 3: Triggers (manual + cron + event) — Design Spec

> **Status:** Approved for implementation plan (2026-06-20). Phase 1 (linear runner) is SHIPPED on `main`.
> **Decision:** Auto-triggers fire a saved flow via the EXISTING `process_engine.start_run("flow:<id>")` path — no new executor, no new run lifecycle. Cron = a single scanning Celery job (`flow_cron`). Event = one internal dispatcher (`flow_triggers.fire_event`) wired into the existing dotted-event chokepoint (`customer_webhooks.emit`).
> **Scope discipline:** ONLY add the three trigger entry-points. Branching (Phase 2) and data-passing (Phase 4) are explicitly out — seams noted, not built.

---

## 1. Why (problem)

Phase 1 made a visually-built flow **runnable** — but only by an admin clicking **Run** (`POST /api/growth/process/start {process:"flow:<id>"}`). A flow that only runs when a human pushes a button is not automation; it is a macro.

The platform already owns the two missing trigger sources:
- **Scheduled (cron):** an in-process IST scheduler (`team_scheduler.scheduler_loop`) + a durable Celery-beat mirror (`worker.py` `beat_schedule`, `staff_jobs.run_staff_job`). The closest existing pattern — `process_autostart.run_due` — already does "scan for due work → `start_run` → `process_tick.delay`, idempotent, 1/tick, flag-gated default OFF". Phase 3 cron is that exact shape, parameterised by the flow's own schedule.
- **Events:** dotted platform events (`lead.created`, `lead.qualified`, `call.completed`, `payment.received`) already flow through ONE function — `app.platform.customer_webhooks.emit(client_id, event_type, payload)` — emitted from `inquiry_hooks` (lead.created), `billing/lead_usage` (lead.qualified), `billing/usage` (call.completed). That single chokepoint is the natural place to also wake any subscribed flow.

**Phase 3 = wire a saved flow to start from cron or an event, reusing both existing rails, with auto-fire gated OFF by default so nothing fires until an admin opts in.**

## 2. Goal / Non-goals

**Goal:** A flow's saved JSON carries a `trigger` block. When auto-triggers are enabled:
- a **cron** flow auto-starts on its schedule (one start per schedule tick, deduped);
- an **event** flow auto-starts when its subscribed platform event fires, receiving the event dict as run `inputs`;
- a **manual** flow behaves EXACTLY as Phase 1 (unchanged).
The admin sets the trigger in the builder UI. All auto-started runs go through the same `process_engine` journal / breakpoints / RBAC / compliance gates — auto-fire never skips a human breakpoint before a send.

**Non-goals (seams only, not built):**
- Branching / conditionals / DAG (Phase 2) — the compiled flow stays strictly linear; a trigger only chooses *when* a run starts, never *which path*.
- Data-passing between nodes / expression mapping (Phase 4) — event payload is injected as the run's top-level `inputs` dict and nothing more; node-to-node wiring is untouched.
- Per-tenant / client-facing trigger config — admin-only, internal tool.
- New event types — subscribe only to the 4 already-emitted dotted events. No new emit points.
- Webhook-IN ("a flow triggered by an inbound HTTP call") — note as future seam; out of scope.
- Multi-tenant fan-out (one event starting N client-scoped flows with tenant filtering) — single global admin scope in Phase 3.

## 3. Architecture

```
 MANUAL (Phase 1, UNCHANGED)
   builder "Run" -> POST /api/growth/process/start {process:"flow:<id>"}
       -> process_engine.start_run -> process_tick.delay

 CRON (NEW)  — one scanning job, reuses process_autostart shape
   worker.py beat  ──crontab(*/5)──>  run_staff_job("flow_cron")
   team_scheduler  ──5-min slot────>  _run_job("flow_cron")
       -> flow_triggers.run_cron_due()
            for each saved flow where trigger.type=="cron" AND due-this-tick AND not-already-fired-this-tick:
               process_engine.start_run("flow:<id>", inputs={"_trigger":"cron","fired_at":...})
               process_tick.delay(run_id)
            state-file dedupe: data/flow_runner/cron_state.json  {flow_id: last_fire_slot}

 EVENT (NEW)  — one dispatcher at the existing dotted-event chokepoint
   inquiry_hooks / billing.lead_usage / billing.usage
       -> customer_webhooks.emit(cid, "lead.created"|"lead.qualified"|"call.completed"|"payment.received", payload)
             |
             +--(additive tail call, never-raise)--> flow_triggers.fire_event(event_type, payload, client_id)
                     for each saved flow where trigger.type=="event" AND trigger.event==event_type:
                        loop-guard: skip if payload carries _flow_origin (event came FROM a flow run)
                        process_engine.start_run("flow:<id>", inputs={**payload, "_trigger":"event", "_event":event_type})
                        process_tick.delay(run_id)
```

**Key reuse:** the run lifecycle (`start_run` / `process_tick` / `advance` / breakpoints / `replay`) is identical for all three triggers. A trigger is purely *a caller of `start_run("flow:<id>", inputs)`*. The compiler, resolver hook (`get_process` `flow:` branch), and `FLOW_RUNNER` gate from Phase 1 are unchanged.

**Gate layering:**
- `FLOW_RUNNER` (Phase 1) — master: flows non-runnable at all when off (resolver returns `None`).
- `FLOW_AUTO_TRIGGERS` (NEW sub-flag, default OFF) — gates cron scanning AND event dispatch. With `FLOW_RUNNER=1` but `FLOW_AUTO_TRIGGERS=0`, flows are still manually runnable but nothing auto-fires. **This is the ban/cost-safety switch.**

## 4. Components (exact paths)

### 4.1 `app/automation/flow_triggers.py` (NEW) — the only new logic module
Pure, import-safe, never-raise. Holds cron discovery+firing and the event dispatcher.

```python
# app/automation/flow_triggers.py
from __future__ import annotations
import json, os
from datetime import datetime, timezone, timedelta
from typing import Any
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
_IST = timezone(timedelta(hours=5, minutes=30))
_STATE = os.path.join("data", "flow_runner", "cron_state.json")   # {flow_id: last_fire_slot}
_MAX_STARTS_PER_TICK = 3          # flood guard across ALL cron flows per scan
_TICK_MINUTES = 5                 # must match the beat/scheduler scan cadence

def _auto_on() -> bool:
    return os.getenv("FLOW_AUTO_TRIGGERS", "0").strip().lower() in ("1", "true", "yes")

def _flow_runner_on() -> bool:
    return os.getenv("FLOW_RUNNER", "0").strip().lower() in ("1", "true", "yes")
```

Functions:
- `run_cron_due() -> dict` — scan + fire due cron flows (see §6). Called by the `flow_cron` staff-job.
- `fire_event(event_type: str, payload: dict, client_id: str = "") -> dict` — dispatch one platform event to subscribed event-flows (see §6.2). Called from the `customer_webhooks.emit` tail.
- `_cron_due(trigger: dict, now_ist: datetime) -> str | None` — pure: returns the *slot key* this flow should fire in for `now`, else `None`. Testable in isolation.
- `_read_state()/_write_state()` — JSON load/atomic-replace of `cron_state.json` (mirror `flow_store._rewrite` tmp+`os.replace`).

### 4.2 `app/tasks/staff_jobs.py` (EDIT, additive) — register `flow_cron`
Add `"flow_cron"` to the `STAFF_JOBS` tuple. No new task function — `run_staff_job` dispatches to `team_scheduler._run_job("flow_cron")`.

### 4.3 `app/platform/team_scheduler.py` (EDIT, additive)
- Add `"flow_cron": None` to `_last_ran`.
- Add a dispatch branch in `_run_job_inner`:
  ```python
  elif job == "flow_cron":
      from app.automation import flow_triggers
      flow_triggers.run_cron_due()   # sync, never-raise, self-gated (FLOW_RUNNER + FLOW_AUTO_TRIGGERS)
  ```
- Add the 5-minute slot fire in `scheduler_loop()` (in-process / rollback path), mirroring the `growth` slot pattern:
  ```python
  fc_slot = now.strftime("%Y-%m-%d %H:") + f"{(now.minute // _TICK_MINUTES) * _TICK_MINUTES:02d}"
  if _last_ran.get("flow_cron") != fc_slot:
      _last_ran["flow_cron"] = fc_slot
      await _run_job("flow_cron")
  ```
  (5-min granularity is sufficient for cron flows; finer-grained = not a Phase-3 need.)

### 4.4 `app/worker.py` (EDIT, additive) — durable beat entry
Add to `beat_schedule` (inside the `staff-*` block so the `ENABLE_LEGACY_BEAT` filter keeps it):
```python
"staff-flow-cron": {
    "task": "app.tasks.staff_jobs.run_staff_job",
    "schedule": crontab(minute="*/5"),
    "args": ("flow_cron",),
},
```

### 4.5 `app/platform/customer_webhooks.py` (EDIT, additive) — event chokepoint tail
In `emit()`, after the existing customer-webhook fan-out loop (just before `return`), add a never-raise tail that wakes subscribed flows. This is the ONLY event wiring change — all 3 dotted-event call sites already route through this one function, so no edit to `inquiry_hooks.py` / `billing/*` is needed.
```python
# Phase-3 Flow Runner event trigger (additive, self-gated, never-raise).
try:
    from app.automation import flow_triggers
    flow_triggers.fire_event(event_type, payload, cid)
except Exception:
    pass
```
**Important:** this tail runs **regardless of `customer_webhooks.enabled()`** — flow triggers must not depend on a customer having registered an HTTP webhook. Because `emit()` early-returns when `not enabled()`, the tail is placed in a thin wrapper OR `fire_event` is also invoked from the early-return branch. Implementation: factor the tail into a `_after_emit(event_type, payload, cid)` helper called on BOTH the disabled-early-return and the normal-return paths. `fire_event` self-gates on `FLOW_RUNNER` + `FLOW_AUTO_TRIGGERS`, so it is inert until both flags are on.

### 4.6 `app/automation/flow_store.py` (EDIT, additive) — persist `trigger`
`save_flow` currently drops unknown keys. Add `trigger` to the persisted record (validated, defaulted to manual):
```python
"trigger": _norm_trigger(flow.get("trigger")),
```
with a local `_norm_trigger(t)`:
```python
def _norm_trigger(t):
    t = t if isinstance(t, dict) else {}
    typ = str(t.get("type") or "manual").lower()
    if typ not in ("manual", "cron", "event"):
        typ = "manual"
    out = {"type": typ}
    if typ == "cron":
        out["cron"] = str(t.get("cron") or "").strip()[:64]      # "*/5 * * * *" OR "HH:MM" IST
    if typ == "event":
        out["event"] = str(t.get("event") or "").strip()[:40]    # one of the 4 dotted events
    return out
```
Add `list_flows()` row field `"trigger": rec.get("trigger", {}).get("type", "manual")` so the UI/API can show it.

### 4.7 `app/api/growth_process.py` (EDIT, additive) — surface trigger in CRUD
- `FlowIn` pydantic model gains `trigger: dict | None = None` (passes through to `save_flow`).
- `flow_get` / `flow_save` responses already return the full flow dict → `trigger` rides along automatically once persisted. No new route.
- Optional helper route (nice-to-have, not required): `GET /api/growth/flows/triggers` returning `{cron:[...], event:[...]}` summary for an ops view. Keep `require_admin` + `FLOW_RUNNER` gate.

### 4.8 `app/api/automation_flags.py` (EDIT, additive)
Add `"FLOW_AUTO_TRIGGERS"` to `AUTOMATION_FLAGS` (right under `FLOW_RUNNER`) so it shows in `GET /api/growth/infra/flags`.

### 4.9 `frontend/explorer.html` (EDIT, additive) — builder trigger picker
In the builder toolbar/side panel, add a **Trigger** control (3 radios: Manual / Cron / Event):
- Manual → no extra fields (default).
- Cron → text input for `cron` (placeholder `*/15 * * * *  or  09:30`), tiny helper text "IST; one start per tick".
- Event → `<select>` of the 4 events (`lead.created`, `lead.qualified`, `call.completed`, `payment.received`).
The trigger object is included in the `POST /api/growth/flow` body and shown in the flow list ("⏰ cron" / "⚡ event: lead.created" / "manual" badge). Save still writes localStorage draft + server (Phase 1 behaviour). No change to Run button. Show a small notice when `FLOW_AUTO_TRIGGERS` is off: "Auto-triggers are disabled platform-wide — this flow will not fire automatically until enabled."

## 5. Data model

Flow JSON gains one optional block (everything else from Phase 1 unchanged):
```json
{
  "id": "flow_ab12cd34",
  "name": "Daily lead campaign",
  "trigger": { "type": "cron", "cron": "*/30 * * * *" },
  "nodes": [ ... ],
  "edges": [ ... ],
  "updated_at": "2026-06-20T..."
}
```
`trigger` shapes:
| type | extra field | meaning |
|---|---|---|
| `manual` | — | Phase-1 behaviour; only the Run button / API starts it. |
| `cron` | `cron` (string) | 5-field cron expr **OR** `HH:MM` (IST). Fires on matching 5-min scan tick. |
| `event` | `event` (string) | One of the 4 dotted events. Fires when that event is emitted. |

Cron-string parsing (NO new dep — Celery's `crontab` is import-only inside the worker, not in the web process; we parse minimally ourselves):
- `HH:MM` → fire in the 5-min slot covering that IST minute, once/day.
- 5-field `m h dom mon dow` → support `*`, `*/N`, comma-lists, and exact ints for minute+hour (the realistic subset). Day-of-month / month / day-of-week supported as `*` or exact/`,`-list. Anything unparseable → flow is **inert** (logged once, never fires) — fail-closed, never crash-loop.

State file (cron dedupe):
```json
// data/flow_runner/cron_state.json
{ "flow_ab12cd34": "2026-06-20 09:30", "flow_xy99": "2026-06-20" }
```
Slot key = `"%Y-%m-%d %H:MM"` (MM floored to 5-min) for interval crons, or `"%Y-%m-%d"` for once-daily `HH:MM`. A flow fires only when its computed due-slot differs from its stored last-fire slot — this is the project's "success-marked state-file" dedupe pattern (same idea as `_last_ran` in `team_scheduler`).

## 6. Trigger discovery + firing logic

### 6.1 Cron — `run_cron_due()`
```
if not (_flow_runner_on() and _auto_on()): return {"skipped":"gated"}
now = datetime.now(_IST)
state = _read_state()
started = 0
for flow in flow_store.list_flows_full():           # need raw flows incl. trigger
    trig = flow.get("trigger") or {}
    if trig.get("type") != "cron": continue
    slot = _cron_due(trig, now)                      # None if not due this tick
    if not slot: continue
    if state.get(flow["id"]) == slot: continue       # already fired this slot (DEDUPE)
    # compile-gate: don't start an un-runnable flow
    proc, errs = flow_compiler.compile_flow(flow)
    if errs: continue
    if started >= _MAX_STARTS_PER_TICK: break        # flood cap
    r = process_engine.start_run(f"flow:{flow['id']}", {"_trigger":"cron","fired_at":now.isoformat()})
    if r.get("ok"):
        process_tick.delay(r["run_id"])              # worker advance; inline-advance not used (sync scan ctx)
        state[flow["id"]] = slot                      # MARK fired (success-marked)
        started += 1
_write_state(state)                                  # atomic tmp+os.replace
return {"ok":True,"started":started}
```
- **Discovery mechanism chosen: a single periodic scanning job** (`flow_cron`, every 5 min via Celery beat + in-process slot), NOT per-flow dynamic beat registration. Rationale: matches the live `process_autostart` pattern exactly; no runtime mutation of Celery's `beat_schedule` (which would need a beat restart and is fragile); one job scans all cron flows. Cheap: `list_flows` is a small JSONL read.
- **Dedupe** = state-file slot comparison (one fire per slot per flow), surviving restarts. State written only AFTER a successful `start_run` (success-marked), so a crash mid-scan re-attempts un-fired flows next tick (at-least-once is acceptable for draft-safe flows; the slot mark makes it effectively once).
- **`_MAX_STARTS_PER_TICK = 3`** caps cost if many cron flows align on one slot. Remaining due flows fire on the next 5-min tick (their slot key persists; the cap just defers them).

### 6.2 Event — `fire_event(event_type, payload, client_id)`
```
if not (_flow_runner_on() and _auto_on()): return {"skipped":"gated"}
if payload.get("_flow_origin"): return {"skipped":"loop_guard"}   # event came from a flow run
fired = 0
for flow in flow_store.list_flows_full():
    trig = flow.get("trigger") or {}
    if trig.get("type") != "event" or trig.get("event") != event_type: continue
    proc, errs = flow_compiler.compile_flow(flow)
    if errs: continue
    # per-flow short-window dedupe (same event payload id within N s) — see §7
    if _recently_fired(flow["id"], payload): continue
    inputs = {**(payload or {}), "_trigger":"event", "_event":event_type, "_flow_origin":flow["id"]}
    r = process_engine.start_run(f"flow:{flow['id']}", inputs)
    if r.get("ok"):
        process_tick.delay(r["run_id"])
        _mark_fired(flow["id"], payload)
        fired += 1
    if fired >= _MAX_STARTS_PER_TICK: break
return {"ok":True,"fired":fired}
```
- **Subscription mechanism chosen: an internal subscriber registry derived from the saved flows themselves** (`trigger.type=="event"`), dispatched by ONE central hook at the existing dotted-event chokepoint (`customer_webhooks.emit` tail). No separate subscription store, no edit to scattered emit sites, no new HTTP path. The flow's own `trigger.event` field IS the subscription.
- The event `payload` becomes the run `inputs` (Phase-4 seam: downstream nodes will later read these; today nodes ignore inputs — that's fine, the data simply rides in the journal).
- `client_id` is recorded in inputs for future tenant-scoping but Phase 3 does not filter on it (global admin scope).

## 7. Safety / loop-guards

**TOP RISK — event self-trigger loop:** a flow subscribed to `lead.qualified` whose body runs an executor that itself causes a `lead.qualified` emit → infinite re-trigger → run/queue flood. Guards (defense-in-depth):
1. **Origin stamp:** every event-triggered run gets `inputs._flow_origin=<flow_id>`. Any platform event emitted *from within* a flow run carries `_flow_origin` in its payload (the engine threads run-inputs context where it emits). `fire_event` **drops any event whose payload has `_flow_origin`** → a flow can never re-arm event flows. (Implementation note: the whitelisted EXECUTORS are draft-safe and mostly do not emit these 4 events; the stamp is belt-and-suspenders for the ones that might via `inquiry_hooks`.)
2. **Per-flow short-window dedupe:** `_recently_fired(flow_id, payload)` keyed on `(flow_id, payload.get("lead_id"|"lead_ref"|"campaign_id"|hash))` within a 60 s window (tiny in-memory + state-file ring, bounded), so a burst of identical events starts at most one run per flow per window.
3. **`_MAX_STARTS_PER_TICK` cap** on both cron and event dispatch bounds worst-case starts per invocation.
4. **`process_engine` is the backstop:** every run is journaled, advances only via `process_tick` (10 s cadence, single chain per run_id), and a flow with a side-effecting step still **pauses at its human breakpoint** before any send — an auto-fired flow cannot auto-send. `process_engine.ensure_alive` already prevents stuck-RUNNING accumulation.

**Other safety:**
- **Double-gated, default OFF:** `FLOW_RUNNER` (master) AND `FLOW_AUTO_TRIGGERS` (auto-fire) both required. Either off → zero auto-fires. This is the ban/cost switch.
- **Compliance intact:** TRAI/DND/AI-disclosure/10am-7pm and WhatsApp/email caps live inside the executors/engines, untouched. A trigger only decides *when start_run is called*; it cannot bypass any downstream gate or breakpoint.
- **Admin-only:** trigger config flows through the existing `require_admin` flow-CRUD routes; no public surface added.
- **Draft-safe:** whitelisted executors only (Phase-1 compiler invariant); auto-fire changes nothing about what a flow may do.
- **Never-raise / import-safe:** every new function try/excepts; `fire_event` is a fire-and-forget tail that can never break `customer_webhooks.emit` or the billing/inquiry path; `run_cron_due` can never break the scheduler tick.
- **No new deps:** cron parsing is a minimal hand-rolled subset; no `croniter`. No new container, DB, or queue.
- **Single-instance:** cron scan runs under the existing scheduler single-instance lock (in-process) / single beat owner (Celery) — no double-fire across workers. The state-file slot mark is the cross-restart backstop.

## 8. Testing plan

- `tests/test_flow_triggers_cron.py` — `_cron_due` unit matrix: `HH:MM` once-daily fires in correct slot + not twice same day; `*/15` interval fires on aligned slots only; `*` minute; comma-list hour; unparseable → `None` (inert); dedupe (same slot → second scan no-op); `_MAX_STARTS_PER_TICK` cap defers extras; gated-off → `{"skipped":"gated"}` and zero `start_run` calls (monkeypatch `start_run`).
- `tests/test_flow_triggers_event.py` — `fire_event` matches only `trigger.type=="event" && trigger.event==X`; injects payload as inputs; `_flow_origin` present → loop-guard skip (CRITICAL test); short-window dedupe on repeat payload; gated-off → no `start_run`; flag-on path calls `start_run("flow:<id>", inputs)` once (stub engine).
- `tests/test_flow_store_trigger.py` — `save_flow` round-trips `trigger`; bad/missing trigger → normalised to `{"type":"manual"}`; invalid type → manual; `list_flows` row exposes trigger type.
- `tests/test_customer_webhooks_flow_tail.py` — `emit` calls `flow_triggers.fire_event` for a supported event (monkeypatch) AND still calls it on the disabled-early-return path; never raises if `fire_event` throws.
- Regression: existing `tests/test_flow_*.py` (Phase 1) stay green (manual path unchanged); `tests/test_customer_webhooks.py` green; `tests/test_process_autostart.py` untouched.
- Verify: `python scripts/prod_check.py` ALL PASSED; `.venv\Scripts\python.exe -m pytest tests/test_flow_triggers_cron.py tests/test_flow_triggers_event.py tests/test_flow_store_trigger.py tests/test_customer_webhooks_flow_tail.py -q`.

## 9. Rollout

1. Ship code with `FLOW_AUTO_TRIGGERS` **unset** (and `FLOW_RUNNER` at its current state). Recreate app **+ worker + scheduler/beat** (cron job lives in worker/beat). Zero behaviour change — no flow auto-fires.
2. Set `FLOW_RUNNER=1` (if not already) → flows runnable manually (Phase 1).
3. Build a trivial cron flow (e.g. `optimizer` → `revenue_sweep`, no breakpoint, `trigger.cron="*/5 * * * *"`). Set `FLOW_AUTO_TRIGGERS=1` → confirm exactly one run starts per 5-min slot (`GET /api/growth/process/runs`), and a second scan in the same slot does NOT double-fire (check `cron_state.json`).
4. Build an event flow on `lead.qualified` with a breakpoint before any send → emit a test `lead.qualified` → confirm one run starts, pauses at breakpoint, and emitting again within 60 s does NOT start a second run (dedupe), and the run's own downstream does NOT re-trigger (loop-guard).
**Rollback:** unset `FLOW_AUTO_TRIGGERS` → all auto-fire stops instantly; manual + Phase-1 surface untouched. Unset `FLOW_RUNNER` → full Phase-1 rollback.

## 10. File touch-list

**New:**
- `app/automation/flow_triggers.py` (cron scan + event dispatch + cron parse + state)
- `tests/test_flow_triggers_cron.py`
- `tests/test_flow_triggers_event.py`
- `tests/test_flow_store_trigger.py`
- `tests/test_customer_webhooks_flow_tail.py`

**Edit (additive, never-raise):**
- `app/automation/flow_store.py` — persist + normalise `trigger`; `list_flows` exposes trigger type; add `list_flows_full()` (raw flows incl. trigger) for the scanner.
- `app/api/growth_process.py` — `FlowIn.trigger` field (passes through); optional `GET /flows/triggers` summary.
- `app/api/automation_flags.py` — add `FLOW_AUTO_TRIGGERS`.
- `app/tasks/staff_jobs.py` — add `"flow_cron"` to `STAFF_JOBS`.
- `app/platform/team_scheduler.py` — `_last_ran["flow_cron"]`, `_run_job_inner` branch, 5-min slot fire.
- `app/worker.py` — `staff-flow-cron` beat entry (`crontab(minute="*/5")`).
- `app/platform/customer_webhooks.py` — `_after_emit` tail calling `flow_triggers.fire_event` on both emit return paths.
- `frontend/explorer.html` — builder trigger picker (radios + cron input + event select), flow-list trigger badge, auto-triggers-off notice.

**No new:** router mount, Celery task function, container, DB, or dependency. (`flow_cron` reuses `run_staff_job`; events reuse `customer_webhooks.emit`.)

## 11. Open questions

1. **Cron timezone in the durable path:** `worker.py` sets `celery_app.conf.timezone = Asia/Kolkata`, but our scan reads `datetime.now(_IST)` itself and parses cron as IST — consistent. Confirm beat invokes the `*/5` task on its own clock (it does); our per-flow due-check is timezone-independent of beat. **Resolved: parse + compare entirely in IST inside `run_cron_due`; beat cadence only needs to be ≤5 min.**
2. **Should event flows be tenant-scoped now?** Phase 3 ignores `client_id` (global admin). If a future per-client builder lands (Phase 7), `fire_event` must filter `trigger.client_id == client_id`. **Decision: record `client_id` in inputs now, filter later — no scope creep.**
3. **`_flow_origin` threading:** confirm the executors that can emit dotted events (via `inquiry_hooks`) actually receive run-context to stamp `_flow_origin` on outgoing payloads. If not cleanly threadable in Phase 3, the per-flow short-window dedupe (guard #2) + breakpoint backstop still prevent runaway; the origin stamp is the *primary* guard but degrades safely to dedupe. **Flag for plan-time spike.**
4. **Cron parse scope:** hand-rolled parser supports minute+hour `* /N , int` plus `HH:MM`; dom/mon/dow only `*`/exact/list. Is that enough for admin needs, or do we accept `croniter` (would be a new dep — currently rejected)? **Default: ship the subset; revisit only if an admin needs dow scheduling.**
```
```

---

## Seams left for later phases (do NOT build here)
- **Phase 2 (branching):** a trigger picks *when* to start; the compiled process stays linear. When DAG lands, `start_run` inputs are unchanged — triggers need no rework.
- **Phase 4 (data-passing):** event payload already lands in run `inputs`; Phase 4 will let nodes *read* it. The injection point (`fire_event` inputs dict) is the forward-compatible seam.
- **Webhook-IN trigger:** a `trigger.type=="webhook"` starting a flow from an inbound signed POST — natural 4th trigger; add a `/api/growth/flow/{id}/trigger` admin-signed endpoint later. Not in Phase 3.
