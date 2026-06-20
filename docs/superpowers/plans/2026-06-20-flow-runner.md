# Flow Runner (Phase 1 — linear) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the explorer's visual builder run LINEAR automation flows on the existing `process_engine` — persist flows server-side, run via the existing `/process/start` API with key `flow:<id>`, show live per-node status, honour human breakpoints.

**Architecture:** A flow `{nodes, edges}` is persisted to `data/flow_runner/flows.jsonl`. A pure compiler turns it into the engine's process-as-code shape (`{name, steps:[...]}`). `process_library.get_process()` gains a `flow:<id>` branch that loads + compiles on demand, so the EXISTING `start_run` / `process_tick` / `approve` machinery runs flows with zero new engine/worker code. Only flow-CRUD endpoints + the builder UI wiring are net-new.

**Tech Stack:** Python 3.12, FastAPI, Pydantic v2, Celery (existing `process_tick`), pytest, vanilla JS (server-rendered `frontend/explorer.html`). No new dependency, container, or DB.

## Global Constraints

- **Windows venv for all python/tests:** `C:\Users\Ratanshila\Documents\leadgenrationaiagent\.venv\Scripts\python.exe` (sandbox python is stale).
- **Windows git:** `C:\PROGRA~1\Git\cmd\git.exe`.
- **Never-raise:** every store/compiler/API/engine-hook function wraps in try/except and returns a safe value — import-safe.
- **Flag-gated:** all flow behaviour behind `FLOW_RUNNER` env (`"1"`/`"true"` = on); default OFF = INERT (routes 503, `flow:` keys unresolved).
- **Admin-only:** every flow route uses `Depends(require_admin)`.
- **Whitelist-only:** a flow task-node's `action` MUST be a key in `process_library.EXECUTORS`; unknown action = compile error. No arbitrary code.
- **V1 linear-only:** each node ≤1 in / ≤1 out edge; exactly one start node; no cycles. Branching/args/triggers = later phases (spec §11).
- **Engine reality:** the engine passes the RUN-level `inputs` dict to every executor; per-step `args` are NOT consumed in V1 (data-passing = Phase 4). The compiler therefore emits `id/action/gate?/max_retries?` for task steps and `kind/id/question` for breakpoints — NOT `args`.
- **Step/process shapes (verbatim from `process_library.py`):** task = `{"id","action","gate"?,"max_retries"?}`; breakpoint = `{"kind":"breakpoint","id","question"}`; process = `{"name","steps":[...]}`; gate = `{"min_count": N}`.
- **EXECUTORS keys (the runnable node types):** `scrape, harvest, rescore, sales_analysis, content_pack, social_drafts, cadence_run, optimizer, revenue_sweep`.

---

### Task 1: Flow compiler (pure function)

**Files:**
- Create: `app/automation/flow_compiler.py`
- Test: `tests/test_flow_compiler.py`

**Interfaces:**
- Produces: `compile_flow(flow: dict) -> tuple[dict | None, list[str]]` — returns `(process_dict, [])` on success or `(None, [errors])`. `process_dict = {"name": str, "steps": list[dict]}`.
- Consumes: `app.agents.process_library.EXECUTORS` (the action whitelist).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flow_compiler.py
from app.automation.flow_compiler import compile_flow

def _flow(nodes, edges, name="t"):
    return {"id": "f1", "name": name, "nodes": nodes, "edges": edges}

def test_valid_linear_compiles_in_order():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b"}],
    ))
    assert errs == []
    assert proc["steps"] == [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}]

def test_breakpoint_node_preserved():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"},
         {"id": "g", "kind": "breakpoint", "question": "send?"}],
        [{"f": "a", "t": "g"}],
    ))
    assert errs == []
    assert proc["steps"][1] == {"kind": "breakpoint", "id": "g", "question": "send?"}

