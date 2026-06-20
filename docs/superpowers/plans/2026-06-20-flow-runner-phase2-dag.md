# Flow Runner — Phase 2 (Branching / DAG) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the explorer builder run **branching** flows — conditional edges (`when`), parallel fan-out, and merge/join — on a NEW `dag_engine` alongside the untouched linear `process_engine`, fully inside the existing journal / RBAC / `FLOW_RUNNER` flag / Celery `process_tick` machinery.

**Architecture:** A `flow:` resolver compiles a flow to either a linear `process` (Phase 1, unchanged) or a DAG `graph`. A thin `flow_dispatch` shim routes each run to the engine that owns it (read from `run_started.engine`). `dag_engine` tracks **per-node** state derived purely by journal replay (ready-set replaces the linear cursor); edge conditions are evaluated by a pure, fail-closed `edge_condition` module. Both engines share the `data/process_runs/` journal dir and the `process_tick` task; only the run-index file differs so each engine's watchdog sees only its own runs.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Celery (existing `process_tick`), pytest, vanilla JS (`frontend/explorer.html`). No new dependency, container, DB, route-mount, worker job, or flag.

## Global Constraints

- **Windows venv for all python/tests:** `C:\Users\Ratanshila\Documents\leadgenrationaiagent\.venv\Scripts\python.exe` (sandbox python is stale; never run app/tests from sandbox python).
- **Windows git:** `C:\PROGRA~1\Git\cmd\git.exe`.
- **Read before Edit:** Read each file immediately before editing it (sandbox mount goes stale after edits). Never parallel-edit the same file.
- **Never-raise:** every store/compiler/engine/dispatch/condition/API function wraps in try/except and returns a safe value — import-safe.
- **Flag-gated:** all DAG behaviour behind the EXISTING `FLOW_RUNNER` env (`"1"`/`"true"`/`"True"` = on); default OFF = INERT (routes 503, `flow:` keys unresolved, DAG path dead). **No new flag.**
- **Admin-only:** every flow route keeps `Depends(require_admin)`.
- **Whitelist-only:** a task node's `action` MUST be a key in `process_library.EXECUTORS`; unknown = compile error. No arbitrary code/HTTP/LLM in conditions.
- **Fail-CLOSED conditions:** an unevaluable/malformed `when` returns `False` → that edge does NOT fire → branch is skipped, never wrongly taken.
- **`process_engine.py` is BYTE-UNCHANGED.** Phase 2 adds files and edits others, but never edits `app/agents/process_engine.py`.
- **Strict DAG:** cycles/loops are rejected at compile (Kahn topological sort).
- **Serial-within-tick parallelism:** "parallel branches" run as ready-set concurrency ACROSS ticks, executed one `await` at a time WITHIN a tick (no `asyncio.gather`) — crash-safe + rate-limit-safe. Documented Phase-2 semantic.
- **Data-passing is Phase 4 — NOT here.** Executors receive only the run-level `inputs` (identical to Phase 1). Edge conditions read the SOURCE node's own result dict only.
- **EXECUTORS keys (runnable task actions):** `scrape, harvest, rescore, sales_analysis, content_pack, social_drafts, cadence_run, optimizer, revenue_sweep`.
- **Node kinds:** `task` (default, has `action`) · `breakpoint` (has `question`) · `merge` (has `join: "all"|"any"`). **Edge:** `{f, t, when?}`.
- **Result dict shape (what executors return / conditions read):** `{ok: bool, count: int, detail: str}`.
- **Shared journal record shape:** `{run_id, type, data, at}` JSONL at `data/process_runs/<run_id>.jsonl` (same dir, same format as Phase 1).

---

### Task 1: Edge-condition evaluator (`edge_condition.py`)

Pure, deterministic, fail-closed condition evaluator + validator. No engine/IO deps — foundational, build first.

**Files:**
- Create: `app/automation/edge_condition.py`
- Test: `tests/test_edge_condition.py`

**Interfaces:**
- Produces:
  - `edge_taken(when: dict | None, source_result: dict) -> bool` — `None`/`{}` ⇒ `True` (unconditional); leaf `{field,op,value}`; combinators `{"all":[...]}`/`{"any":[...]}`; never raises, malformed ⇒ `False`.
  - `validate(when: dict | None) -> list[str]` — `[]` if valid; nesting depth ≤ 3; known op; non-empty string `field`; scalar `value` for relational ops.
  - `OPS: set[str]` = `{== != > >= < <= in not_in truthy falsy exists}`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_edge_condition.py
from app.automation.edge_condition import edge_taken, validate


def test_none_and_empty_are_unconditional():
    assert edge_taken(None, {"count": 0}) is True
    assert edge_taken({}, {"count": 0}) is True


def test_numeric_leaf_ops():
    assert edge_taken({"field": "count", "op": ">=", "value": 1}, {"count": 5}) is True
    assert edge_taken({"field": "count", "op": "<", "value": 1}, {"count": 0}) is True
    assert edge_taken({"field": "count", "op": ">=", "value": 1}, {"count": 0}) is False


def test_string_vs_numeric_coercion():
    # both castable to float -> numeric compare
    assert edge_taken({"field": "count", "op": "==", "value": 3}, {"count": "3"}) is True
    # not castable -> string compare
    assert edge_taken({"field": "detail", "op": "==", "value": "merged"}, {"detail": "merged"}) is True
    assert edge_taken({"field": "detail", "op": "!=", "value": "x"}, {"detail": "merged"}) is True


def test_truthy_falsy_exists():
    assert edge_taken({"field": "ok", "op": "truthy", "value": None}, {"ok": True}) is True
    assert edge_taken({"field": "ok", "op": "falsy", "value": None}, {"ok": False}) is True
    assert edge_taken({"field": "count", "op": "exists", "value": None}, {"count": 0}) is True
    assert edge_taken({"field": "nope", "op": "exists", "value": None}, {"count": 0}) is False


def test_in_not_in():
    assert edge_taken({"field": "count", "op": "in", "value": [1, 2, 3]}, {"count": 2}) is True
    assert edge_taken({"field": "count", "op": "not_in", "value": [1, 2, 3]}, {"count": 9}) is True


def test_all_any_combinators():
    cond = {"all": [{"field": "ok", "op": "truthy", "value": None},
                    {"field": "count", "op": ">=", "value": 1}]}
    assert edge_taken(cond, {"ok": True, "count": 2}) is True
    assert edge_taken(cond, {"ok": True, "count": 0}) is False
    any_cond = {"any": [{"field": "count", "op": ">=", "value": 100},
                        {"field": "ok", "op": "truthy", "value": None}]}
    assert edge_taken(any_cond, {"ok": True, "count": 0}) is True


def test_missing_field_relational_fail_closed():
    # relational op on a missing field -> None -> False (fail-closed)
    assert edge_taken({"field": "ghost", "op": ">=", "value": 1}, {"count": 5}) is False


def test_malformed_when_fail_closed():
    assert edge_taken({"field": "count", "op": "bogus", "value": 1}, {"count": 5}) is False
    assert edge_taken("not-a-dict", {"count": 5}) is False


def test_validate_accepts_good():
    assert validate({"field": "count", "op": ">=", "value": 1}) == []
    assert validate({"all": [{"field": "ok", "op": "truthy", "value": None}]}) == []
    assert validate(None) == []


