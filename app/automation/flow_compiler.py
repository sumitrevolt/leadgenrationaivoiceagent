"""Flow compiler — visual {nodes, edges} -> executable shape.

Phase 1: LINEAR flows -> process_engine process-as-code ({name, steps:[...]}).
Phase 2: BRANCHING flows -> dag_engine graph (per-node, conditional edges, merge).

`compile_flow` returns a 3-TUPLE: (result | None, errors, kind) where
kind in {"linear","dag"}. Linear output is byte-identical to Phase 1.
Pure, no side-effects, never-raise.
"""
from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

# Phase 5: actions that can have an external side effect when their flag is on.
# A NON-FATAL warning is attached when one has no upstream Approval (breakpoint).
SIDE_EFFECT_ACTIONS = {"telegram_draft", "crm_queue"}


def _warn_text(nid: str, action: str) -> str:
    return f"'{nid}' ({action}) has no upstream Approval — add a breakpoint before it"


def _linear_warnings(order: list[str], nmap: dict) -> list[str]:
    warns: list[str] = []
    seen_bp = False
    for nid in order:
        n = nmap[nid]
        if n.get("kind") == "breakpoint":
            seen_bp = True
            continue
        act = str(n.get("action") or "")
        if act in SIDE_EFFECT_ACTIONS and not seen_bp:
            warns.append(_warn_text(nid, act))
    return warns


def _dag_warnings(gnodes: dict, in_map: dict) -> list[str]:
    warns: list[str] = []
    for nid, spec in gnodes.items():
        if spec.get("kind") != "task" or spec.get("action") not in SIDE_EFFECT_ACTIONS:
            continue
        seen: set[str] = set()
        stack = [e["f"] for e in in_map.get(nid, [])]
        has_bp = False
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u)
            if gnodes.get(u, {}).get("kind") == "breakpoint":
                has_bp = True
                break
            stack.extend(e["f"] for e in in_map.get(u, []))
        if not has_bp:
            warns.append(_warn_text(nid, spec["action"]))
    return warns


def compile_flow(flow: dict) -> tuple[dict | None, list[str], str]:
    """(result, errors, kind). See module docstring."""
    errors: list[str] = []
    try:
        from app.agents.process_library import EXECUTORS
        from app.automation import edge_condition

        whitelist = set(EXECUTORS.keys())
        nodes = flow.get("nodes") or []
        edges = flow.get("edges") or []
        if not nodes:
            return None, ["flow has no nodes"], "linear"

        ids = [str(n.get("id")) for n in nodes if n.get("id")]
        idset = set(ids)
        if len(idset) != len(ids):
            errors.append("duplicate node ids")
        nmap = {str(n.get("id")): n for n in nodes if n.get("id")}

        valid_edges = []
        for e in edges:
            f, t = str(e.get("f")), str(e.get("t"))
            if f not in idset:
                errors.append(f"edge source '{f}' is not a node")
            if t not in idset:
                errors.append(f"edge target '{t}' is not a node")
            if f in idset and t in idset:
                valid_edges.append(e)

        for n in nodes:
            if n.get("kind") in ("breakpoint", "merge"):
                continue
            act = str(n.get("action") or "")
            if act not in whitelist:
                errors.append(f"node '{n.get('id')}' action '{act}' not in executor whitelist")

        outdeg = {i: 0 for i in idset}
        indeg = {i: 0 for i in idset}
        for e in valid_edges:
            outdeg[str(e["f"])] += 1
            indeg[str(e["t"])] += 1

        # ---- decide kind: linear iff Phase-1-shaped (no branching primitives) ----
        has_when = any(isinstance(e.get("when"), dict) and e.get("when") for e in valid_edges)
        has_merge = any(nmap[i].get("kind") == "merge" for i in idset)
        max_in = max(indeg.values()) if indeg else 0
        max_out = max(outdeg.values()) if outdeg else 0
        roots = [i for i in idset if indeg[i] == 0]
        is_linear = (not has_when and not has_merge and max_in <= 1 and max_out <= 1
                     and len(roots) == 1)

        if is_linear:
            return _compile_linear(flow, nmap, idset, valid_edges, roots, errors)
        return _compile_dag(flow, nmap, idset, valid_edges, indeg, roots, edge_condition, errors)
    except Exception as e:
        return None, [f"compile error: {e}"], "linear"