def test_gate_and_retries_pass_through():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "content_pack", "gate": {"min_count": 1}, "max_retries": 2}], []))
    # single node, no edges -> it is the lone start+sink
    assert errs == []
    assert proc["steps"][0] == {"id": "a", "action": "content_pack", "gate": {"min_count": 1}, "max_retries": 2}

def test_empty_flow_errors():
    proc, errs = compile_flow(_flow([], []))
    assert proc is None and any("no nodes" in e for e in errs)

def test_dangling_edge_errors():
    proc, errs = compile_flow(_flow([{"id": "a", "action": "scrape"}], [{"f": "a", "t": "zzz"}]))
    assert proc is None and any("zzz" in e for e in errs)

def test_unknown_action_errors():
    proc, errs = compile_flow(_flow([{"id": "a", "action": "definitely_not_real"}], []))
    assert proc is None and any("whitelist" in e for e in errs)

def test_branch_rejected():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}, {"id": "c", "action": "optimizer"}],
        [{"f": "a", "t": "b"}, {"f": "a", "t": "c"}],
    ))
    assert proc is None and any("linear" in e for e in errs)

def test_cycle_rejected():
    proc, errs = compile_flow(_flow(
        [{"id": "a", "action": "scrape"}, {"id": "b", "action": "rescore"}],
        [{"f": "a", "t": "b"}, {"f": "b", "t": "a"}],
    ))
    assert proc is None and errs  # two start nodes (none indeg 0) OR cycle -> error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_compiler.py -q`
Expected: FAIL — `ModuleNotFoundError: app.automation.flow_compiler`.

- [ ] **Step 3: Write the implementation**

```python
# app/automation/flow_compiler.py
"""Flow compiler — visual {nodes, edges} -> process_engine process-as-code.
Pure, no side-effects, never-raise. V1: LINEAR only, whitelisted actions.
"""
from __future__ import annotations

from typing import Any


def compile_flow(flow: dict) -> tuple[dict | None, list[str]]:
    """Return (process_dict | None, errors). process_dict = {name, steps:[...]}.
    Task step = {id, action, gate?, max_retries?}; breakpoint = {kind, id, question}.
    Per-step `args` is intentionally dropped (engine uses run-level inputs in V1)."""
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_compiler.py -q`
Expected: PASS (8 passed).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/automation/flow_compiler.py tests/test_flow_compiler.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): pure linear flow->process compiler + tests"
```

---

### Task 2: Flow store (persistence)

**Files:**
- Create: `app/automation/flow_store.py`
- Test: `tests/test_flow_store.py`

**Interfaces:**
- Produces: `save_flow(flow: dict, by: str = "admin") -> dict` (`{"ok": bool, "flow": rec}` or `{"ok": False, "error"}`), `get_flow(flow_id: str) -> dict | None`, `list_flows() -> list[dict]`, `delete_flow(flow_id: str) -> bool`. Module globals `_DIR`, `_PATH` (monkeypatchable in tests).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flow_store.py
import app.automation.flow_store as fs

def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "flow_runner"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "flow_runner" / "flows.jsonl"))

def test_save_assigns_id_and_get_roundtrip(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    r = fs.save_flow({"name": "Demo", "nodes": [{"id": "a", "action": "scrape"}], "edges": []})
    assert r["ok"] and r["flow"]["id"].startswith("flow_")
    got = fs.get_flow(r["flow"]["id"])
    assert got["name"] == "Demo" and len(got["nodes"]) == 1

def test_upsert_keeps_id(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    a = fs.save_flow({"id": "fixed", "name": "v1", "nodes": [], "edges": []})
    b = fs.save_flow({"id": "fixed", "name": "v2", "nodes": [], "edges": []})
    assert a["flow"]["id"] == b["flow"]["id"] == "fixed"
    assert fs.get_flow("fixed")["name"] == "v2"
    assert len(fs.list_flows()) == 1

def test_list_and_delete(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    fs.save_flow({"id": "x", "name": "X", "nodes": [], "edges": []})
    assert any(f["id"] == "x" for f in fs.list_flows())
    assert fs.delete_flow("x") is True
    assert fs.get_flow("x") is None

def test_bad_input_rejected(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    assert fs.save_flow("not-a-dict")["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_store.py -q`
Expected: FAIL — `ModuleNotFoundError: app.automation.flow_store`.