def test_validate_rejects_bad():
    assert validate({"field": "count", "op": "bogus", "value": 1})  # unknown op
    assert validate({"field": "", "op": "==", "value": 1})          # empty field
    deep = {"all": [{"all": [{"all": [{"all": [{"field": "a", "op": "==", "value": 1}]}]}]}]}
    assert validate(deep)  # depth > 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edge_condition.py -q`
Expected: FAIL — `ModuleNotFoundError: app.automation.edge_condition`.

- [ ] **Step 3: Write the implementation**

```python
# app/automation/edge_condition.py
"""Edge-condition evaluator for the DAG flow runner (Phase 2).

Pure + deterministic — NO code/LLM/attribute-access/arithmetic. Evaluates an
edge's `when` against the SOURCE node's result dict ({ok,count,detail}).
FAIL-CLOSED: any malformed/unevaluable condition returns False, so a branch you
cannot evaluate is NEVER taken (a broken condition can't trigger a side effect).
Import-safe, never raises.
"""
from __future__ import annotations

from typing import Any

OPS = {"==", "!=", ">", ">=", "<", "<=", "in", "not_in", "truthy", "falsy", "exists"}
_REL = {"==", "!=", ">", ">=", "<", "<="}
_MAX_DEPTH = 3


def _cmp(actual: Any, value: Any, op: str) -> bool:
    a, b = actual, value
    try:
        a, b = float(actual), float(value)  # numeric compare if both castable
    except (TypeError, ValueError):
        a, b = str(actual), str(value)      # else string compare
    if op == "==":
        return a == b
    if op == "!=":
        return a != b
    if op == ">":
        return a > b
    if op == ">=":
        return a >= b
    if op == "<":
        return a < b
    if op == "<=":
        return a <= b
    return False


def _leaf(cond: dict, src: dict) -> bool:
    field = cond.get("field")
    op = cond.get("op")
    if op not in OPS:
        return False
    present = isinstance(src, dict) and field in src
    actual = src.get(field) if isinstance(src, dict) else None
    if op == "exists":
        return present
    if op == "truthy":
        return bool(actual)
    if op == "falsy":
        return not bool(actual)
    if op == "in":
        try:
            return actual in cond.get("value")
        except TypeError:
            return False
    if op == "not_in":
        try:
            return actual not in cond.get("value")
        except TypeError:
            return False
    if actual is None:           # relational op on missing/None -> fail-closed
        return False
    return _cmp(actual, cond.get("value"), op)


def edge_taken(when: dict | None, source_result: dict) -> bool:
    """True if the edge fires. None/{} -> unconditional True. Never raises."""
    try:
        if not when:
            return True
        if not isinstance(when, dict):
            return False
        src = source_result if isinstance(source_result, dict) else {}
        if "all" in when:
            subs = when.get("all") or []
            return bool(subs) and all(edge_taken(s, src) for s in subs)
        if "any" in when:
            subs = when.get("any") or []
            return any(edge_taken(s, src) for s in subs)
        return _leaf(when, src)
    except Exception:
        return False


def validate(when: dict | None, _depth: int = 0) -> list[str]:
    """Return list of error strings ([] = valid). Caught at SAVE, not run."""
    errs: list[str] = []
    if when is None or when == {}:
        return errs
    if not isinstance(when, dict):
        return ["condition must be an object"]
    if _depth > _MAX_DEPTH:
        return [f"condition nesting too deep (>{_MAX_DEPTH})"]
    if "all" in when or "any" in when:
        key = "all" if "all" in when else "any"
        subs = when.get(key)
        if not isinstance(subs, list) or not subs:
            errs.append(f"'{key}' must be a non-empty list")
        else:
            for s in subs:
                errs += validate(s, _depth + 1)
        return errs
    op = when.get("op")
    if op not in OPS:
        errs.append(f"unknown op '{op}'")
    field = when.get("field")
    if not isinstance(field, str) or not field:
        errs.append("field must be a non-empty string")
    if op in _REL and not isinstance(when.get("value"), (int, float, str, bool)):
        errs.append("value must be a scalar for relational ops")
    return errs


__all__ = ["edge_taken", "validate", "OPS"]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_edge_condition.py -q`
Expected: PASS (all).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/automation/edge_condition.py tests/test_edge_condition.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): pure fail-closed edge-condition evaluator + validator (Phase 2)"
```

---

### Task 2: Compiler — 3-tuple return + DAG path (`flow_compiler.py`)

Widen `compile_flow` to return `(result, errors, kind)`. Linear flows return the SAME `process_dict` as Phase 1 (byte-identical steps) with `kind="linear"`. New shapes (any `when`, any `merge`, indegree>1, or outdegree>1, or not-single-root) take the DAG path and return a `graph` dict with `kind="dag"`.

**Files:**
- Modify (full rewrite, additive behaviour): `app/automation/flow_compiler.py`
- Create: `tests/test_flow_compiler_dag.py`
- Modify: `tests/test_flow_compiler.py` (3-tuple unpacking + `test_branch_rejected` now compiles as dag)

**Interfaces:**
- Consumes: `app.agents.process_library.EXECUTORS`; `app.automation.edge_condition.validate` (from Task 1).
- Produces: `compile_flow(flow: dict) -> tuple[dict | None, list[str], str]` where the 3rd element `kind ∈ {"linear","dag"}`.
  - Linear success: `({"name", "steps":[...]}, [], "linear")`.
  - DAG success: `(graph_dict, [], "dag")` where `graph_dict = {"name","kind":"dag","nodes":{id:spec},"edges":[{f,t,when}],"in":{id:[{f,when}]},"out":{id:[{t,when}]},"roots":[id]}`.
  - Failure: `(None, [errors], kind)`.

- [ ] **Step 1: Write the failing DAG tests**

```python
# tests/test_flow_compiler_dag.py
from app.automation.flow_compiler import compile_flow


def _flow(nodes, edges, name="t"):
    return {"id": "f1", "name": name, "nodes": nodes, "edges": edges}


def test_linear_flow_still_linear_kind():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b"}],
    ))
    assert kind == "linear" and errs == []
    assert proc["steps"] == [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}]


def test_conditional_edge_makes_dag():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}}],
    ))
    assert kind == "dag" and errs == []
    assert proc["roots"] == ["a"]
    assert proc["out"]["a"] == [{"t": "b", "when": {"field": "count", "op": ">=", "value": 1}}]
    assert proc["in"]["b"] == [{"f": "a", "when": {"field": "count", "op": ">=", "value": 1}}]


def test_parallel_fanout_and_merge():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"},
         {"id": "b", "action": "rescore"},
         {"id": "c", "action": "harvest"},
         {"id": "m", "kind": "merge", "join": "all"}],
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"},
         {"f": "b", "t": "m"}, {"f": "c", "t": "m"}],
    ))
    assert kind == "dag" and errs == []
    assert sorted(proc["in"]["m"], key=lambda e: e["f"]) == [{"f": "b", "when": None}, {"f": "c", "when": None}]
    assert proc["nodes"]["m"]["kind"] == "merge" and proc["nodes"]["m"]["join"] == "all"


def test_indegree2_without_merge_rejected():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        [{"f": "a", "t": "c"}, {"f": "b", "t": "c"}],
    ))
    assert proc is None and kind == "dag"
    assert any("merge" in e for e in errs)


