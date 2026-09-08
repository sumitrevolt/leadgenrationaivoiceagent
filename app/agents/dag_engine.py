"""DAG engine — Phase 2 branching flow runner (alongside process_engine).

Per-node, journal-derived executor. State = ready-set recomputed from the journal
each tick (the per-node analogue of process_engine's integer cursor). Shares the
journal DIR data/process_runs/ with process_engine (same record format) but uses
a SEPARATE index file (dag_index.jsonl) so each engine's watchdog sees only its
own runs. process_engine.py is byte-unchanged.

Parallelism = ready-set concurrency ACROSS ticks; one await at a time WITHIN a
tick (no asyncio.gather) — crash-safe + rate-limit-safe. Conditions are
FAIL-CLOSED (edge_condition). run_completed/run_failed are EMITTED by advance
(replay reflects journal truth, like process_engine). Import-safe, never raises.
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

_RUNS_DIR = os.path.join("data", "process_runs")  # SHARED journal dir
_INDEX = os.path.join("data", "process_runs", "dag_index.jsonl")  # SEPARATE index
_STEP_TIMEOUT_S = 240

ST_RUNNING = "running"
ST_WAITING = "waiting_approval"
ST_COMPLETED = "completed"
ST_FAILED = "failed"

_TERMINAL_NODE = ("done", "skipped", "failed")


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
        logger.warning(f"[dag] journal write failed {run_id}: {e}")


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


# ---------------------------------------------------------------- replay (per-node state)


def _edge_state(edge: dict, nodes: dict) -> str:
    """fired | dead | undetermined for one edge, from the SOURCE node's state."""
    from app.automation import edge_condition

    src = nodes.get(edge.get("f"), {})
    s = src.get("state")
    if s == "done":
        return (
            "fired"
            if edge_condition.edge_taken(edge.get("when"), src.get("result") or {})
            else "dead"
        )
    if s in ("skipped", "failed"):
        return "dead"
    return "undetermined"


def _frontier(graph: dict, nodes: dict) -> tuple[list[str], list[str]]:
    """(ready, skip): pending/running nodes runnable now; pending nodes to skip."""
    ready: list[str] = []
    skip: list[str] = []
    in_map = graph.get("in", {})
    for nid, spec in graph.get("nodes", {}).items():
        s = nodes.get(nid, {}).get("state")
        if s == "running":
            ready.append(nid)  # crash re-run (node_started w/o completion)
            continue
        if s != "pending":
            continue
        ins = in_map.get(nid, [])
        if not ins:
            ready.append(nid)  # root
            continue
        states = [_edge_state(e, nodes) for e in ins]
        fired = any(x == "fired" for x in states)
        undet = any(x == "undetermined" for x in states)
        join = "any" if (spec.get("kind") == "merge" and spec.get("join") == "any") else "all"
        if join == "any":
            if fired:
                ready.append(nid)
            elif not undet:
                skip.append(nid)
        else:  # all
            if undet:
                continue
            if fired:
                ready.append(nid)
            else:
                skip.append(nid)
    return ready, skip


