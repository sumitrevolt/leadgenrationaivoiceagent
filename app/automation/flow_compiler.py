"""Flow compiler — visual {nodes, edges} -> process_engine process-as-code.
Pure, no side-effects, never-raise. V1: LINEAR only, whitelisted actions.

Task step  = {id, action, gate?, max_retries?}
Breakpoint = {kind:"breakpoint", id, question}
Process    = {name, steps:[...]}
Per-step `args` is intentionally dropped — the engine passes the RUN-level
`inputs` to every executor in V1 (data-passing = Phase 4).
"""
from __future__ import annotations

from typing import Any


def compile_flow(flow: dict) -> tuple[dict | None, list[str]]:
    """Return (process_dict | None, errors)."""
    errors: list[str] = []
    try:
        from app.agents.process_library import EXECUTORS

        whitelist = set(EXECUTORS.keys())
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        if not nodes:
            return None, ["flow has no nodes"]

        ids = [str(n.get("id")) for n in nodes if n.get("id")]
        idset = set(ids)
        if len(idset) != len(ids):
            errors.append("duplicate node ids")
        nmap = {str(n.get("id")): n for n in nodes if n.get("id")}

        for e in edges:
            f, t = str(e.get("f")), str(e.get("t"))
            if f not in idset:
                errors.append(f"edge source '{f}' is not a node")
            if t not in idset:
                errors.append(f"edge target '{t}' is not a node")

        for n in nodes:
            if n.get("kind") == "breakpoint":
                continue
            act = str(n.get("action") or "")
            if act not in whitelist:
                errors.append(f"node '{n.get('id')}' action '{act}' not in executor whitelist")

        outdeg = {i: 0 for i in idset}
        indeg = {i: 0 for i in idset}
        for e in edges:
            f, t = str(e.get("f")), str(e.get("t"))
            if f in outdeg:
                outdeg[f] += 1
            if t in indeg:
                indeg[t] += 1
        for i in sorted(idset):
            if outdeg[i] > 1:
                errors.append(f"node '{i}' has {outdeg[i]} outgoing edges — V1 is linear only")
            if indeg[i] > 1:
                errors.append(f"node '{i}' has {indeg[i]} incoming edges — V1 is linear only")
        sources = [i for i in idset if indeg[i] == 0]
        if len(sources) != 1:
            errors.append(f"flow must have exactly 1 start node (found {len(sources)})")

        if errors:
            return None, errors

        nxt = {str(e.get("f")): str(e.get("t")) for e in edges}
        order: list[str] = []
        seen: set[str] = set()
        cur: str | None = sources[0]
        while cur:
            if cur in seen:
                return None, ["cycle detected"]
            seen.add(cur)
            order.append(cur)
            cur = nxt.get(cur)
        if len(order) != len(idset):
            return None, ["graph not a single connected linear chain"]

        steps: list[dict[str, Any]] = []
        for nid in order:
            n = nmap[nid]
            if n.get("kind") == "breakpoint":
                steps.append({
                    "kind": "breakpoint",
                    "id": nid,
                    "question": str(n.get("question") or n.get("title") or "Approve?"),
                })
            else:
                step: dict[str, Any] = {"id": nid, "action": str(n.get("action"))}
                if isinstance(n.get("gate"), dict):
                    step["gate"] = n["gate"]
                if n.get("max_retries") is not None:
                    step["max_retries"] = int(n["max_retries"])
                steps.append(step)
        return {"name": str(flow.get("name") or "flow"), "steps": steps}, []
    except Exception as e:
        return None, [f"compile error: {e}"]