- [ ] **Step 3: Write the implementation**

```python
# app/automation/flow_store.py
"""Flow store — persist explorer builder flows for the Flow Runner.
JSONL at data/flow_runner/flows.jsonl (shared ./data bind-mount, web+worker).
Upsert by id (rewrite). Import-safe, never-raise.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DIR = os.path.join("data", "flow_runner")
_PATH = os.path.join(_DIR, "flows.jsonl")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_all() -> dict[str, dict]:
    out: dict[str, dict] = {}
    try:
        if os.path.exists(_PATH):
            with open(_PATH, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                        fid = rec.get("id")
                        if fid:
                            out[fid] = rec
                    except Exception:
                        pass
    except Exception as e:
        logger.warning(f"[flow_store] read failed: {e}")
    return out


def _rewrite(flows: dict[str, dict]) -> bool:
    try:
        os.makedirs(_DIR, exist_ok=True)
        tmp = _PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for rec in flows.values():
                f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
        os.replace(tmp, _PATH)
        return True
    except Exception as e:
        logger.warning(f"[flow_store] rewrite failed: {e}")
        return False


def save_flow(flow: dict, by: str = "admin") -> dict:
    try:
        if not isinstance(flow, dict):
            return {"ok": False, "error": "flow must be an object"}
        fid = str(flow.get("id") or "").strip() or f"flow_{uuid.uuid4().hex[:8]}"
        rec = {
            "id": fid,
            "name": str(flow.get("name") or "Untitled flow")[:120],
            "nodes": flow.get("nodes") or [],
            "edges": flow.get("edges") or [],
            "created_by": str(flow.get("created_by") or by)[:60],
            "updated_at": _now(),
        }
        flows = _read_all()
        flows[fid] = rec
        if not _rewrite(flows):
            return {"ok": False, "error": "persist failed"}
        return {"ok": True, "flow": rec}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def get_flow(flow_id: str) -> dict | None:
    return _read_all().get((flow_id or "").strip())


def list_flows() -> list[dict]:
    out = []
    for rec in _read_all().values():
        out.append({
            "id": rec.get("id"),
            "name": rec.get("name"),
            "nodes": len(rec.get("nodes") or []),
            "edges": len(rec.get("edges") or []),
            "updated_at": rec.get("updated_at"),
        })
    return sorted(out, key=lambda r: r.get("updated_at") or "", reverse=True)


def delete_flow(flow_id: str) -> bool:
    fid = (flow_id or "").strip()
    flows = _read_all()
    if fid in flows:
        del flows[fid]
        return _rewrite(flows)
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_store.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/automation/flow_store.py tests/test_flow_store.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): server-side flow store (jsonl upsert) + tests"
```

---

### Task 3: `get_process` flow resolver hook + flag

**Files:**
- Modify: `app/agents/process_library.py` (the `get_process` function, currently `def get_process(key): return PROCESSES.get((key or "").strip().lower())`)
- Test: `tests/test_flow_resolver.py`

**Interfaces:**
- Consumes: `flow_store.get_flow`, `flow_compiler.compile_flow`.
- Produces: `get_process("flow:<id>")` returns the compiled process dict when `FLOW_RUNNER` on + flow exists + compiles; else `None`. Static keys unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_resolver.py
import app.automation.flow_store as fs
from app.agents import process_library


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    fs.save_flow({"id": "demo", "name": "d",
                  "nodes": [{"id": "a", "action": "scrape"}], "edges": []})

