"""Process Engine — babysitter-pattern adapt (a5c-ai/babysitter, 674★, MIT).

CORE IDEA (deterministic, hallucination-free orchestration):
  - **Process-as-code**: workflow = ordered steps DEFINED IN CODE (process_library.py).
    Agent/LLM sirf step ke ANDAR kaam karta — kaunsa step kab chalega yeh code
    decide karta, LLM nahi. (Humara coordinator/self_improve LLM-planned hai —
    yeh uska deterministic complement hai, replacement nahi.)
  - **Quality gates = code checks** (counts/flags), LLM-opinion nahi. Gate fail →
    bounded retry → fir run FAILED (aage nahi badhega).
  - **Breakpoints = enforced human approval** — ban-risky steps (outreach/publish)
    se pehle run PAUSE hota, admin `approve` kare tabhi aage. Drafts-only
    philosophy ka structured version.
  - **Event-sourced journal** — har event immutable JSONL me
    (`data/process_runs/<run_id>.jsonl`); state HAMESHA journal replay se derive
    hota → crash/restart pe exact resume, full audit trail.

Execution Celery worker me (`staff_jobs.process_tick`) — web process kabhi
heavy advance nahi karta (prod-down lesson). Koi naya dep nahi. Import-safe,
kabhi raise nahi.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_RUNS_DIR = os.path.join("data", "process_runs")
_INDEX = os.path.join(_RUNS_DIR, "index.jsonl")
_STEP_TIMEOUT_S = 240  # per-step hard cap

# Run statuses (journal-derived)
ST_RUNNING = "running"
ST_WAITING = "waiting_approval"
ST_COMPLETED = "completed"
ST_FAILED = "failed"


def engine_enabled() -> bool:
    """Master gate for process-as-code execution.

    The engine itself is safe to keep available: auto-start remains separately
    gated by PROCESS_AUTOSTART and risky steps still stop at breakpoints.
    """
    raw = os.environ.get("PROCESS_ENGINE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run_path(run_id: str) -> str:
    safe = "".join(c for c in run_id if c.isalnum() or c in "-_")[:40]
    return os.path.join(_RUNS_DIR, f"{safe}.jsonl")


def _append_event(run_id: str, etype: str, data: dict[str, Any] | None = None) -> None:
    try:
        os.makedirs(_RUNS_DIR, exist_ok=True)
        rec = {"run_id": run_id, "type": etype, "data": data or {}, "at": _now()}
        with open(_run_path(run_id), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception as e:
        logger.warning(f"[process] journal write failed {run_id}: {e}")


def _read_events(run_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        p = _run_path(run_id)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
    except Exception:
        pass
    return rows


# ---------------------------------------------------------------- replay (event-sourced state)


def replay(run_id: str) -> dict[str, Any]:
    """Journal se run-state derive karo (single source of truth — babysitter core).
    Returns: {status, process, inputs, step_index, retries, steps_done, last_error}."""
    st: dict[str, Any] = {
        "run_id": run_id,
        "status": ST_FAILED,
        "process": "",
        "inputs": {},
        "step_index": 0,
        "retries": 0,
        "steps_done": [],
        "last_error": "",
        "started_at": "",
        "ended_at": "",
    }
    events = _read_events(run_id)
    if not events:
        st["last_error"] = "run not found"
        return st
    for ev in events:
        t, d = ev.get("type"), ev.get("data") or {}
        if t == "run_started":
            st.update(
                status=ST_RUNNING,
                process=d.get("process", ""),
                inputs=d.get("inputs", {}),
                started_at=ev.get("at", ""),
            )
        elif t == "step_completed":
            st["steps_done"].append(
                {"step": d.get("step"), "detail": str(d.get("detail", ""))[:200]}
            )
            st["step_index"] = int(d.get("index", st["step_index"])) + 1
            st["retries"] = 0
        elif t == "gate_failed":
            st["retries"] = int(d.get("retries", st["retries"] + 1))
            st["last_error"] = f"gate: {d.get('reason', '')}"
        elif t == "breakpoint_waiting":
            st["status"] = ST_WAITING
        elif t == "breakpoint_approved":
            st["status"] = ST_RUNNING
            st["step_index"] = int(d.get("index", st["step_index"])) + 1
        elif t == "run_completed":
            st["status"] = ST_COMPLETED
            st["ended_at"] = ev.get("at", "")
        elif t == "run_failed":
            st["status"] = ST_FAILED
            st["last_error"] = str(d.get("error", ""))[:300]
            st["ended_at"] = ev.get("at", "")
    return st


# ---------------------------------------------------------------- run lifecycle


def start_run(process_key: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    """Naya run start (journal me run_started). Advance Celery tick se hota.
    Kabhi raise nahi."""
    if not engine_enabled():
        return {"ok": False, "skipped": "PROCESS_ENGINE off"}
    try:
        from app.agents import process_library

        proc = process_library.get_process(process_key)
        if not proc:
            return {"ok": False, "error": f"unknown process (valid: {process_library.list_keys()})"}
        run_id = f"{process_key[:18]}-{uuid.uuid4().hex[:8]}"
        _append_event(run_id, "run_started", {"process": process_key, "inputs": inputs or {}})
        try:
            os.makedirs(_RUNS_DIR, exist_ok=True)
            with open(_INDEX, "a", encoding="utf-8") as f:
                f.write(json.dumps({"run_id": run_id, "process": process_key, "at": _now()}) + "\n")
        except Exception:
            pass
        try:
            from app.platform import team

            team.log_event("manager", "process_started", f"{process_key} run {run_id}")
        except Exception:
            pass
        return {"ok": True, "run_id": run_id, "steps": len(proc["steps"])}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def advance(run_id: str, max_steps: int = 10) -> dict[str, Any]:
    """Run ko aage badhao: next step execute → gate check → journal. Rukta hai:
    breakpoint / completion / gate-fail (retries khatam) / step-budget pe.
    State sirf journal-replay se — crash-safe resume. Kabhi raise nahi."""
    if not engine_enabled():
        return {"ok": True, "skipped": "PROCESS_ENGINE off", "run_id": run_id}
    try:
        from app.agents import process_library

        st = replay(run_id)
        if st["status"] in (ST_COMPLETED, ST_FAILED) and st.get("last_error") != "run not found":
            return {"run_id": run_id, "status": st["status"], "note": "already ended"}
        if st.get("last_error") == "run not found":
            return {"run_id": run_id, "status": ST_FAILED, "error": "run not found"}
        if st["status"] == ST_WAITING:
            return {"run_id": run_id, "status": ST_WAITING, "note": "human approval pending"}

        proc = process_library.get_process(st["process"])
        if not proc:
            _append_event(run_id, "run_failed", {"error": f"process '{st['process']}' missing"})
            return {"run_id": run_id, "status": ST_FAILED, "error": "process definition missing"}

        steps = proc["steps"]
        done = 0
        while done < max_steps:
            idx = st["step_index"]
            if idx >= len(steps):
                _append_event(run_id, "run_completed", {})
                try:
                    from app.platform import team

                    team.log_event("manager", "process_completed", f"{st['process']} run {run_id}")
                except Exception:
                    pass
                return {"run_id": run_id, "status": ST_COMPLETED, "steps_done": idx}

            step = steps[idx]
            sid = step.get("id", f"step{idx}")

            # ---- breakpoint: ENFORCED human gate (approve hone tak run yahi rukta)
            if step.get("kind") == "breakpoint":
                _append_event(
                    run_id,
                    "breakpoint_waiting",
                    {"index": idx, "step": sid, "question": step.get("question", "Approve?")},
                )
                try:
                    from app.platform import team

                    team.log_event(
                        "manager",
                        "process_breakpoint",
                        f"{run_id}: {step.get('question', '')[:80]}",
                    )
                except Exception:
                    pass
                return {
                    "run_id": run_id,
                    "status": ST_WAITING,
                    "breakpoint": step.get("question", ""),
                    "step": sid,
                }

            # ---- task step
            _append_event(run_id, "step_started", {"index": idx, "step": sid})
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    process_library.execute_step(step, st["inputs"]), timeout=_STEP_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                result = {"ok": False, "detail": f"timeout {_STEP_TIMEOUT_S}s"}
            except Exception as e:
                result = {"ok": False, "detail": str(e)[:200]}
            ms = round((time.monotonic() - t0) * 1000, 1)

            # ---- deterministic gate (code check, LLM nahi)
            gate_ok, reason = process_library.check_gate(step, result)
            if gate_ok:
                _append_event(
                    run_id,
                    "step_completed",
                    {"index": idx, "step": sid, "detail": result.get("detail", ""), "ms": ms},
                )
                st = replay(run_id)
                done += 1
                continue

            retries = st["retries"] + 1
            max_r = int(step.get("max_retries", 1))
            _append_event(
                run_id,
                "gate_failed",
                {"index": idx, "step": sid, "reason": reason, "retries": retries},
            )
            if retries > max_r:
                _append_event(
                    run_id,
                    "run_failed",
                    {"error": f"step '{sid}' gate fail after {retries} tries: {reason}"},
                )
                return {"run_id": run_id, "status": ST_FAILED, "error": reason, "step": sid}
            st = replay(run_id)
            done += 1  # retry bhi budget kha ta hai (infinite loop guard)

        return {
            "run_id": run_id,
            "status": replay(run_id)["status"],
            "note": "step budget — tick continue karega",
        }
    except Exception as e:
        logger.warning(f"[process] advance failed {run_id}: {e}")
        return {"run_id": run_id, "status": ST_FAILED, "error": str(e)[:200]}


def approve(run_id: str, approved_by: str = "admin", note: str = "") -> dict[str, Any]:
    """Breakpoint approve → run resume-ready (Celery tick aage badhayega).
    Kabhi raise nahi."""
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {
                "ok": False,
                "error": f"run status '{st['status']}' — koi breakpoint pending nahi",
            }
        _append_event(
            run_id,
            "breakpoint_approved",
            {"index": st["step_index"], "by": approved_by[:40], "note": note[:200]},
        )
        return {"ok": True, "run_id": run_id, "resumed_at_step": st["step_index"] + 1}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def reject(run_id: str, by: str = "admin", reason: str = "") -> dict[str, Any]:
    """Breakpoint reject → run FAILED (audit trail ke saath)."""
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {"ok": False, "error": f"run status '{st['status']}'"}
        _append_event(run_id, "run_failed", {"error": f"rejected by {by}: {reason[:150]}"})
        return {"ok": True, "run_id": run_id, "status": ST_FAILED}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    """Recent runs + live status (journal replay)."""
    out: list[dict[str, Any]] = []
    try:
        rows: list[dict[str, Any]] = []
        if os.path.exists(_INDEX):
            with open(_INDEX, encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            pass
        for r in rows[-limit:][::-1]:
            st = replay(r.get("run_id", ""))
            out.append(
                {
                    "run_id": r.get("run_id"),
                    "process": st["process"] or r.get("process"),
                    "status": st["status"],
                    "step_index": st["step_index"],
                    "steps_done": len(st["steps_done"]),
                    "last_error": st["last_error"],
                    "started_at": st["started_at"] or r.get("at"),
                }
            )
    except Exception:
        pass
    return out


def journal(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Run ka full immutable journal (audit/debug)."""
    return _read_events(run_id)[-limit:]