def test_cycle_rejected_dag():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        [{"f": "a", "t": "b"}, {"f": "b", "t": "c"}, {"f": "c", "t": "b"}],
    ))
    assert proc is None and any("cycle" in e for e in errs)


def test_unreachable_node_rejected():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"},
         {"id": "c", "action": "harvest"}, {"id": "d", "action": "optimizer"}],
        # a->b (linear-ish) but with a fan we force dag; c,d island reachable only from c
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}, {"f": "c", "t": "d"}, {"f": "d", "t": "c"}],
    ))
    # cycle c<->d also triggers, but the point: invalid -> None
    assert proc is None and errs


def test_bad_condition_rejected_at_compile():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b", "when": {"field": "count", "op": "BOGUS", "value": 1}}],
    ))
    assert proc is None and any("unknown op" in e for e in errs)


def test_breakpoint_outedge_condition_rejected():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"},
         {"id": "g", "kind": "breakpoint", "question": "ok?"},
         {"id": "b", "action": "rescore"},
         {"id": "c", "action": "harvest"}],
        # branch from a forces dag; breakpoint g has a conditional out-edge -> error
        [{"f": "a", "t": "g"}, {"f": "a", "t": "c"},
         {"f": "g", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}}],
    ))
    assert proc is None and any("breakpoint" in e.lower() for e in errs)


def test_unknown_action_rejected_dag():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "nope"}, {"id": "c", "action": "harvest"}],
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
    ))
    assert proc is None and any("whitelist" in e for e in errs)
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_compiler_dag.py -q`
Expected: FAIL — `compile_flow` returns a 2-tuple (`ValueError: not enough values to unpack`).

- [ ] **Step 3: Rewrite `app/automation/flow_compiler.py`**

Read the file first, then replace its entire contents with:

```python
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
    return {"name": str(flow.get("name") or "flow"), "steps": steps}, [], "linear"


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
    return graph, [], "dag"
```

- [ ] **Step 4: Update Phase-1 regression tests to the 3-tuple**

Read `tests/test_flow_compiler.py`. Change every `proc, errs = compile_flow(...)` to `proc, errs, _kind = compile_flow(...)` (8 call sites). Then REPLACE the `test_branch_rejected` function (branching is now ALLOWED — it compiles as a DAG, not an error) with:

```python
def test_branch_now_compiles_as_dag():
    proc, errs, kind = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "optimizer"}],
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
    ))
    assert kind == "dag" and errs == []
    assert proc["roots"] == ["a"]
```

(`test_cycle_rejected` stays as-is: a 2-node a↔b cycle has no root → DAG path → `cycle detected`; it asserts `proc is None and errs`, still true.)

- [ ] **Step 5: Run both compiler suites**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_compiler.py tests/test_flow_compiler_dag.py -q`
Expected: PASS (all). If `test_unreachable_node_rejected` or `test_breakpoint_outedge_condition_rejected` is flaky on ordering, confirm the error list is non-empty — those tests only assert `proc is None and <some error>`.