def test_flow_resolves_when_flag_on(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.setenv("FLOW_RUNNER", "1")
    proc = process_library.get_process("flow:demo")
    assert proc and proc["steps"][0]["action"] == "scrape"

def test_flow_none_when_flag_off(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch)
    monkeypatch.delenv("FLOW_RUNNER", raising=False)
    assert process_library.get_process("flow:demo") is None

def test_static_process_still_resolves(monkeypatch):
    assert process_library.get_process("growth_audit") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_resolver.py -q`
Expected: FAIL — `test_flow_resolves_when_flag_on` returns None (no `flow:` branch yet).

- [ ] **Step 3: Edit `get_process`**

Replace the existing function:
```python
def get_process(key: str) -> dict[str, Any] | None:
    return PROCESSES.get((key or "").strip().lower())
```
with:
```python
def get_process(key: str) -> dict[str, Any] | None:
    key = (key or "").strip()
    if key.lower().startswith("flow:"):
        import os

        if os.getenv("FLOW_RUNNER", "0") not in ("1", "true", "True"):
            return None
        try:
            from app.automation import flow_compiler, flow_store

            fl = flow_store.get_flow(key[5:])
            if not fl:
                return None
            proc, _errs = flow_compiler.compile_flow(fl)
            return proc  # None if compile errors
        except Exception:
            return None
    return PROCESSES.get(key.lower())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_resolver.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/agents/process_library.py tests/test_flow_resolver.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): get_process resolves flow:<id> (flag-gated)"
```

---

### Task 4: Flow-CRUD API (extend `growth_process.py`)

**Files:**
- Modify: `app/api/growth_process.py` (add imports + 4 routes at end of file)
- Test: `tests/test_flow_api.py`

**Interfaces:**
- Produces routes (paths under the router's `/api/growth` mount): `GET /flows`, `POST /flow`, `GET /flow/{id}`, `DELETE /flow/{id}`. All `require_admin` + `FLOW_RUNNER` gated.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_flow_api.py
import importlib

import app.automation.flow_store as fs
from fastapi.testclient import TestClient


def _client(tmp_path, monkeypatch, flag="1"):
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    if flag is None:
        monkeypatch.delenv("FLOW_RUNNER", raising=False)
    else:
        monkeypatch.setenv("FLOW_RUNNER", flag)
    # bypass admin auth
    from app.api import auth_deps
    from app.main import app
    app.dependency_overrides[auth_deps.require_admin] = lambda: type("U", (), {"email": "t@t"})()
    return TestClient(app)


def test_flag_off_503(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch, flag=None)
    assert c.get("/api/growth/flows").status_code == 503

def test_create_get_delete(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/growth/flow", json={"name": "Demo",
        "nodes": [{"id": "a", "action": "scrape"}], "edges": []})
    assert r.status_code == 200 and r.json()["runnable"] is True
    fid = r.json()["flow"]["id"]
    assert c.get(f"/api/growth/flow/{fid}").json()["runnable"] is True
    assert c.delete(f"/api/growth/flow/{fid}").json()["ok"] is True

def test_invalid_flow_reports_compile_errors(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/api/growth/flow", json={"name": "Bad",
        "nodes": [{"id": "a", "action": "nope"}], "edges": []})
    assert r.status_code == 200 and r.json()["runnable"] is False
    assert r.json()["compile_errors"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_api.py -q`
Expected: FAIL — routes 404 (not yet added).

- [ ] **Step 3: Append routes to `app/api/growth_process.py`**

