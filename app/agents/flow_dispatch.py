"""Flow dispatch — route a run to the engine that owns it (Phase 2).

engine_for(run_id) peeks run_started.engine in the shared journal. start()
compiles the flow to learn its kind BEFORE routing. The API + process_tick call
THROUGH this shim so neither knows which engine a run uses. Linear runs (incl.
pre-Phase-2 runs with no 'engine' key) -> process_engine; dag runs -> dag_engine.
Never raises.
"""

from __future__ import annotations

import json
import os
from typing import Any


def _flow_runner_on() -> bool:
    return os.getenv("FLOW_RUNNER", "0") in ("1", "true", "True")


def engine_for(run_id: str):
    from app.agents import dag_engine, process_engine

    try:
        for ev in process_engine._read_events(run_id):  # shared file reader
            if ev.get("type") == "run_started":
                eng = (ev.get("data") or {}).get("engine")
                return dag_engine if eng == "dag" else process_engine
    except Exception:
        pass
    return process_engine


def start(process_key: str, inputs: dict | None = None) -> dict[str, Any]:
    try:
        kind = "linear"
        pk = process_key or ""
        if pk.lower().startswith("flow:") and _flow_runner_on():
            from app.automation import flow_compiler, flow_store

            fl = flow_store.get_flow(pk[5:])
            if fl:
                _res, _errs, kind = flow_compiler.compile_flow(fl)
        if kind == "dag":
            from app.agents import dag_engine

            r = dag_engine.start_run(process_key, inputs)
            r["kind"] = "dag"
            return r
        from app.agents import process_engine

        r = process_engine.start_run(process_key, inputs)
        r["kind"] = "linear"
        return r
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


async def advance(run_id: str, max_steps: int | None = None) -> dict[str, Any]:
    try:
        eng = engine_for(run_id)
        if max_steps is None:
            return await eng.advance(run_id)
        return await eng.advance(run_id, max_steps)
    except Exception as e:
        return {"run_id": run_id, "status": "failed", "error": str(e)[:200]}


def replay(run_id: str) -> dict[str, Any]:
    try:
        return engine_for(run_id).replay(run_id)
    except Exception as e:
        return {"run_id": run_id, "status": "failed", "last_error": str(e)[:200]}


def approve(
    run_id: str, approved_by: str = "admin", note: str = "", node_id: str = ""
) -> dict[str, Any]:
    try:
        from app.agents import dag_engine

        eng = engine_for(run_id)
        if eng is dag_engine:
            return eng.approve(run_id, approved_by=approved_by, note=note, node_id=node_id)
        return eng.approve(run_id, approved_by=approved_by, note=note)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def reject(run_id: str, by: str = "admin", reason: str = "", node_id: str = "") -> dict[str, Any]:
    try:
        from app.agents import dag_engine

        eng = engine_for(run_id)
        if eng is dag_engine:
            return eng.reject(run_id, by=by, reason=reason, node_id=node_id)
        return eng.reject(run_id, by=by, reason=reason)
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
    from app.agents import dag_engine, process_engine

    rows: list[dict[str, Any]] = []
    for idx in (process_engine._INDEX, dag_engine._INDEX):
        try:
            if os.path.exists(idx):
                with open(idx, encoding="utf-8") as f:
                    for line in f:
                        if line.strip():
                            try:
                                rows.append(json.loads(line))
                            except Exception:
                                pass
        except Exception:
            pass
    rows.sort(key=lambda r: str(r.get("at") or ""))
    out: list[dict[str, Any]] = []
    for r in rows[-limit:][::-1]:
        rid = str(r.get("run_id") or "")
        st = replay(rid)
        out.append(
            {
                "run_id": rid,
                "process": st.get("process") or r.get("process"),
                "status": st.get("status"),
                "engine": st.get("engine", "linear"),
                "step_index": st.get("step_index", 0),
                "nodes": len(st.get("nodes", {})) if st.get("engine") == "dag" else None,
                "last_error": st.get("last_error", ""),
                "started_at": st.get("started_at") or r.get("at"),
            }
        )
    return out


def journal(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    from app.agents import process_engine

    return process_engine.journal(run_id, limit)  # shared JSONL reader (format-identical)


__all__ = ["engine_for", "start", "advance", "replay", "approve", "reject", "list_runs", "journal"]
