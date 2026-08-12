"""Flow Runner — Phase 3 triggers (cron scan + event dispatch).

Pure logic + thin firing seam. A trigger only decides WHEN a saved flow starts;
it reuses the full run lifecycle via flow_dispatch.start (linear->process_engine,
dag->dag_engine) + process_tick. Double-gated (FLOW_RUNNER + FLOW_AUTO_TRIGGERS),
default OFF. Import-safe, never raises — can never break customer_webhooks.emit,
billing, inquiry, or the scheduler tick.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_IST = timezone(timedelta(hours=5, minutes=30))
_STATE = os.path.join("data", "flow_runner", "cron_state.json")  # {flow_id: last_fire_slot}
_MAX_STARTS_PER_TICK = 3  # flood guard across ALL flows per scan/dispatch
_TICK_MINUTES = 5  # must match the beat/scheduler scan cadence
_EVENT_WINDOW_S = 60.0  # per-flow event dedupe window
_EVENT_FIRED: dict[str, float] = {}  # in-memory bounded dedupe ring (reset-able in tests)


def _on(name: str) -> bool:
    return os.getenv(name, "0").strip().lower() in ("1", "true", "yes")


def _flow_runner_on() -> bool:
    return _on("FLOW_RUNNER")


def _auto_on() -> bool:
    return _on("FLOW_AUTO_TRIGGERS")


# ---------------------------------------------------------------- cron parser (minimal, no dep)


def _match(field: str, value: int, lo: int, hi: int) -> bool:
    """Match a single cron field against `value`. Supports * , */N , a-b , int (comma-list)."""
    field = (field or "").strip()
    if field == "*":
        return True
    for part in field.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("*/"):
            try:
                step = int(part[2:])
            except ValueError:
                continue
            if step > 0 and (value - lo) % step == 0:
                return True
        elif "-" in part:
            try:
                a, b = part.split("-", 1)
                if int(a) <= value <= int(b):
                    return True
            except ValueError:
                continue
        else:
            try:
                if int(part) == value:
                    return True
            except ValueError:
                continue
    return False


def _cron_due(trigger: dict, now: datetime) -> str | None:
    """Return the slot-key this cron flow should fire in for `now` (IST), else None.
    Pure + fail-closed: any unparseable cron => None (inert, never crash)."""
    try:
        cron = str((trigger or {}).get("cron") or "").strip()
        if not cron:
            return None
        slot_min = (now.minute // _TICK_MINUTES) * _TICK_MINUTES
        # "HH:MM" once-daily (IST)
        if ":" in cron and len(cron.split()) == 1:
            hh_s, mm_s = cron.split(":", 1)
            hh, mm = int(hh_s), int(mm_s)
            if not (0 <= hh < 24 and 0 <= mm < 60):
                return None
            target_slot = (mm // _TICK_MINUTES) * _TICK_MINUTES
            if now.hour == hh and slot_min == target_slot:
                return now.strftime("%Y-%m-%d")  # once-per-day slot key
            return None
        # 5-field "m h dom mon dow"
        parts = cron.split()
        if len(parts) != 5:
            return None
        m_f, h_f, dom_f, mon_f, dow_f = parts
        # minute matched at 5-min slot granularity (robust to scan jitter)
        minute_ok = any(_match(m_f, mm, 0, 59) for mm in range(slot_min, slot_min + _TICK_MINUTES))
        cron_dow = now.isoweekday() % 7  # cron: 0=Sun..6=Sat
        if (
            minute_ok
            and _match(h_f, now.hour, 0, 23)
            and _match(dom_f, now.day, 1, 31)
            and _match(mon_f, now.month, 1, 12)
            and _match(dow_f, cron_dow, 0, 6)
        ):
            return now.strftime("%Y-%m-%d %H:") + f"{slot_min:02d}"
        return None
    except Exception:
        return None


# ---------------------------------------------------------------- state (cron slot dedupe)


def _read_state() -> dict:
    try:
        if os.path.exists(_STATE):
            with open(_STATE, encoding="utf-8") as f:
                d = json.load(f)
                return d if isinstance(d, dict) else {}
    except Exception:
        pass
    return {}


def _write_state(state: dict) -> None:
    try:
        os.makedirs(os.path.dirname(_STATE), exist_ok=True)
        tmp = _STATE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, _STATE)
    except Exception as e:
        logger.debug(f"[flow_triggers] state write failed: {e}")


# ---------------------------------------------------------------- firing seam (testable)


def _fire(flow_id: str, inputs: dict) -> bool:
    """Start a saved flow via the dispatcher (routes linear/dag) + enqueue advance.
    Never raises. Returns True if a run started."""
    try:
        from app.agents import flow_dispatch

        r = flow_dispatch.start(f"flow:{flow_id}", inputs)
        if not r.get("ok"):
            return False
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(r["run_id"])
        except Exception:
            pass  # worker down — ensure_alive/watchdog will revive
        return True
    except Exception as e:
        logger.debug(f"[flow_triggers] fire {flow_id} failed: {e}")
        return False


def _compiles(flow: dict) -> bool:
    try:
        from app.automation import flow_compiler

        _res, errs, _kind = flow_compiler.compile_flow(flow)  # 3-tuple (Phase 2)
        return not errs
    except Exception:
        return False


# ---------------------------------------------------------------- cron scan


def run_cron_due(now: datetime | None = None) -> dict:
    """Scan saved flows; start due cron flows (one per slot, deduped). Never raises."""
    try:
        if not (_flow_runner_on() and _auto_on()):
            return {"skipped": "gated"}
        from app.automation import flow_store

        now = now or datetime.now(_IST)
        state = _read_state()
        started = 0
        per_owner: dict[str, int] = {}  # PER-OWNER flood cap (was a global break that
        # permanently starved overflow single-slot crons — they don't re-match next tick)
        for flow in flow_store.list_flows_full():
            trig = flow.get("trigger") or {}
            if trig.get("type") != "cron":
                continue
            slot = _cron_due(trig, now)
            if not slot:
                continue
            fid = flow.get("id")
            if not fid or state.get(fid) == slot:
                continue  # already fired this slot
            owner = str(flow.get("owner_client_id") or "")
            if per_owner.get(owner, 0) >= _MAX_STARTS_PER_TICK:
                continue  # this owner hit their cap — keep scanning OTHER tenants
            if not _compiles(flow):
                continue  # don't start an un-runnable flow
            # Hydrate the owning tenant's client context so executors (brand_pulse needs
            # business_name, client_report needs client_id) get their inputs — the cron
            # path never did this; mirrors customer_flows.cf_run. Admin flows (owner "")
            # keep empty context.
            inputs = {"_trigger": "cron", "fired_at": now.isoformat()}
            if owner:
                try:
                    from app.marketing import clients_store

                    _c = clients_store.get_client(owner) or {}
                    inputs.update(
                        {
                            "_owner_client_id": owner,
                            "client_id": owner,
                            "business_name": _c.get("business_name") or "",
                            "niche": _c.get("niche") or "general",
                            "city": _c.get("city") or "",
                        }
                    )
                except Exception:
                    pass
            if _fire(fid, inputs):
                state[fid] = slot  # success-marked dedupe
                started += 1
                per_owner[owner] = per_owner.get(owner, 0) + 1
        _write_state(state)
        return {"ok": True, "started": started}
    except Exception as e:
        logger.warning(f"[flow_triggers] run_cron_due failed: {e}")
        return {"ok": False, "error": str(e)[:120]}


# ---------------------------------------------------------------- event dispatch


def _dedupe_key(flow_id: str, payload: dict) -> str:
    p = payload or {}
    pid = p.get("lead_id") or p.get("lead_ref") or p.get("campaign_id") or p.get("id")
    if not pid:
        try:
            pid = str(hash(frozenset((str(k), str(v)) for k, v in p.items())))
        except Exception:
            pid = "x"
    return f"{flow_id}:{pid}"


def _recently_fired(flow_id: str, payload: dict) -> bool:
    last = _EVENT_FIRED.get(_dedupe_key(flow_id, payload))
    return last is not None and (time.time() - last) < _EVENT_WINDOW_S


def _mark_fired(flow_id: str, payload: dict) -> None:
    _EVENT_FIRED[_dedupe_key(flow_id, payload)] = time.time()
    if len(_EVENT_FIRED) > 500:  # bound the ring
        for k in sorted(_EVENT_FIRED, key=lambda x: _EVENT_FIRED[x])[:250]:
            _EVENT_FIRED.pop(k, None)


def fire_event(event_type: str, payload: dict, client_id: str = "") -> dict:
    """Dispatch a platform event to subscribed event-flows. Never raises.
    Called from the customer_webhooks.emit tail (the single dotted-event chokepoint)."""
    try:
        if not (_flow_runner_on() and _auto_on()):
            return {"skipped": "gated"}
        payload = payload if isinstance(payload, dict) else {}
        if payload.get("_flow_origin"):
            return {"skipped": "loop_guard"}  # event came FROM a flow run
        from app.automation import flow_store

        fired = 0
        for flow in flow_store.list_flows_full():
            trig = flow.get("trigger") or {}
            if trig.get("type") != "event" or trig.get("event") != event_type:
                continue
            fid = flow.get("id")
            if not fid or _recently_fired(fid, payload):
                continue
            if not _compiles(flow):
                continue
            if fired >= _MAX_STARTS_PER_TICK:
                break
            inputs = {
                **payload,
                "_trigger": "event",
                "_event": event_type,
                "_flow_origin": fid,
                "_client_id": str(client_id or ""),
            }
            if _fire(fid, inputs):
                _mark_fired(fid, payload)
                fired += 1
        return {"ok": True, "fired": fired}
    except Exception as e:
        logger.warning(f"[flow_triggers] fire_event failed: {e}")
        return {"ok": False, "error": str(e)[:120]}


__all__ = ["run_cron_due", "fire_event", "_cron_due"]