Add at the top with the other imports:
```python
import os

from fastapi.responses import JSONResponse
```
Append at the END of the file:
```python
# ------------- Flow Runner (visual builder -> process-as-code, flag-gated) ------------- #
def _flow_runner_on() -> bool:
    return os.getenv("FLOW_RUNNER", "0") in ("1", "true", "True")


class FlowIn(BaseModel):
    id: str | None = None
    name: str = "Untitled flow"
    nodes: list[dict] = []
    edges: list[dict] = []


@router.get("/flows")
async def flows_list(_user=Depends(require_admin)):
    """List saved builder flows (Flow Runner)."""
    if not _flow_runner_on():
        return JSONResponse({"error": "FLOW_RUNNER disabled"}, status_code=503)
    from app.automation import flow_store

    return {"flows": flow_store.list_flows()}


@router.post("/flow")
async def flow_save(body: FlowIn, _user=Depends(require_admin)):
    """Create/update a flow + return compile preview (runnable?)."""
    if not _flow_runner_on():
        return JSONResponse({"error": "FLOW_RUNNER disabled"}, status_code=503)
    from app.automation import flow_compiler, flow_store

    saved = flow_store.save_flow(body.model_dump(), by=getattr(_user, "email", "admin") or "admin")
    if not saved.get("ok"):
        return saved
    _proc, errs = flow_compiler.compile_flow(saved["flow"])
    return {"ok": True, "flow": saved["flow"], "compile_errors": errs, "runnable": not errs}


@router.get("/flow/{flow_id}")
async def flow_get(flow_id: str, _user=Depends(require_admin)):
    """Get a flow + compiled steps + compile errors."""
    if not _flow_runner_on():
        return JSONResponse({"error": "FLOW_RUNNER disabled"}, status_code=503)
    from app.automation import flow_compiler, flow_store

    fl = flow_store.get_flow(flow_id)
    if not fl:
        return JSONResponse({"error": "not found"}, status_code=404)
    proc, errs = flow_compiler.compile_flow(fl)
    return {"flow": fl, "compile_errors": errs, "steps": (proc or {}).get("steps", []), "runnable": not errs}


@router.delete("/flow/{flow_id}")
async def flow_delete(flow_id: str, _user=Depends(require_admin)):
    """Delete a flow."""
    if not _flow_runner_on():
        return JSONResponse({"error": "FLOW_RUNNER disabled"}, status_code=503)
    from app.automation import flow_store

    return {"ok": flow_store.delete_flow(flow_id)}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_api.py -q`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/growth_process.py tests/test_flow_api.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): flow CRUD API on growth_process router (flag-gated, admin-only)"
```

---

### Task 5: End-to-end run (integration test — no UI)

Proves a saved flow runs through the EXISTING engine via key `flow:<id>`: start → advance task → breakpoint → approve → complete. Uses a stub executor so no network.

**Files:**
- Test: `tests/test_flow_run_e2e.py`

**Interfaces:**
- Consumes: `process_engine.start_run`, `process_engine.advance`, `process_engine.approve`, `process_engine.replay`; `process_library.EXECUTORS` (monkeypatched stub).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_flow_run_e2e.py
import asyncio

import app.automation.flow_store as fs
from app.agents import process_engine, process_library


def test_flow_runs_start_to_completion(tmp_path, monkeypatch):
    # isolate stores
    monkeypatch.setattr(fs, "_DIR", str(tmp_path / "fr"))
    monkeypatch.setattr(fs, "_PATH", str(tmp_path / "fr" / "flows.jsonl"))
    monkeypatch.setattr(process_engine, "_RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setattr(process_engine, "_INDEX", str(tmp_path / "runs" / "index.jsonl"))
    monkeypatch.setenv("FLOW_RUNNER", "1")

    async def _noop(inputs):
        return {"ok": True, "count": 5, "detail": "stub"}
    monkeypatch.setitem(process_library.EXECUTORS, "noop", _noop)

    fs.save_flow({"id": "e2e", "name": "e2e",
        "nodes": [{"id": "s", "action": "noop"},
                  {"id": "g", "kind": "breakpoint", "question": "ok?"},
                  {"id": "s2", "action": "noop"}],
        "edges": [{"f": "s", "t": "g"}, {"f": "g", "t": "s2"}]})

    started = process_engine.start_run("flow:e2e", {})
    assert started["ok"]
    rid = started["run_id"]

    # advance to the breakpoint
    asyncio.run(process_engine.advance(rid))
    assert process_engine.replay(rid)["status"] == "waiting_approval"

    # approve + advance to completion
    assert process_engine.approve(rid, "tester")["ok"]
    asyncio.run(process_engine.advance(rid))
    assert process_engine.replay(rid)["status"] == "completed"
```