def ensure_alive(stale_minutes: int = 15) -> dict[str, Any]:
    """Watchdog: stale RUNNING process runs ko process_tick se revive karo."""
    revived: list[str] = []
    active: list[str] = []
    try:
        now = datetime.now(timezone.utc)
        for r in list_runs(limit=50):
            if r.get("status") != ST_RUNNING:
                continue
            run_id = str(r.get("run_id") or "")
            if not run_id:
                continue
            events = _read_events(run_id)
            if not events:
                continue
            last_at = str(events[-1].get("at") or "")
            try:
                last = datetime.fromisoformat(last_at.replace("Z", "+00:00"))
                if last.tzinfo is None:
                    last = last.replace(tzinfo=timezone.utc)
                age_min = (now - last).total_seconds() / 60.0
            except Exception:
                age_min = float(stale_minutes + 1)
            if age_min < stale_minutes:
                active.append(run_id)
                continue
            try:
                from app.tasks.staff_jobs import process_tick

                process_tick.delay(run_id)
                revived.append(run_id)
            except Exception as e:
                logger.debug(f"[process] revive enqueue failed {run_id}: {e}")
        return {"ok": True, "revived": revived, "active": active}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


__all__ = [
    "start_run",
    "advance",
    "approve",
    "reject",
    "replay",
    "list_runs",
    "journal",
    "ensure_alive",
    "ST_RUNNING",
    "ST_WAITING",
    "ST_COMPLETED",
    "ST_FAILED",
]