- [ ] **Step 6: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/automation/flow_compiler.py tests/test_flow_compiler_dag.py tests/test_flow_compiler.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): compiler 3-tuple + DAG path (branch/merge/conditions) + Phase-1 regression"
```

---

### Task 3: `get_process` tolerates the 3-tuple (`process_library.py`)

`get_process("flow:<id>")` must keep resolving LINEAR flows for `process_engine`, and return `None` for DAG flows (DAG flows are resolved by `dag_engine`, not here). One-line-ish change: unpack the 3-tuple and gate on `kind`.

**Files:**
- Modify: `app/agents/process_library.py` (the `flow:` branch inside `get_process`, lines ~229-238)
- Test: `tests/test_flow_resolver.py` (existing — must stay green; add one DAG case)

**Interfaces:**
- Consumes: `flow_compiler.compile_flow` (3-tuple, Task 2), `flow_store.get_flow`.
- Produces: `get_process("flow:<id>")` → linear `process` dict when `FLOW_RUNNER` on + flow exists + compiles linear; `None` when flag off / missing / compile-error / `kind=="dag"`.

- [ ] **Step 1: Add the failing DAG test to `tests/test_flow_resolver.py`**

Read `tests/test_flow_resolver.py`, then append:

```python
def test_dag_flow_resolves_to_none_here(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")
    fs.save_flow({"id": "dagf", "name": "d",
                  "nodes": [{"id": "a", "action": "scrape"},
                            {"id": "b", "action": "rescore"},
                            {"id": "c", "action": "harvest"}],
                  "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})
    # DAG flow -> get_process returns None (dag_engine owns it, not process_library)
    assert process_library.get_process("flow:dagf") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_resolver.py -q`
Expected: FAIL — current code does `proc, _errs = compile_flow(fl)` → `ValueError` (3-tuple now).

- [ ] **Step 3: Edit `get_process`**

In `app/agents/process_library.py`, replace this block:

```python
            fl = flow_store.get_flow(key[5:])
            if not fl:
                return None
            proc, _errs = flow_compiler.compile_flow(fl)
            return proc  # None if compile errors
```

with:

```python
            fl = flow_store.get_flow(key[5:])
            if not fl:
                return None
            proc, _errs, kind = flow_compiler.compile_flow(fl)
            return proc if kind == "linear" else None  # DAG flows resolved by dag_engine
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_resolver.py -q`
Expected: PASS (all, incl. the new DAG case + Phase-1 linear cases).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/agents/process_library.py tests/test_flow_resolver.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): get_process tolerates 3-tuple; DAG flows -> None (dag_engine owns)"
```

---

### Task 4: DAG engine (`dag_engine.py`) — the heart

Per-node, journal-derived executor that mirrors `process_engine`'s public surface but tracks a ready-set instead of a cursor. Shares the journal DIR with `process_engine`; uses a SEPARATE index file (`dag_index.jsonl`) so each engine's `ensure_alive` sees only its own runs.

**Files:**
- Create: `app/agents/dag_engine.py`
- Test: `tests/test_dag_engine.py`

**Interfaces:**
- Consumes: `flow_store.get_flow`, `flow_compiler.compile_flow` (Task 2), `edge_condition.edge_taken` (Task 1), `process_library.execute_step`/`check_gate`.
- Produces (mirrors `process_engine` so `flow_dispatch` is trivial):
  - `start_run(process_key: str, inputs: dict | None = None) -> dict` → `{ok, run_id, nodes}` | `{ok:False, error}`. Journals `run_started` with `{process, inputs, engine:"dag", graph}`.
  - `replay(run_id: str) -> dict` → `{run_id, status, process, inputs, engine:"dag", graph, nodes:{id:{state,result,retries}}, ready:[id], skip:[id], waiting:id|"", last_error, started_at, ended_at}`.
  - `async advance(run_id: str, max_steps: int = 16) -> dict` → `{run_id, status, ...}` (same status vocabulary as process_engine: `running`/`waiting_approval`/`completed`/`failed`; emits `note` on budget).
  - `approve(run_id, approved_by="admin", note="", node_id="") -> dict`; `reject(run_id, by="admin", reason="", node_id="") -> dict`.
  - `list_runs(limit=20) -> list[dict]`; `journal(run_id, limit=100) -> list[dict]`; `ensure_alive(stale_minutes=15) -> dict`.
  - Module globals (monkeypatchable): `_RUNS_DIR`, `_INDEX`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dag_engine.py
import asyncio

import app.automation.flow_store as fs
from app.agents import dag_engine, process_library


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")


def _stub_executors(monkeypatch, count_for=None):
    async def mk(name):
        async def _fn(inputs):
            c = (count_for or {}).get(name, 1)
            return {"ok": True, "count": c, "detail": f"{name}={c}"}
        return _fn
    for nm in ("scrape", "rescore", "harvest", "optimizer", "cadence_run", "revenue_sweep"):
        monkeypatch.setitem(process_library.EXECUTORS, nm, asyncio.get_event_loop().run_until_complete(mk(nm)))


def _run_to_end(rid, n=20):
    for _ in range(n):
        st = dag_engine.replay(rid)
        if st["status"] in ("completed", "failed", "waiting_approval"):
            return st
        asyncio.run(dag_engine.advance(rid))
    return dag_engine.replay(rid)


def test_if_true_branch_runs_false_skipped(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})  # count>=1 -> true branch
    fs.save_flow({"id": "iff", "name": "iff",
        "nodes": [{"id": "a", "action": "scrape"},
                  {"id": "b", "action": "rescore"},   # taken when count>=1
                  {"id": "c", "action": "harvest"}],   # taken when count<1
        "edges": [{"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                  {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}}]})
    started = dag_engine.start_run("flow:iff", {})
    assert started["ok"]
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    assert st["nodes"]["b"]["state"] == "done"
    assert st["nodes"]["c"]["state"] == "skipped"


def test_parallel_branches_then_merge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch)
    fs.save_flow({"id": "par", "name": "par",
        "nodes": [{"id": "a", "action": "scrape"},
                  {"id": "b", "action": "rescore"},
                  {"id": "c", "action": "harvest"},
                  {"id": "m", "kind": "merge", "join": "all"},
                  {"id": "d", "action": "optimizer"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"},
                  {"f": "b", "t": "m"}, {"f": "c", "t": "m"}, {"f": "m", "t": "d"}]})
    started = dag_engine.start_run("flow:par", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    for nid in ("a", "b", "c", "m", "d"):
        assert st["nodes"][nid]["state"] == "done", nid


def test_merge_any_completes_on_first(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})
    fs.save_flow({"id": "anyf", "name": "anyf",
        "nodes": [{"id": "a", "action": "scrape"},
                  {"id": "b", "action": "rescore"},
                  {"id": "c", "action": "harvest"},
                  {"id": "m", "kind": "merge", "join": "any"}],
        # only b's in-edge fires (count>=1); c's edge dead (count<1)
        "edges": [{"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                  {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}},
                  {"f": "b", "t": "m"}, {"f": "c", "t": "m"}]})
    started = dag_engine.start_run("flow:anyf", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "completed"
    assert st["nodes"]["m"]["state"] == "done"
    assert st["nodes"]["c"]["state"] == "skipped"


def test_breakpoint_in_branch_pauses_then_resumes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch)
    fs.save_flow({"id": "bpf", "name": "bpf",
        "nodes": [{"id": "a", "action": "scrape"},
                  {"id": "g", "kind": "breakpoint", "question": "send?"},
                  {"id": "b", "action": "cadence_run"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "g"}]})  # fan-out -> dag; g is breakpoint
    started = dag_engine.start_run("flow:bpf", {})
    rid = started["run_id"]
    st = _run_to_end(rid)
    assert st["status"] == "waiting_approval"
    assert st["waiting"] == "g"
    assert dag_engine.approve(rid, "tester", node_id="g")["ok"]
    st2 = _run_to_end(rid)
    assert st2["status"] == "completed"
    assert st2["nodes"]["g"]["state"] == "done"


def test_gate_fail_fails_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 0})
    fs.save_flow({"id": "gf", "name": "gf",
        "nodes": [{"id": "a", "action": "scrape", "gate": {"min_count": 1}},
                  {"id": "b", "action": "rescore"},
                  {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})  # fan-out -> dag
    started = dag_engine.start_run("flow:gf", {})
    st = _run_to_end(started["run_id"])
    assert st["status"] == "failed"


def test_replay_is_pure_repeatable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _stub_executors(monkeypatch, count_for={"scrape": 5})
    fs.save_flow({"id": "rep", "name": "rep",
        "nodes": [{"id": "a", "action": "scrape"},
                  {"id": "b", "action": "rescore"},
                  {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b", "when": {"field": "count", "op": ">=", "value": 1}},
                  {"f": "a", "t": "c", "when": {"field": "count", "op": "<", "value": 1}}]})
    rid = dag_engine.start_run("flow:rep", {})["run_id"]
    _run_to_end(rid)
    s1 = dag_engine.replay(rid)
    s2 = dag_engine.replay(rid)
    assert s1["nodes"] == s2["nodes"] and s1["status"] == s2["status"]
```

> Note on the `_stub_executors` helper: it replaces real executors with deterministic stubs returning a fixed `count`. The `asyncio.get_event_loop().run_until_complete(mk(...))` is only used to build the inner coroutine factory at setup time; if your pytest/asyncio versions warn about a closing loop, simplify `mk` to a plain (non-async) factory returning `_fn`.

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dag_engine.py -q`
Expected: FAIL — `ModuleNotFoundError: app.agents.dag_engine`.

- [ ] **Step 3: Write `app/agents/dag_engine.py`**

```python
"""DAG engine — Phase 2 branching flow runner (alongside process_engine).

Per-node, journal-derived executor. State = ready-set recomputed from the journal
each tick (the per-node analogue of process_engine's integer cursor). Shares the
journal DIR data/process_runs/ with process_engine (same record format) but uses
a SEPARATE index file (dag_index.jsonl) so each engine's watchdog sees only its
own runs. process_engine.py is byte-unchanged.

Parallelism = ready-set concurrency ACROSS ticks; one await at a time WITHIN a
tick (no asyncio.gather) — crash-safe + rate-limit-safe. Conditions are
FAIL-CLOSED (edge_condition). Import-safe, never raises.
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

_RUNS_DIR = os.path.join("data", "process_runs")          # SHARED journal dir
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
    """fired | dead | undetermined for one in/out edge, from the SOURCE node state."""
    from app.automation import edge_condition

    src = nodes.get(edge.get("f"), {})
    s = src.get("state")
    if s == "done":
        return "fired" if edge_condition.edge_taken(edge.get("when"), src.get("result") or {}) else "dead"
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
        "run_id": run_id, "status": ST_FAILED, "process": "", "inputs": {},
        "engine": "dag", "graph": {}, "nodes": {}, "ready": [], "skip": [],
        "waiting": "", "last_error": "", "started_at": "", "ended_at": "",
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
    # waiting node (if any)
    waiting = next((nid for nid, n in nodes.items() if n["state"] == "waiting"), "")
    st["waiting"] = waiting
    # ready/skip frontier (only meaningful while not terminal)
    if st["status"] not in (ST_COMPLETED, ST_FAILED):
        ready, skip = _frontier(graph, nodes)
        st["ready"], st["skip"] = ready, skip
        # status rollup
        if waiting:
            st["status"] = ST_WAITING
        elif nodes and all(n["state"] in _TERMINAL_NODE for n in nodes.values()):
            st["status"] = ST_COMPLETED  # provisional; advance emits run_completed
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
        _append_event(run_id, "run_started",
                      {"process": process_key, "inputs": inputs or {}, "engine": "dag", "graph": graph})
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
                    _append_event(run_id, "node_skipped", {"node": nid, "reason": "branch not taken"})
                continue  # recompute frontier

            if not ready:
                # nothing ready/skippable: any non-terminal left = unreachable -> skip; then complete
                for nid, n in nodes.items():
                    if n["state"] not in _TERMINAL_NODE:
                        _append_event(run_id, "node_skipped", {"node": nid, "reason": "unreachable"})
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
                _append_event(run_id, "breakpoint_waiting",
                              {"node": nid, "question": node.get("question", "Approve?")})
                try:
                    from app.platform import team

                    team.log_event("manager", "dag_breakpoint", f"{run_id}: {node.get('question', '')[:80]}")
                except Exception:
                    pass
                return {"run_id": run_id, "status": ST_WAITING, "node": nid,
                        "breakpoint": node.get("question", "")}

            if kind == "merge":
                res = {"ok": True, "count": 1, "detail": "merged"}
                _append_event(run_id, "node_completed", {"node": nid, "result": res, "ms": 0})
                _emit_out(run_id, graph, nid, res)
                done += 1
                continue

            # task node
            _append_event(run_id, "node_started", {"node": nid})
            t0 = time.monotonic()
            try:
                result = await asyncio.wait_for(
                    process_library.execute_step(node, inputs), timeout=_STEP_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                result = {"ok": False, "detail": f"timeout {_STEP_TIMEOUT_S}s"}
            except Exception as e:
                result = {"ok": False, "detail": str(e)[:200]}
            ms = round((time.monotonic() - t0) * 1000, 1)

            ok, reason = process_library.check_gate(node, result)
            if ok:
                clean = {"ok": result.get("ok"), "count": result.get("count"),
                         "detail": str(result.get("detail", ""))[:200]}
                _append_event(run_id, "node_completed", {"node": nid, "result": clean, "ms": ms})
                _emit_out(run_id, graph, nid, clean)
                done += 1
                continue

            retries = int(nodes[nid].get("retries", 0)) + 1
            max_r = int(node.get("max_retries", 1))
            _append_event(run_id, "node_gate_failed", {"node": nid, "reason": reason, "retries": retries})
            if retries > max_r:
                _append_event(run_id, "run_failed",
                              {"error": f"node '{nid}' gate fail after {retries}: {reason}", "node": nid})
                return {"run_id": run_id, "status": ST_FAILED, "error": reason, "node": nid}
            done += 1  # retry consumes budget
            continue

        return {"run_id": run_id, "status": replay(run_id)["status"],
                "note": "step budget — tick continue karega"}
    except Exception as e:
        logger.warning(f"[dag] advance failed {run_id}: {e}")
        return {"run_id": run_id, "status": ST_FAILED, "error": str(e)[:200]}


def approve(run_id: str, approved_by: str = "admin", note: str = "", node_id: str = "") -> dict[str, Any]:
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {"ok": False, "error": f"run status '{st['status']}' — koi breakpoint pending nahi"}
        nid = node_id or st.get("waiting") or ""
        if not nid or nid not in st["nodes"]:
            return {"ok": False, "error": "no waiting node"}
        _append_event(run_id, "breakpoint_approved",
                      {"node": nid, "by": approved_by[:40], "note": note[:200]})
        # breakpoint out-edges are unconditional (compiler-enforced) -> emit for UI
        for e in (st.get("graph", {}).get("out", {}).get(nid, []) or []):
            _append_event(run_id, "edge_taken", {"f": nid, "t": e.get("t")})
        return {"ok": True, "run_id": run_id, "node": nid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def reject(run_id: str, by: str = "admin", reason: str = "", node_id: str = "") -> dict[str, Any]:
    try:
        st = replay(run_id)
        if st["status"] != ST_WAITING:
            return {"ok": False, "error": f"run status '{st['status']}'"}
        _append_event(run_id, "run_failed",
                      {"error": f"rejected by {by}: {reason[:150]}", "node": node_id or st.get("waiting", "")})
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
            out.append({
                "run_id": r.get("run_id"),
                "process": st["process"] or r.get("process"),
                "status": st["status"],
                "engine": "dag",
                "nodes": len(nodes),
                "done": sum(1 for n in nodes.values() if n["state"] in _TERMINAL_NODE),
                "last_error": st["last_error"],
                "started_at": st["started_at"] or r.get("at"),
            })
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
    "start_run", "advance", "approve", "reject", "replay", "list_runs",
    "journal", "ensure_alive", "ST_RUNNING", "ST_WAITING", "ST_COMPLETED", "ST_FAILED",
]
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_dag_engine.py -q`
Expected: PASS (all 7). If `_stub_executors` triggers an asyncio loop warning, switch its factory to a plain function (drop `run_until_complete`).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/agents/dag_engine.py tests/test_dag_engine.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): dag_engine — per-node ready-set executor (branch/merge/breakpoint, crash-safe)"
```

---

### Task 5: Engine dispatcher (`flow_dispatch.py`)

Thin never-raise router so the API and `process_tick` don't branch on engine type. `engine_for(run_id)` reads `run_started.engine` from the shared journal; `start()` compiles to learn `kind` before routing.

**Files:**
- Create: `app/agents/flow_dispatch.py`
- Test: `tests/test_flow_dispatch.py`

**Interfaces:**
- Consumes: `process_engine` (read-only `_read_events`, `_INDEX`, `journal`, lifecycle), `dag_engine` (Task 4), `flow_compiler.compile_flow` (Task 2), `flow_store.get_flow`.
- Produces:
  - `engine_for(run_id) -> module` (process_engine | dag_engine; default process_engine for pre-Phase-2 runs).
  - `start(process_key, inputs=None) -> dict` (adds `"kind"`).
  - `async advance(run_id, max_steps=None) -> dict`.
  - `replay(run_id) -> dict`; `approve(run_id, approved_by="admin", note="", node_id="") -> dict`; `reject(run_id, by="admin", reason="", node_id="") -> dict`.
  - `list_runs(limit=20) -> list[dict]` (merged index); `journal(run_id, limit=100) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flow_dispatch.py
import asyncio

import app.automation.flow_store as fs
from app.agents import dag_engine, flow_dispatch, process_engine, process_library


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}
    monkeypatch.setitem(process_library.EXECUTORS, "scrape", _noop)
    monkeypatch.setitem(process_library.EXECUTORS, "rescore", _noop)
    monkeypatch.setitem(process_library.EXECUTORS, "harvest", _noop)


def test_start_routes_linear_vs_dag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow({"id": "lin", "name": "lin",
        "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        "edges": [{"f": "a", "t": "b"}]})
    fs.save_flow({"id": "dag", "name": "dag",
        "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})
    rl = flow_dispatch.start("flow:lin", {})
    rd = flow_dispatch.start("flow:dag", {})
    assert rl["ok"] and rl["kind"] == "linear"
    assert rd["ok"] and rd["kind"] == "dag"
    assert flow_dispatch.engine_for(rl["run_id"]) is process_engine
    assert flow_dispatch.engine_for(rd["run_id"]) is dag_engine


def test_pre_phase2_run_defaults_linear(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    # a run_started with no 'engine' key (Phase-1 builtin process)
    started = process_engine.start_run("growth_audit", {})
    assert flow_dispatch.engine_for(started["run_id"]) is process_engine


def test_dispatch_replay_advance_dag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow({"id": "dag2", "name": "dag2",
        "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})
    r = flow_dispatch.start("flow:dag2", {})
    rid = r["run_id"]
    for _ in range(10):
        st = flow_dispatch.replay(rid)
        if st["status"] in ("completed", "failed", "waiting_approval"):
            break
        asyncio.run(flow_dispatch.advance(rid))
    assert flow_dispatch.replay(rid)["status"] == "completed"


def test_list_runs_merges_both(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    fs.save_flow({"id": "dag3", "name": "dag3",
        "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})
    flow_dispatch.start("flow:dag3", {})
    process_engine.start_run("growth_audit", {})
    runs = flow_dispatch.list_runs(20)
    engines = {r.get("engine") for r in runs}
    assert "dag" in engines and "linear" in engines
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_dispatch.py -q`
Expected: FAIL — `ModuleNotFoundError: app.agents.flow_dispatch`.

- [ ] **Step 3: Write `app/agents/flow_dispatch.py`**

```python
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


def approve(run_id: str, approved_by: str = "admin", note: str = "", node_id: str = "") -> dict[str, Any]:
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
        out.append({
            "run_id": rid,
            "process": st.get("process") or r.get("process"),
            "status": st.get("status"),
            "engine": st.get("engine", "linear"),
            "step_index": st.get("step_index", 0),
            "nodes": len(st.get("nodes", {})) if st.get("engine") == "dag" else None,
            "last_error": st.get("last_error", ""),
            "started_at": st.get("started_at") or r.get("at"),
        })
    return out


def journal(run_id: str, limit: int = 100) -> list[dict[str, Any]]:
    from app.agents import process_engine

    return process_engine.journal(run_id, limit)  # shared JSONL reader (format-identical)


__all__ = ["engine_for", "start", "advance", "replay", "approve", "reject", "list_runs", "journal"]
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_dispatch.py -q`
Expected: PASS (all 4).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/agents/flow_dispatch.py tests/test_flow_dispatch.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): flow_dispatch — engine router (linear vs dag) + merged list_runs"
```

---

### Task 6: API routes through the dispatcher (`growth_process.py`)

Route the 5 process-lifecycle endpoints through `flow_dispatch` so they transparently serve both engines. Add optional `node_id` to the approve/reject body. No new routes; flow-CRUD routes unchanged.

**Files:**
- Modify: `app/api/growth_process.py`
- Test: `tests/test_flow_api.py` (extend with a DAG run-through-API case)

**Interfaces:**
- Consumes: `flow_dispatch` (Task 5).
- Produces: `/process/start`, `/process/runs`, `/process/run/{id}`, `/process/run/{id}/approve`, `/process/run/{id}/reject` now back both engines. `ProcessApproveIn` gains `node_id: str = ""`.

- [ ] **Step 1: Write the failing test (extend `tests/test_flow_api.py`)**

Read `tests/test_flow_api.py`, then append:

```python
import asyncio  # add near top imports if not present


def test_dag_flow_runs_through_api(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)  # FLOW_RUNNER=1, admin bypassed
    # isolate engine journals so the test worker doesn't enqueue real Celery
    from app.agents import dag_engine, process_engine, process_library
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setattr(dag_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(dag_engine, "_INDEX", str(tmp_path / "runs" / "dag_index.jsonl"))

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}
    for nm in ("scrape", "rescore", "harvest"):
        monkeypatch.setitem(process_library.EXECUTORS, nm, _noop)

    r = c.post("/api/growth/flow", json={"name": "Dag",
        "nodes": [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "harvest"}],
        "edges": [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}]})
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]

    started = c.post("/api/growth/process/start", json={"process": "flow:" + fid, "inputs": {}}).json()
    assert started.get("ok") and started.get("kind") == "dag"
    rid = started["run_id"]

    from app.agents import flow_dispatch
    for _ in range(10):
        st = flow_dispatch.replay(rid)
        if st["status"] in ("completed", "failed"):
            break
        asyncio.run(flow_dispatch.advance(rid))

    detail = c.get("/api/growth/process/run/" + rid).json()["state"]
    assert detail["status"] == "completed"
    assert detail["nodes"]["c"]["state"] == "done"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_api.py -q`
Expected: FAIL — `started["kind"]` missing / start still on `process_engine` (no dag routing).

- [ ] **Step 3: Edit `app/api/growth_process.py`**

Read the file. Make these edits (preserve the worker-down inline-advance fallback, just swap `process_engine` → `flow_dispatch`):

1. In `process_start` (the `from app.agents import process_engine` block): replace the function body's engine calls:
```python
@router.post("/process/start")
async def process_start(body: ProcessStartIn, _user=Depends(require_admin)):
    """Run start + Celery worker me advance enqueue; worker down ho to inline advance."""
    from app.agents import flow_dispatch

    r = flow_dispatch.start(body.process, body.inputs)
    if r.get("ok"):
        run_id = r.get("run_id") or ""
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            try:
                adv = await flow_dispatch.advance(run_id)
                r["queued"] = False
                r["fallback"] = "in_process"
                r["advance"] = adv
            except Exception as e2:
                r["queued"] = False
                r["hint"] = f"worker+inline fail: {str(e2)[:100]}"
    return r
```

2. `process_runs`:
```python
@router.get("/process/runs")
async def process_runs(limit: int = 20, _user=Depends(require_admin)):
    """Recent runs + journal-derived live status (both engines)."""
    from app.agents import flow_dispatch

    return {"runs": flow_dispatch.list_runs(limit)}
```

3. `process_run_detail`:
```python
@router.get("/process/run/{run_id}")
async def process_run_detail(run_id: str, _user=Depends(require_admin)):
    """Run state (replay) + full immutable journal."""
    from app.agents import flow_dispatch

    return {"state": flow_dispatch.replay(run_id), "journal": flow_dispatch.journal(run_id)}
```

4. Widen `ProcessApproveIn` and route approve/reject:
```python
class ProcessApproveIn(BaseModel):
    note: str = ""
    node_id: str = ""  # DAG: which breakpoint node (linear ignores it)


@router.post("/process/run/{run_id}/approve")
async def process_approve(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint APPROVE → run resume (Celery tick)."""
    from app.agents import flow_dispatch

    r = flow_dispatch.approve(
        run_id, approved_by=getattr(_user, "email", "admin") or "admin",
        note=body.note, node_id=body.node_id,
    )
    if r.get("ok"):
        try:
            from app.tasks.staff_jobs import process_tick

            process_tick.delay(run_id)
            r["queued"] = True
        except Exception:
            try:
                adv = await flow_dispatch.advance(run_id)
                r["queued"] = False
                r["fallback"] = "in_process"
                r["advance"] = adv
            except Exception:
                r["queued"] = False
    return r


@router.post("/process/run/{run_id}/reject")
async def process_reject(run_id: str, body: ProcessApproveIn, _user=Depends(require_admin)):
    """Breakpoint REJECT → run failed (audit trail)."""
    from app.agents import flow_dispatch

    return flow_dispatch.reject(
        run_id, by=getattr(_user, "email", "admin") or "admin",
        reason=body.note, node_id=body.node_id,
    )
```

(Leave `process_definitions` and the Flow-CRUD routes `/flows`, `/flow`, `/flow/{id}` UNCHANGED. They already use `flow_store`/`flow_compiler`; the GET preview still works — note that `flow_get`/`flow_save` already unpack `compile_flow` and were fixed for the 3-tuple? They were NOT — fix them here too, see step 4b.)

- [ ] **Step 3b: Fix the CRUD compile unpacking (3-tuple)**

In `flow_save` change `_proc, errs = flow_compiler.compile_flow(saved["flow"])` to `_proc, errs, _kind = flow_compiler.compile_flow(saved["flow"])`.
In `flow_get` change `proc, errs = flow_compiler.compile_flow(fl)` to `proc, errs, _kind = flow_compiler.compile_flow(fl)`.

- [ ] **Step 4: Run to verify it passes (+ Phase-1 API regression)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_api.py tests/test_flow_run_e2e.py -q`
Expected: PASS (all). `test_flow_run_e2e.py` (linear via process_engine) stays green; the new DAG-through-API test passes.

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/growth_process.py tests/test_flow_api.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): route process lifecycle API through flow_dispatch (serves both engines)"
```

---

### Task 7: Celery tick + watchdog + explorer structural node

`process_tick` advances via the dispatcher (so dag runs advance correctly). The watchdog gains a `dag_engine.ensure_alive()` call (separate index → no double-revive). The explorer structural `flow_runner` node's `files:` lists the 3 new modules so the reverse-sync gate + engine-module gate stay green when `team_scheduler` imports `dag_engine`.

**Files:**
- Modify: `app/tasks/staff_jobs.py` (`process_tick`, 1 line + the requeue condition already handles the `note`)
- Modify: `app/platform/team_scheduler.py` (watchdog block ~547-552)
- Modify: `frontend/explorer.html` (structural `flow_runner` node `files:` at line ~429)
- Test: none new (covered by `test_process_autostart.py` regression + Task 9 gates)

- [ ] **Step 1: Point `process_tick` at the dispatcher**

Read `app/tasks/staff_jobs.py`. In `process_tick`, replace:
```python
        from app.agents import process_engine

        res = _run_async(process_engine.advance(run_id)) or {}
```
with:
```python
        from app.agents import flow_dispatch

        res = _run_async(flow_dispatch.advance(run_id)) or {}
```
(The requeue condition below it — `res.get("status") == "running"` or the `"step budget — tick continue karega"` note — is unchanged; `dag_engine.advance` returns the same shape/note.)

- [ ] **Step 2: Add dag watchdog revive**

Read `app/platform/team_scheduler.py` around the watchdog (the `process_engine.ensure_alive()` block ~547-552). Immediately AFTER that `try/except` block, add:
```python
            try:
                from app.agents import dag_engine

                dag_engine.ensure_alive()  # stale RUNNING dag flows → process_tick revive
            except Exception:
                pass
```

- [ ] **Step 3: Update the explorer structural node `files:`**

Read `frontend/explorer.html`. At the `flow_runner` structural node (line ~429), change:
```javascript
files:'flow_store.py · flow_compiler.py · growth_process.py',
```
to:
```javascript
files:'flow_store.py · flow_compiler.py · dag_engine.py · edge_condition.py · flow_dispatch.py · growth_process.py',
```
and update the `desc:` from `…linear V1` to `…linear+DAG (branch/merge/conditions)`.

- [ ] **Step 4: Sanity import + autostart regression**

Run:
```
.venv\Scripts\python.exe -c "import app.tasks.staff_jobs, app.platform.team_scheduler, app.agents.flow_dispatch, app.agents.dag_engine; print('import ok')"
.venv\Scripts\python.exe -m pytest tests/test_process_autostart.py -q
```
Expected: `import ok`; autostart tests PASS (they use builtin linear processes — unaffected; `process_autostart.py` deliberately stays on `process_engine` since it only starts linear builtin processes).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/tasks/staff_jobs.py app/platform/team_scheduler.py frontend/explorer.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): process_tick via dispatch + dag watchdog revive + explorer node files"
```

---

### Task 8: Builder UI — conditions, merge node, skipped state (`explorer.html`)

Make the builder draw + persist `when` on edges and `merge` nodes, send them to the server, and paint per-node DAG status (incl. `skipped`). No JS test harness — manual smoke (Task 9 / deploy). There is NO client-side "linear only" lint to remove (the Phase-1 builder already relies on server compile), so that spec item is a no-op.

**Files:**
- Modify: `frontend/explorer.html` (NODE_TEMPLATES, addBuilderNode, `_frPayload`, `_frPaint`, `_frPollStart`, showBuilderPanel edge editor)

- [ ] **Step 1: Add a Merge palette template**

In `NODE_TEMPLATES` (line ~1025), add before the breakpoint entry:
```javascript
  {type:'data', badge:'MERGE', title:'Merge / Join', desc:'Join parallel branches (all/any)', kind:'merge', join:'all', files:'dag_engine.py', color:'#22d3ee'},
```

- [ ] **Step 2: Carry `join` onto created merge nodes**

In `addBuilderNode` (line ~1117), in the `node` object literal add `join: template.join,` next to `action`/`kind`:
```javascript
    action: template.action || '', kind: template.kind, join: template.join,
```

- [ ] **Step 3: Send `when` + `join` to the server**

In `_frPayload` (line ~2506), change the nodes/edges maps to include the new fields:
```javascript
    nodes: (v.nodes || []).map(n => ({id:n.id, action:n.action||'', kind:n.kind, join:n.join, title:n.title, question:n.question})),
    edges: (v.edges || []).map(e => ({f:e.f, t:e.t, when:e.when || null})),
```

- [ ] **Step 4: Paint DAG per-node status (incl. skipped)**

Replace `_frPaint` (line ~2529) with a version that handles BOTH engines:
```javascript
function _frPaint(st) {
  const nodes = st.nodes || null;  // dag -> per-node map; linear -> undefined
  const linearDone = new Set((st.steps_done||[]).map(s => s.step));
  const COLORS = {done:'2px solid #4ade80', running:'2px solid #fbbf24',
                  skipped:'2px dashed #6b7280', waiting:'2px solid #e879f9',
                  failed:'2px solid #f87171', pending:''};
  (getViewData().nodes||[]).forEach(n => {
    const el = document.getElementById('node-'+n.id);
    if(!el) return;
    if(nodes && nodes[n.id]) {
      el.style.outline = COLORS[nodes[n.id].state] || '';
      el.style.opacity = nodes[n.id].state === 'skipped' ? '0.45' : '1';
    } else {
      el.style.outline = linearDone.has(n.id) ? COLORS.done : '';
      el.style.opacity = '1';
    }
  });
}
```

- [ ] **Step 5: Tolerant run-status text (linear step vs dag nodes)**

In `_frPollStart` (line ~2558), replace the `else` status line so it works for both:
```javascript
    } else {
      const prog = st.nodes
        ? Object.values(st.nodes).filter(x=>['done','skipped'].includes(x.state)).length + '/' + Object.keys(st.nodes).length + ' nodes'
        : 'step ' + (st.step_index||0);
      _frStatus('run '+(st.status||'?')+' · '+prog);
    }
```

- [ ] **Step 6: Edge-condition editor in the builder panel**

In `showBuilderPanel` (line ~2070), replace the selected-edge block:
```javascript
  if(selectedEdge != null && activeEdges[selectedEdge]) {
    const e = activeEdges[selectedEdge];
    html += `<button class="action-btn" style="color:#f87171;margin-top:6px" onclick="removeBuilderEdge(${selectedEdge})">× Delete Selected Edge</button>`;
  }
```
with:
```javascript
  if(selectedEdge != null && activeEdges[selectedEdge]) {
    const e = activeEdges[selectedEdge];
    const w = (e.when && e.when.field) ? e.when : {field:'', op:'>=', value:''};
    const ops = ['>=','<=','>','<','==','!=','truthy','falsy','exists'];
    html += `<div class="panel-hdr">Edge Condition (when)</div>
      <div style="font-size:9px;color:#6b7280;margin-bottom:4px">Blank field = unconditional edge. Source result keys: count · ok · detail</div>
      <select class="builder-field" id="ec-field" onchange="setEdgeWhen(${selectedEdge})">
        <option value=""${!w.field?' selected':''}>(unconditional)</option>
        <option value="count"${w.field==='count'?' selected':''}>count</option>
        <option value="ok"${w.field==='ok'?' selected':''}>ok</option>
        <option value="detail"${w.field==='detail'?' selected':''}>detail</option>
      </select>
      <select class="builder-field" id="ec-op" onchange="setEdgeWhen(${selectedEdge})">
        ${ops.map(o=>`<option value="${o}"${w.op===o?' selected':''}>${o}</option>`).join('')}
      </select>
      <input class="builder-field" id="ec-value" placeholder="value" value="${(w.value!==undefined&&w.value!==null)?String(w.value).replace(/"/g,'&quot;'):''}" onchange="setEdgeWhen(${selectedEdge})">
      <button class="action-btn" style="color:#f87171;margin-top:6px" onclick="removeBuilderEdge(${selectedEdge})">× Delete Selected Edge</button>`;
  }
```
Then add a new function near `connectFromSelected` (line ~2089):
```javascript
function setEdgeWhen(idx) {
  const e = getViewData().edges[idx];
  if(!e) return;
  const field = document.getElementById('ec-field')?.value || '';
  const op = document.getElementById('ec-op')?.value || '>=';
  const valRaw = (document.getElementById('ec-value')?.value || '').trim();
  if(!field || op === 'truthy' || op === 'falsy' || op === 'exists') {
    e.when = field ? {field, op} : null;
  } else {
    const num = Number(valRaw);
    e.when = {field, op, value: (valRaw !== '' && !isNaN(num)) ? num : valRaw};
  }
  persistCustomFlow();
}
```

- [ ] **Step 7: Quick local sanity (no harness)**

Open `frontend/explorer.html` mentally / in a browser if available; confirm no JS syntax error by loading the page. (Automated coverage is the gates in Task 9; UI behaviour is smoke-tested post-deploy.)

- [ ] **Step 8: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/explorer.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): builder — edge-condition editor, merge node, per-node DAG status (skipped)"
```

---

### Task 9: Green gates + full flow suite

Prove the whole Phase-2 surface is wired and nothing regressed.

**Files:** none (verification only).

- [ ] **Step 1: Reverse-sync + drift gate**

Run: `.venv\Scripts\python.exe scripts/explorer_sync.py --check`
Expected: exit 0 — `[OK] every engine module represented · no dangling edges · no orphan nodes · all file refs resolve`. (If it FAILs on `dag_engine` missing-module: confirm Task 7 Step 3 put `dag_engine` text in explorer.html. If on `files:` not on disk: confirm `dag_engine.py`/`edge_condition.py`/`flow_dispatch.py` exist.)

- [ ] **Step 2: Prod check**

Run: `.venv\Scripts\python.exe scripts/prod_check.py`
Expected: ALL PASSED (import-safe, no route shadow, automation-gaps clean).

- [ ] **Step 3: Full flow-runner test suite (Phase 1 + Phase 2)**

Run:
```
.venv\Scripts\python.exe -m pytest tests/test_edge_condition.py tests/test_flow_compiler.py tests/test_flow_compiler_dag.py tests/test_flow_store.py tests/test_flow_resolver.py tests/test_dag_engine.py tests/test_flow_dispatch.py tests/test_flow_api.py tests/test_flow_run_e2e.py tests/test_explorer_sync.py tests/test_process_autostart.py -q
```
Expected: ALL PASS. (Linear Phase-1 behaviour unchanged; DAG Phase-2 green.)

- [ ] **Step 4: Commit (if any gate forced a fixup)**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add -A
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "test(flow-runner): Phase 2 gates green (explorer-sync + prod_check + full flow suite)"
```

---

## Deploy (after all tasks green)

1. Ship with `FLOW_RUNNER` **OFF** (DAG path stays dead). VPS pull → `docker compose -f docker-compose.vps.yml build app` → `up -d --no-deps app worker scheduler` (worker runs `process_tick`; scheduler runs the watchdog). Verify `/health` = `environment:production` (sleep 16 + 2× check).
2. Set `FLOW_RUNNER=1` in `/opt/leadgen/.env` → recreate app + worker + scheduler.
3. Smoke (admin, `/app/explorer` builder view):
   - **IF branch:** Prospector → (edge `count >= 1`) Re-score; Prospector → (edge `count < 1`) Harvest. Run → confirm one branch `done`, the other `skipped` (greyed/dashed).
   - **Parallel + merge:** Prospector → Re-score & Harvest (two edges) → Merge(all) → Optimizer. Run → all `done`.
   - **Breakpoint in branch:** any branch → Human Approval → Cadence. Run → pauses `waiting_approval`; Approve → completes.
4. Rollback = unset `FLOW_RUNNER` → routes 503, DAG path dead, linear `process_engine` untouched.

## Self-Review notes (done)

- **Spec coverage:** edge_condition §4.3→T1 · compiler 3-tuple+DAG §4.4/§6→T2 · process_library §4.5→T3 · dag_engine §4.2/§5.5/§7→T4 · flow_dispatch §4.1→T5 · API §4.6→T6 · Celery §4.7 + watchdog→T7 · builder UI §4.8→T8 · flag §4.9 (reused, no change) · tests §9→T1-9 · safety §8 (flag/admin/whitelist/fail-closed/never-raise/no-deps/linear-untouched) preserved throughout. Open questions §11 resolved per spec recommendations (serial-per-tick; one-breakpoint-blocks-all; losing `any` branch finishes/ignored; breakpoint out-edge `when` = compile error; `edge_taken` emitted for UI).
- **Spec reconciliation:** §5.2 showed `out/in` as id-lists but §7.1 uses `e.t`/`e.when`; this plan uses edge-dict adjacency (`out[n]=[{t,when}]`, `in[n]=[{f,when}]`) — the §7.1-consistent form. dag_engine uses a SEPARATE index (`dag_index.jsonl`) sharing the journal dir, so `process_engine.ensure_alive` (byte-unchanged) never double-revives dag runs; the watchdog adds `dag_engine.ensure_alive`. `test_flow_compiler.py::test_branch_rejected` is replaced (branching is now valid → dag).
- **Type consistency:** `compile_flow -> (result, errors, kind)` used identically in T2/T3/T5/T6. `dag_engine.replay` shape (`nodes`/`ready`/`skip`/`waiting`/`graph`) consumed by T4 tests + T5 list_runs + T8 paint. `approve(... node_id="")` signature consistent T4/T5/T6/T8. `flow_dispatch.start(...)["kind"]` consumed in T5/T6/T8.
- **Placeholder scan:** no TBD/"handle errors"/"similar to" — all code blocks complete.