- [ ] **Step 2: Run test to verify it fails (then passes)**

Run: `.venv\Scripts\python.exe -m pytest tests/test_flow_run_e2e.py -q`
Expected: With Tasks 1-3 done, this should PASS immediately (it exercises existing engine + the new resolver). If it FAILS, the failure pinpoints a resolver/compiler bug — fix before moving on. (This task is a guard test; no new production code unless it surfaces a bug.)

- [ ] **Step 3: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add tests/test_flow_run_e2e.py
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "test(flow-runner): e2e run start->breakpoint->approve->complete via flow:<id>"
```

---

### Task 6: Builder UI wiring (`frontend/explorer.html`)

Make the builder save to the server, run a flow, poll status, and approve breakpoints. UI = manual smoke (no JS test harness in repo).

**Files:**
- Modify: `frontend/explorer.html` (builder palette `NODE_TEMPLATES`, builder toolbar, JS functions)

**Interfaces:**
- Calls: `POST /api/growth/flow`, `GET /api/growth/flow/{id}`, `POST /api/growth/process/start` (`{process:"flow:<id>"}`), `GET /api/growth/process/run/{run_id}`, `POST /api/growth/process/run/{run_id}/approve`.

- [ ] **Step 1: Give builder nodes a runnable `action`**

In `NODE_TEMPLATES` (around line 1017), set each template's `action` to an EXECUTORS key and add a breakpoint template. Replace the array so every entry carries `action` (or `kind:'breakpoint'`):
```javascript
const NODE_TEMPLATES = [
  {type:'platform', badge:'TRIGGER', title:'Manual Start', desc:'Run button se flow start', action:'', color:'#60a5fa'},
  {type:'marketing', badge:'SCRAPE', title:'Prospector', desc:'Leads scrape + enrich', action:'scrape', color:'#3b82f6'},
  {type:'marketing', badge:'HARVEST', title:'Lead Harvester', desc:'Multi-source harvest', action:'harvest', color:'#3b82f6'},
  {type:'data', badge:'SCORE', title:'Re-score Leads', desc:'lead_scoring rescore', action:'rescore', color:'#22d3ee'},
  {type:'ai', badge:'ANALYZE', title:'Sales Deep-dive', desc:'BANT analysis (draft)', action:'sales_analysis', color:'#818cf8'},
  {type:'marketing', badge:'CONTENT', title:'Content Pack', desc:'Niche content pack', action:'content_pack', color:'#3b82f6'},
  {type:'marketing', badge:'SOCIAL', title:'Social Drafts', desc:'Draft social posts', action:'social_drafts', color:'#3b82f6'},
  {type:'marketing', badge:'CADENCE', title:'Cadence Run', desc:'Omnichannel touches (gated)', action:'cadence_run', color:'#3b82f6'},
  {type:'monitor', badge:'OPTIMIZE', title:'Growth Optimizer', desc:'Funnel weakest-stage', action:'optimizer', color:'#fbbf24'},
  {type:'platform', badge:'REVENUE', title:'Revenue Sweep', desc:'Dunning + nurture (draft)', action:'revenue_sweep', color:'#60a5fa'},
  {type:'loop', badge:'APPROVE', title:'Human Approval', desc:'Breakpoint — admin approve to continue', kind:'breakpoint', color:'#e879f9'},
];
```
Ensure `addBuilderNode(template, ...)` copies `action` and `kind` onto the created node (check the function near line 1109; add `action: template.action, kind: template.kind` to the node object if not already carried).

- [ ] **Step 2: Add toolbar buttons**

In the builder toolbar (near the existing `exportFlow()` button, line ~300), add:
```html
<button class="tr-btn" onclick="saveFlowToServer()">💾 Save to Server</button>
<button class="tr-btn" onclick="runFlow()" id="runFlowBtn">▶ Run</button>
<span id="flowRunStatus" style="margin-left:8px;color:#9ca3af"></span>
```

- [ ] **Step 3: Add JS (near the other builder functions, after `exportFlow`)**

```javascript
let activeFlowId = null, activeRunId = null, runPoll = null;

