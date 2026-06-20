# Flow Runner — Phase 3 (Triggers: manual + cron + event) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use `- [ ]`. Built TDD on branch `flow-runner-phase2-5-specs` (has Phase 1+2). Spec: `docs/superpowers/specs/2026-06-20-flow-runner-phase3-triggers.md`.

**Goal:** A saved flow carries a `trigger` block; with `FLOW_AUTO_TRIGGERS=1` a cron flow auto-starts on its schedule (deduped) and an event flow auto-starts when its subscribed platform event fires — both reusing the existing run lifecycle. Manual = Phase-1 unchanged. Double-gated OFF by default.

**Architecture:** One new logic module `flow_triggers.py` (cron scan + event dispatch + minimal cron parser + state dedupe). Cron = a `flow_cron` staff-job scanned every 5 min (Celery beat + in-process slot). Event = a never-raise tail in the single dotted-event chokepoint `customer_webhooks.emit`. Triggers are just callers of `flow_dispatch.start("flow:<id>", inputs)` → reuses journal/breakpoints/RBAC/compliance and routes linear→process_engine, dag→dag_engine.

**Tech Stack:** Python 3.12, Celery (existing `run_staff_job`/`process_tick`), pytest, vanilla JS. No new dep/container/DB/route/task.

## Global Constraints
- Windows venv: `.venv\Scripts\python.exe`; Windows git `C:\PROGRA~1\Git\cmd\git.exe`. Read before Edit; no parallel-edit same file.
- Never-raise + import-safe everywhere; trigger code can NEVER break `customer_webhooks.emit`, billing, inquiry, or the scheduler tick.
- **Double-gated, default OFF:** `FLOW_RUNNER` (master) AND `FLOW_AUTO_TRIGGERS` (auto-fire). Either off → zero auto-fire.
- **Phase-2 reconciliations (spec predates Phase 2 build — MUST apply):**
  1. `flow_compiler.compile_flow(flow)` returns a **3-tuple** `(result, errors, kind)` → unpack accordingly in the scanner.
  2. Fire via **`flow_dispatch.start(f"flow:{id}", inputs)`** (NOT `process_engine.start_run`) so cron/event correctly fire **dag** flows too; then `process_tick.delay(run_id)`.
  3. Event tail goes at the **top of `emit`** (single never-raise call) — `emit` is async and early-returns when `not enabled()`, so a single top call fires regardless of `CUSTOMER_WEBHOOKS`.
- Compliance untouched: a trigger only decides *when* `start` is called; breakpoints/DND/DLT/caps stay server-side. Auto-fired flows still pause at human breakpoints before any send.
- Admin-only (trigger config rides existing `require_admin` CRUD). No new public surface.
- 4 subscribable events ONLY (already emitted): `lead.created`, `lead.qualified`, `call.completed`, `payment.received`.

---

### P3-T1: `flow_store` persists `trigger` + `list_flows_full()`
**Files:** Modify `app/automation/flow_store.py`; Test `tests/test_flow_store_trigger.py`.
- `save_flow` rec gains `"trigger": _norm_trigger(flow.get("trigger"))` (normalised: type∈{manual,cron,event}, cron str ≤64, event str ≤40; bad→manual).
- New `list_flows_full() -> list[dict]` = `list(_read_all().values())` (raw flows incl. trigger, for the scanner).
- `list_flows()` row gains `"trigger": rec.get("trigger", {}).get("type", "manual")`.
- Tests: round-trip trigger; missing/invalid → `{"type":"manual"}`; cron/event fields persist; `list_flows` row exposes type; `list_flows_full` returns full nodes/edges/trigger.