def replay(run_id: str) -> dict[str, Any]:
    st: dict[str, Any] = {
        "run_id": run_id,
        "status": ST_FAILED,
        "process": "",
        "inputs": {},
        "engine": "dag",
        "graph": {},
        "nodes": {},
        "ready": [],
        "skip": [],
        "waiting": "",
        "last_error": "",
        "started_at": "",
        "ended_at": "",
    }
    events = _read_events(run_id)
    if not events:
        st["last_error"] = "run not found"
        return st
    nodes: dict[str, dict] = {}
    graph: dict[str, Any] = {}
    for ev in events:
        t, d = ev.get("type"), ev.get("data") or {}
        if t == "run_started":
            graph = d.get("graph") or {}
            st["process"] = d.get("process", "")
            st["inputs"] = d.get("inputs", {})
            st["started_at"] = ev.get("at", "")
            st["status"] = ST_RUNNING
            for nid in graph.get("nodes", {}):
                nodes[nid] = {"state": "pending", "result": None, "retries": 0}
        elif t == "node_started":
            n = d.get("node")
            if n in nodes:
                nodes[n]["state"] = "running"
        elif t == "node_completed":
            n = d.get("node")
            if n in nodes:
                nodes[n]["state"] = "done"
                nodes[n]["result"] = d.get("result")
        elif t == "node_gate_failed":
            n = d.get("node")
            if n in nodes:
                nodes[n]["retries"] = int(d.get("retries", nodes[n]["retries"] + 1))
                nodes[n]["state"] = "pending"  # re-runnable until retries exhausted
        elif t == "node_skipped":
            n = d.get("node")
            if n in nodes:
                nodes[n]["state"] = "skipped"
        elif t == "breakpoint_waiting":
            n = d.get("node")
            if n in nodes:
                nodes[n]["state"] = "waiting"
        elif t == "breakpoint_approved":
            n = d.get("node")
            if n in nodes:
                nodes[n]["state"] = "done"  # no result; out-edges unconditional
        elif t == "run_completed":
            st["status"] = ST_COMPLETED
            st["ended_at"] = ev.get("at", "")
        elif t == "run_failed":
            st["status"] = ST_FAILED
            st["last_error"] = str(d.get("error", ""))[:300]
            st["ended_at"] = ev.get("at", "")
    st["graph"] = graph
    st["nodes"] = nodes
    waiting = next((nid for nid, n in nodes.items() if n["state"] == "waiting"), "")
    st["waiting"] = waiting
    # frontier + waiting rollup (only while not terminally journaled).
    # NOTE: 'all nodes terminal' does NOT roll up to completed here — advance emits
    # run_completed so the journal/watchdog stay consistent with process_engine.
    if st["status"] not in (ST_COMPLETED, ST_FAILED):
        ready, skip = _frontier(graph, nodes)
        st["ready"], st["skip"] = ready, skip
        if waiting:
            st["status"] = ST_WAITING
    return st


# ---------------------------------------------------------------- run lifecycle