function _activeFlowPayload() {
  const f = customFlowStore.flows[customFlowStore.activeId] || {};
  return {
    id: activeFlowId || undefined,
    name: f.name || 'Untitled flow',
    nodes: (f.nodes || []).map(n => ({id:n.id, action:n.action||'', kind:n.kind, title:n.title, question:n.question})),
    edges: (f.edges || []).map(e => ({f:e.f, t:e.t})),
  };
}

async function _api(path, opts) {
  for (const base of getApiBases()) {
    try {
      const r = await fetch(base + path, Object.assign({headers:{'Content-Type':'application/json'}}, opts));
      if (r.status !== 404) return await r.json();
    } catch(e) {}
  }
  return null;
}

async function saveFlowToServer() {
  const res = await _api('/api/growth/flow', {method:'POST', body: JSON.stringify(_activeFlowPayload())});
  if (res && res.flow) {
    activeFlowId = res.flow.id;
    document.getElementById('flowRunStatus').textContent =
      res.runnable ? 'saved ✓ (runnable)' : 'saved — errors: ' + (res.compile_errors||[]).join('; ');
  } else {
    document.getElementById('flowRunStatus').textContent = 'save failed (FLOW_RUNNER off?)';
  }
}

async function runFlow() {
  if (!activeFlowId) { await saveFlowToServer(); }
  if (!activeFlowId) return;
  const res = await _api('/api/growth/process/start', {method:'POST', body: JSON.stringify({process:'flow:'+activeFlowId, inputs:{}})});
  if (res && res.run_id) { activeRunId = res.run_id; _startPolling(); }
  else { document.getElementById('flowRunStatus').textContent = 'run failed: ' + JSON.stringify(res); }
}

function _startPolling() {
  if (runPoll) clearInterval(runPoll);
  runPoll = setInterval(async () => {
    const res = await _api('/api/growth/process/run/' + activeRunId, {method:'GET'});
    const st = (res && res.state) || {};
    const el = document.getElementById('flowRunStatus');
    el.textContent = 'run ' + (st.status||'?') + ' · step ' + (st.step_index||0);
    _paintRunStatus(st);
    if (st.status === 'waiting_approval') {
      el.innerHTML = 'WAITING: ' + (st.last_error||'approval') +
        ' <button class="tr-btn" onclick="approveRun()">✓ Approve</button>';
    }
    if (st.status === 'completed' || st.status === 'failed') { clearInterval(runPoll); runPoll = null; }
  }, 2000);
}

async function approveRun() {
  await _api('/api/growth/process/run/' + activeRunId + '/approve', {method:'POST', body: JSON.stringify({note:'ok'})});
}

function _paintRunStatus(st) {
  // mark builder nodes done/running using replay steps_done + step_index
  const done = new Set((st.steps_done||[]).map(s => s.step));
  (((customFlowStore.flows[customFlowStore.activeId]||{}).nodes)||[]).forEach((n,i) => {
    const el = document.querySelector('[data-node-id="'+n.id+'"]');
    if (!el) return;
    el.style.outline = done.has(n.id) ? '2px solid #4ade80'
      : (i === (st.step_index||0) ? '2px solid #fbbf24' : 'none');
  });
}
```
(Adjust `data-node-id` selector / paint logic to match how builder nodes are rendered in this file — find the builder node render function and reuse its id attribute.)

- [ ] **Step 4: Manual smoke (documented, not automated)**

After deploy with `FLOW_RUNNER=1`:
1. Open `/app/explorer` → builder view → drag Prospector → Re-score → Run. Watch status reach `completed`.
2. Build Prospector → Approval → Revenue Sweep → Run → confirm it pauses at `waiting_approval`, click Approve, confirm `completed`.

- [ ] **Step 5: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add frontend/explorer.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): builder save-to-server + Run + live status + approve UI"
```