### P3-T2: `flow_triggers.py` — cron parser + scan + event dispatch
**Files:** Create `app/automation/flow_triggers.py`; Tests `tests/test_flow_triggers_cron.py`, `tests/test_flow_triggers_event.py`.
- Pure `_cron_due(trigger, now_ist) -> slot_key|None`: `HH:MM` once-daily (slot covers that 5-min, key=`%Y-%m-%d`); 5-field `m h dom mon dow` matched at **5-min slot granularity** (any minute in slot matches the minute field — robust to scan jitter), key=`%Y-%m-%d %H:MM`. dow uses cron 0=Sun (`isoweekday()%7`). Unparseable → `None` (inert, fail-closed).
- `_match(field, value, lo, hi)`: `*`, `*/N`, comma-list, `a-b` range, exact int.
- `run_cron_due()`: gated (`_flow_runner_on() and _auto_on()`); scan `list_flows_full()`; for cron+due+not-fired-this-slot → `compile_flow` (3-tuple, skip if errs) → `flow_dispatch.start` → `process_tick.delay` → mark slot in `cron_state.json` (atomic). Cap `_MAX_STARTS_PER_TICK=3`.
- `fire_event(event_type, payload, client_id="")`: gated; loop-guard skip if `payload._flow_origin`; per-flow 60s dedupe (`_recently_fired`/`_mark_fired`, in-memory bounded); match `trigger.type=="event" and trigger.event==event_type`; `compile_flow` gate; `inputs={**payload,"_trigger":"event","_event":event_type,"_flow_origin":flow_id}`; `flow_dispatch.start` + `process_tick.delay`; cap 3.
- Tests (cron): HH:MM once-daily fires its slot + not twice same day; `*/15` only aligned slots; `*` minute; comma-list hour; unparseable→None; dedupe (same slot→no-op); cap defers; gated-off→`{"skipped":"gated"}` + zero start (monkeypatch `flow_dispatch.start`).
- Tests (event): matches only subscribed event; injects payload as inputs; `_flow_origin`→loop-guard skip (CRITICAL); short-window dedupe; gated-off→no start; flag-on calls `flow_dispatch.start` once (stub).

### P3-T3: event chokepoint tail in `customer_webhooks.emit`
**Files:** Modify `app/platform/customer_webhooks.py`; Test `tests/test_customer_webhooks_flow_tail.py`.
- At the TOP of `async def emit(...)`, before `if not enabled()`, add never-raise:
  ```python
  try:
      from app.automation import flow_triggers
      flow_triggers.fire_event(event_type, payload or {}, (client_id or "").strip())
  except Exception:
      pass
  ```
- Tests: `emit` calls `fire_event` for a supported event even when `CUSTOMER_WEBHOOKS` off (monkeypatch fire_event, assert called); `emit` never raises if `fire_event` throws.

### P3-T4: `flow_cron` scheduler wiring
**Files:** Modify `app/tasks/staff_jobs.py`, `app/platform/team_scheduler.py`, `app/worker.py`.
- `staff_jobs.STAFF_JOBS`: append `"flow_cron"`.
- `team_scheduler`: `_last_ran["flow_cron"]=None`; `_run_job_inner` elif `job=="flow_cron"` → `from app.automation import flow_triggers; flow_triggers.run_cron_due()`; in `scheduler_loop`, after the growth slot, add 5-min `flow_cron` slot fire (`fc_slot=%Y-%m-%d %H:` + floored-5; `if _last_ran.get("flow_cron")!=fc_slot: _last_ran["flow_cron"]=fc_slot; await _run_job("flow_cron")`).
- `worker.py` beat (inside `staff-*` block): `"staff-flow-cron": {"task":"app.tasks.staff_jobs.run_staff_job","schedule":crontab(minute="*/5"),"args":("flow_cron",)}`.
- Verify: import smoke + `tests/test_process_autostart.py` green.

### P3-T5: API + flag + builder UI
**Files:** Modify `app/api/growth_process.py`, `app/api/automation_flags.py`, `frontend/explorer.html`.
- `FlowIn` gains `trigger: dict | None = None` (passes to `save_flow`; rides back in flow dict).
- `automation_flags.AUTOMATION_FLAGS`: add `"FLOW_AUTO_TRIGGERS"` under `FLOW_RUNNER`.
- explorer builder: Trigger control (Manual/Cron/Event radios; cron text input; event select of 4); include `trigger` in `_frPayload`; flow-list trigger badge; "auto-triggers off" notice. Update flow_runner node `files:` to add `flow_triggers.py`.
- Verify: `tests/test_flow_api.py` green (trigger rides through).

### P3-T6: green gates
- `.venv\Scripts\python.exe scripts/explorer_sync.py --check` → [OK].
- `.venv\Scripts\python.exe scripts/prod_check.py` → ALL PASSED.
- Full flow suite + new trigger suites green.

## Rollout
Ship `FLOW_AUTO_TRIGGERS` unset → recreate app+worker+scheduler (cron lives in worker/beat). Zero auto-fire. Then `FLOW_AUTO_TRIGGERS=1` → smoke a `*/5` cron flow (one start/slot, no double-fire) + an event flow with breakpoint (one start, dedupe, loop-guard). Rollback = unset `FLOW_AUTO_TRIGGERS`.