def _compile_linear(flow, nmap, idset, valid_edges, roots, errors):
    """Phase-1 linear path — byte-identical steps output."""
    if errors:
        return None, errors, "linear"
    nxt = {str(e["f"]): str(e["t"]) for e in valid_edges}
    order: list[str] = []
    seen: set[str] = set()
    cur = roots[0]
    while cur:
        if cur in seen:
            return None, ["cycle detected"], "linear"
        seen.add(cur)
        order.append(cur)
        cur = nxt.get(cur)
    if len(order) != len(idset):
        return None, ["graph not a single connected linear chain"], "linear"
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
    proc: dict[str, Any] = {"name": str(flow.get("name") or "flow"), "steps": steps}
    w = _linear_warnings(order, nmap)
    if w:
        proc["warnings"] = w
    return proc, [], "linear"


def _compile_dag(flow, nmap, idset, valid_edges, indeg, roots, edge_condition, errors):
    """Phase-2 DAG path — validate then emit a graph dict."""
    # condition validity (caught at save)
    for e in valid_edges:
        w = e.get("when")
        if w:
            for msg in edge_condition.validate(w):
                errors.append(f"edge {e.get('f')}->{e.get('t')}: {msg}")

    # join semantics: indegree>=2 MUST be merge; merge MUST be indegree>=2
    for i in idset:
        n = nmap[i]
        if indeg[i] >= 2 and n.get("kind") != "merge":
            errors.append(f"node '{i}' has {indeg[i]} incoming edges — use a merge node before it")
        if n.get("kind") == "merge" and indeg[i] < 2:
            errors.append(f"merge node '{i}' needs >=2 incoming edges")

    # breakpoint out-edges must be unconditional (breakpoint has no result dict)
    for e in valid_edges:
        if e.get("when") and nmap.get(str(e["f"]), {}).get("kind") == "breakpoint":
            errors.append(f"breakpoint '{e['f']}' out-edge cannot have a condition")

    # acyclic (Kahn) + reachability
    adj: dict[str, list[str]] = defaultdict(list)
    for e in valid_edges:
        adj[str(e["f"])].append(str(e["t"]))
    if not roots:
        errors.append("no start node (every node has an incoming edge — cycle?)")
    ind = dict(indeg)
    q = deque([i for i in idset if ind[i] == 0])
    visited = 0
    while q:
        u = q.popleft()
        visited += 1
        for v in adj[u]:
            ind[v] -= 1
            if ind[v] == 0:
                q.append(v)
    if visited != len(idset):
        errors.append("cycle detected — Phase 2 is a strict DAG (no loops)")
    reach: set[str] = set()
    dq = deque(roots)
    while dq:
        u = dq.popleft()
        if u in reach:
            continue
        reach.add(u)
        for v in adj[u]:
            dq.append(v)
    for i in sorted(idset):
        if i not in reach:
            errors.append(f"node '{i}' unreachable from any start node")

    if errors:
        return None, errors, "dag"

    in_map: dict[str, list[dict]] = {i: [] for i in idset}
    out_map: dict[str, list[dict]] = {i: [] for i in idset}
    for e in valid_edges:
        f, t = str(e["f"]), str(e["t"])
        w = e.get("when") if isinstance(e.get("when"), dict) and e.get("when") else None
        out_map[f].append({"t": t, "when": w})
        in_map[t].append({"f": f, "when": w})

    gnodes: dict[str, dict] = {}
    for i in sorted(idset):
        n = nmap[i]
        k = n.get("kind", "task")
        spec: dict[str, Any] = {"id": i, "kind": k}
        if k == "task":
            spec["action"] = str(n.get("action"))
            if isinstance(n.get("gate"), dict):
                spec["gate"] = n["gate"]
            if n.get("max_retries") is not None:
                spec["max_retries"] = int(n["max_retries"])
        elif k == "merge":
            spec["join"] = "any" if str(n.get("join", "all")).lower() == "any" else "all"
        elif k == "breakpoint":
            spec["question"] = str(n.get("question") or n.get("title") or "Approve?")
        gnodes[i] = spec

    graph = {
        "name": str(flow.get("name") or "flow"),
        "kind": "dag",
        "nodes": gnodes,
        "edges": [{"f": str(e["f"]), "t": str(e["t"]),
                   "when": (e.get("when") if isinstance(e.get("when"), dict) and e.get("when") else None)}
                  for e in valid_edges],
        "in": in_map,
        "out": out_map,
        "roots": sorted(roots),
    }
    w = _dag_warnings(gnodes, in_map)
    if w:
        graph["warnings"] = w
    return graph, [], "dag"