def start_run(process_key: str, inputs: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        from app.automation import flow_compiler, flow_store

        pk = process_key or ""
        if not pk.lower().startswith("flow:"):
            return {"ok": False, "error": "dag_engine only runs flow:<id>"}
        fl = flow_store.get_flow(pk[5:])
        if not fl:
            return {"ok": False, "error": "flow not found"}
        graph, errs, kind = flow_compiler.compile_flow(fl)
        if kind != "dag" or not graph:
            return {"ok": False, "error": "not a dag flow: " + "; ".join(errs)[:160]}
        run_id = f"{pk[:18]}-{uuid.uuid4().hex[:8]}"
        _append_event(
            run_id,
            "run_started",
            {"process": process_key, "inputs": inputs or {}, "engine": "dag", "graph": graph},
        )
        try:
            os.makedirs(_RUNS_DIR, exist_ok=True)
            with open(_INDEX, "a", encoding="utf-8") as f:
                f.write(json.dumps({"run_id": run_id, "process": process_key, "at": _now()}) + "\n")
        except Exception:
            pass
        try:
            from app.platform import team

            team.log_event("manager", "dag_started", f"{process_key} run {run_id}")
        except Exception:
            pass
        return {"ok": True, "run_id": run_id, "nodes": len(graph.get("nodes", {}))}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _resolve_inputs(node: dict, run_inputs: dict, nodes: dict) -> dict:
    """Phase 4 data-passing: merge resolved upstream outputs + literals over run inputs.
    FAIL-CLOSED — a missing/not-done source or absent key is OMITTED (never garbage).
    Source nodes are compiler-guaranteed ancestors, so they are `done` by the time
    this node runs. Never raises."""
    eff = dict(run_inputs or {})
    imap = node.get("inputs_map")
    if not isinstance(imap, dict):
        return eff
    for tgt, spec in imap.items():
        try:
            if not isinstance(spec, dict):
                continue
            if "value" in spec:
                eff[tgt] = spec["value"]
                continue
            src = nodes.get(spec.get("from")) or {}
            res = src.get("result")
            key = spec.get("key")
            if src.get("state") == "done" and isinstance(res, dict) and key in res:
                eff[tgt] = res[key]
            # else: fail-closed — omit
        except Exception:
            pass
    return eff


def _emit_out(run_id: str, graph: dict, nid: str, result: dict) -> None:
    """Emit edge_taken for fired out-edges (UI/audit; replay recomputes anyway)."""
    from app.automation import edge_condition

    for e in graph.get("out", {}).get(nid, []):
        try:
            if edge_condition.edge_taken(e.get("when"), result or {}):
                _append_event(run_id, "edge_taken", {"f": nid, "t": e.get("t")})
        except Exception:
            pass


async def advance(run_id: str, max_steps: int = 16) -> dict[str, Any]:
    try:
        from app.agents import process_library

        done = 0
        while done < max_steps:
            st = replay(run_id)
            if st.get("last_error") == "run not found":
                return {"run_id": run_id, "status": ST_FAILED, "error": "run not found"}
            status = st["status"]
            if status == ST_WAITING:
                return {"run_id": run_id, "status": ST_WAITING, "note": "human approval pending"}
            if status in (ST_COMPLETED, ST_FAILED):
                return {"run_id": run_id, "status": status, "note": "already ended"}

            graph, nodes = st["graph"], st["nodes"]
            inputs = st["inputs"]
            ready, skip = st["ready"], st["skip"]

            if skip:
                for nid in skip:
                    _append_event(
                        run_id, "node_skipped", {"node": nid, "reason": "branch not taken"}
                    )
                continue  # recompute frontier

            if not ready:
                # nothing ready/skippable: any non-terminal left = unreachable -> skip; then complete
                for nid, n in nodes.items():
                    if n["state"] not in _TERMINAL_NODE:
                        _append_event(
                            run_id, "node_skipped", {"node": nid, "reason": "unreachable"}
                        )
                _append_event(run_id, "run_completed", {})
                try:
                    from app.platform import team

                    team.log_event("manager", "dag_completed", f"{st['process']} run {run_id}")
                except Exception:
                    pass
                return {"run_id": run_id, "status": ST_COMPLETED}

            nid = ready[0]
            node = graph["nodes"][nid]
            kind = node.get("kind", "task")

            if kind == "breakpoint":
                _append_event(
                    run_id,
                    "breakpoint_waiting",
                    {"node": nid, "question": node.get("question", "Approve?")},
                )
                try:
                    from app.platform import team

                    team.log_event(
                        "manager", "dag_breakpoint", f"{run_id}: {node.get('question', '')[:80]}"
                    )
                except Exception:
                    pass
                return {
                    "run_id": run_id,
                    "status": ST_WAITING,
                    "node": nid,
                    "breakpoint": node.get("question", ""),
                }

            if kind == "merge":
                res = {"ok": True, "count": 1, "detail": "merged"}
                _append_event(run_id, "node_completed", {"node": nid, "result": res, "ms": 0})
                _emit_out(run_id, graph, nid, res)
                done += 1
                continue

            # task node — Phase 4: resolve per-node inputs (upstream outputs + literals)
            eff_inputs = _resolve_inputs(node, inputs, nodes)
            _append_event(run_id, "node_started", {"node": nid})
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    process_library.execute_step(node, eff_inputs), timeout=_STEP_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                result = {"ok": False, "detail": f"timeout {_STEP_TIMEOUT_S}s"}
            except Exception as e:
                result = {"ok": False, "detail": str(e)[:200]}
            ms = round((time.monotonic() - t0) * 1000, 1)

            ok, reason = process_library.check_gate(node, result)

            # Harness DAG shadow (record-only; INERT unless AGENT_HARNESS +
            # AGENT_HARNESS_SHADOW on, agent in canary agents, dag_engine in
            # canary loops). NEVER executes/blocks/retries the node; never raises.
            try:
                from app.agents.harness.adapters import observe_dag_action

                _cur = int(nodes[nid].get("retries", 0))
                _maxr = int(node.get("max_retries", 1))
                if ok:
                    _nstatus, _retry = "completed", False
                elif (_cur + 1) > _maxr:
                    _nstatus, _retry = "failed", False
                else:
                    _nstatus, _retry = "retry_pending", True
                observe_dag_action(
                    dag_run_id=run_id,
                    node_id=nid,
                    attempt=_cur,
                    agent_id=str(
                        inputs.get("_harness_agent_id") or inputs.get("agent_id") or "manager"
                    ),
                    tenant_id=str(inputs.get("tenant_id") or inputs.get("client_id") or ""),
                    tool_name=str(node.get("action") or nid),
                    tool_version=str(node.get("version") or "v1"),
                    arguments=eff_inputs,
                    actual_result=(result if ok else None),
                    actual_error=(None if ok else reason),
                    latency_ms=int(ms),
                    dag_node_status=_nstatus,
                    retry_scheduled=_retry,
                )
            except Exception:
                pass

            if ok:
                clean = {
                    "ok": result.get("ok"),
                    "count": result.get("count"),
                    "detail": str(result.get("detail", ""))[:200],
                }
                _append_event(run_id, "node_completed", {"node": nid, "result": clean, "ms": ms})
                _emit_out(run_id, graph, nid, clean)
                done += 1
                continue

            retries = int(nodes[nid].get("retries", 0)) + 1
            max_r = int(node.get("max_retries", 1))
            _append_event(
                run_id, "node_gate_failed", {"node": nid, "reason": reason, "retries": retries}
            )
            if retries > max_r:
                _append_event(
                    run_id,
                    "run_failed",
                    {"error": f"node '{nid}' gate fail after {retries}: {reason}", "node": nid},
                )
                return {"run_id": run_id, "status": ST_FAILED, "error": reason, "node": nid}
            done += 1  # retry consumes budget
            continue

        return {
            "run_id": run_id,
            "status": replay(run_id)["status"],
            "note": "step budget — tick continue karega",
        }
    except Exception as e:
        logger.warning(f"[dag] advance failed {run_id}: {e}")
        return {"run_id": run_id, "status": ST_FAILED, "error": str(e)[:200]}


def approve(
    run_id: str, approved_by: str = "admin", note: str = "", node_id: str = ""
) -> dict[str, Any]:
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {
                "ok": False,
                "error": f"run status '{st['status']}' — koi breakpoint pending nahi",
            }
        nid = node_id or st.get("waiting") or ""
        if not nid or nid not in st["nodes"]:
            return {"ok": False, "error": "no waiting node"}
        _append_event(
            run_id, "breakpoint_approved", {"node": nid, "by": approved_by[:40], "note": note[:200]}
        )
        # breakpoint out-edges are unconditional (compiler-enforced) -> emit for UI
        for e in st.get("graph", {}).get("out", {}).get(nid, []) or []:
            _append_event(run_id, "edge_taken", {"f": nid, "t": e.get("t")})
        return {"ok": True, "run_id": run_id, "node": nid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def reject(run_id: str, by: str = "admin", reason: str = "", node_id: str = "") -> dict[str, Any]:
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {"ok": False, "error": f"run status '{st['status']}'"}
        _append_event(
            run_id,
            "run_failed",
            {
                "error": f"rejected by {by}: {reason[:150]}",
                "node": node_id or st.get("waiting", ""),
            },
        )
        return {"ok": True, "run_id": run_id, "status": ST_FAILED}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_runs(limit: int = 20) -> list[dict[str, Any]]:
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
            nodes = st["nodes"]
            out.append(
                {
                    "run_id": r.get("run_id"),
                    "process": st["process"] or r.get("process"),
                    "status": st["status"],
                    "engine": "dag",
                    "nodes": len(nodes),
                    "done": sum(1 for n in nodes.values() if n["state"] in _TERMINAL_NODE),
                    "last_error": st["last_error"],
                    "started_at": st["started_at"] or r.get("at"),
                }
            )
    except Exception:
        pass
    return out


def journal(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    return _read_events(run_id)[-limit:]


def ensure_alive(stale_minutes: int = 15) -> dict[str, Any]:
    """Watchdog: stale RUNNING dag runs -> process_tick revive."""
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
            # Guard: process_tick → flow_dispatch.engine_for(); malformed /
            # pre-Phase-2 journal (no engine=dag) silently falls back to
            # process_engine and mis-advances the run. Skip those revive.
            try:
                from app.agents import dag_engine as _dag
                from app.agents.flow_dispatch import engine_for

                if engine_for(run_id) is not _dag:
                    logger.warning(
                        f"[dag] revive skip {run_id}: engine_for mismatch "
                        f"(not dag — refusing process_engine fallback)"
                    )
                    continue
            except Exception as e:
                logger.debug(f"[dag] engine_for check failed {run_id}: {e}")
                continue
            try:
                from app.tasks.staff_jobs import process_tick

                process_tick.delay(run_id)
                revived.append(run_id)
            except Exception as e:
                logger.debug(f"[dag] revive enqueue failed {run_id}: {e}")
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