---

### Task 7: Flag registry + explorer node + green gates

**Files:**
- Modify: `app/api/growth.py` (`AUTOMATION_FLAGS` list — add `"FLOW_RUNNER"`)
- Modify: `frontend/explorer.html` (structural view — add `flow_runner` node + edges)

- [ ] **Step 1: Register the flag**

In `app/api/growth.py`, find `AUTOMATION_FLAGS = [` and add `"FLOW_RUNNER",` to the list (so it shows in `GET /api/growth/infra/flags`).

- [ ] **Step 2: Add explorer node (structural view)**

In `frontend/explorer.html` structural-view `nodes:[...]`, near the `process`/`celery` nodes, add:
```javascript
      {id:'flow_runner', type:'platform', badge:'FLOW', cx:'moderate', title:'Flow Runner', desc:'Visual builder → process-as-code execution · FLOW_RUNNER · admin · linear V1', files:'flow_store.py · flow_compiler.py · growth_process.py', flag:'FLOW_RUNNER', x:1260, y:1240, w:260, h:100},
```
and edges (in the same view's `edges:[...]`):
```javascript
      {f:'explorer', t:'flow_runner', lbl:'builder', style:'sync'},
      {f:'flow_runner', t:'process', lbl:'compile→run', style:'async'},
      {f:'flow_runner', t:'data', lbl:'flows.jsonl', style:'sync'},
```
(Place coordinates so it doesn't overlap; adjust x/y if the validator reports overlap.)

- [ ] **Step 3: Verify gates green**

Run:
```
.venv\Scripts\python.exe scripts/explorer_sync.py --check
.venv\Scripts\python.exe scripts/prod_check.py
.venv\Scripts\python.exe -m pytest tests/test_flow_compiler.py tests/test_flow_store.py tests/test_flow_resolver.py tests/test_flow_api.py tests/test_flow_run_e2e.py tests/test_explorer_sync.py -q
```
Expected: explorer `--check` exit 0 (new node files resolve via reverse-sync gate) · prod_check ALL PASSED · all flow tests + explorer tests green.

- [ ] **Step 4: Commit**

```bash
"C:\PROGRA~1\Git\cmd\git.exe" add app/api/growth.py frontend/explorer.html
"C:\PROGRA~1\Git\cmd\git.exe" commit -m "feat(flow-runner): FLOW_RUNNER flag registry + explorer node (gates green)"
```

---

## Deploy (after all tasks green)

1. Ship with `FLOW_RUNNER` **OFF** → VPS pull → `docker compose -f docker-compose.vps.yml build app` → `up -d --no-deps app worker` (worker too — `process_tick` runs there). Verify `/health` = production.
2. Set `FLOW_RUNNER=1` in `/opt/leadgen/.env` → recreate app + worker.
3. Smoke per Task 6 Step 4. Rollback = unset `FLOW_RUNNER` → routes 503, zero other surface.

## Self-Review notes (done)

- **Spec coverage:** flow_store (§4.1)→T2 · compiler (§4.2)→T1 · get_process hook (§4.3)→T3 · CRUD API (§4.4)→T4 · run reuse→T5 · UI (§4.5)→T6 · flag (§4.6)+explorer node (§4.7)→T7 · tests (§7)→T1-5,7 · rollout (§8)→Deploy. All covered.
- **Type consistency:** `compile_flow -> (dict|None, list[str])` used identically in T1/T3/T4. `save_flow -> {"ok","flow"}` used in T2/T4/T5. Step shapes match `process_library` verbatim.
- **No per-step args** (engine ignores them in V1) — compiler omits `args`; documented in Global Constraints.
