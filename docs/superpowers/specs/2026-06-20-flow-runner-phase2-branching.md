# Flow Runner — Phase 2: Branching / DAG — Design Spec

> **Status:** Draft (ready for plan-eng-review) — Phase 1 (linear flow runner) shipped 2026-06-20.
> **Decision:** **(b) New `dag_engine.py` module alongside `process_engine.py`.** Linear flows keep using `process_engine` UNCHANGED. The `flow:` resolver routes DAG flows to the new engine. Justification in §3.0.
> **Scope discipline:** branching (IF/Switch on a prior step's result) + parallel branches + merge/join ONLY. **Data-passing between nodes = Phase 4** — explicitly NOT designed here (seam noted in §5.6). Same guardrails as Phase 1: flag-OFF default, admin-only, whitelist executors, draft-safe breakpoints, free-stack, additive, never-raise, no new deps, reuse Celery `process_tick`.

---

## 1. Why (problem)

Phase 1 made a **linear** visually-built flow executable on `process_engine`. The n8n-parity CORE — and the actual reason a visual canvas beats a code list — is **branching**: "if the scrape found ≥1 lead, run cadence; else run harvest", run two branches **in parallel**, then **merge** before a human-approval send. Today the compiler (`app/automation/flow_compiler.py`) **rejects** any node with >1 incoming or >1 outgoing edge ("V1 is linear only") and rejects cycles. So the builder canvas — which can already *draw* forks and joins — cannot run them.

The HARD problem: `process_engine.replay()` derives **all** run state from a single integer `step_index` walking an **ordered** `steps[]` list (`process_engine.py:118` `st["step_index"] = int(d.get("index")) + 1`). One cursor, one path. A DAG needs:
- **Per-node state** (`pending` / `running` / `done` / `skipped` / `failed`) — not one cursor.
- **Conditional edge evaluation** — an edge fires only if its `when` condition holds against the **source node's result**.
- **Ready-set scheduling** — a node becomes runnable when **all** its satisfied incoming edges' sources are `done` (join semantics).
- **Skip propagation** — when a branch is not taken, its nodes (and their exclusive descendants) become `skipped`, not stuck `pending`.

This cannot be bolted onto a monotonic cursor without rewriting the heart of `process_engine` and risking the 3 prod-tested linear processes (`lead_campaign`, `client_content`, `growth_audit`). Phase 2 introduces a **parallel DAG executor** that shares the same journal/replay/breakpoint/Celery philosophy but tracks **per-node** progress.

## 2. Goal / Non-goals

**Goal (Phase 2):** An admin can build a flow with **conditional edges** (`when` on a source result), **parallel fan-out**, and **merge/join** nodes; **save** it; **run** it; watch **per-node** live status (incl. `skipped` branches) on the canvas; and **approve breakpoints inside any branch** — all executed by a new `dag_engine`, fully inside the existing journal / RBAC / `FLOW_RUNNER` flag / compliance gates.

**Non-goals (Phase 2 — sequenced into the §11 roadmap of the Phase-1 spec, not dropped):**
- **Data-passing** node-output → downstream-input (key-map / expressions). **Phase 4.** Edge conditions read the **source step's own result dict** only (the result the engine already has in hand) — no upstream-output plumbing into executor inputs. Seam in §5.6.
- Cron / event triggers (manual run only — Phase 3).
- Arbitrary code/HTTP nodes, new side-effecting actions, retry-policy UI, per-tenant builder (Phases 5–7).
- **Loops / cycles** — still rejected. A DAG with a real loop needs visit-counting + loop-budget semantics; out of scope. Phase 2 = strict **DAG** (acyclic).
- Replacing or modifying `process_engine` for linear flows — it stays byte-for-byte as shipped.

## 3. Architecture

### 3.0 The decision: (b) new `dag_engine.py`, justified

| | (a) Generalize `process_engine` to a DAG executor | **(b) New `dag_engine.py` alongside** ← CHOSEN |
|---|---|---|
| `replay()` | Rewrite cursor→per-node map; every linear branch re-tested | Untouched; linear flows bit-identical |
| Risk to 3 prod processes | High (shared replay/advance rewrite) | **Zero** (no edits to process_engine) |
| Journal compat | Must keep old events meaning the same AND add new | Old journal = process_engine's; DAG runs get a **distinct event vocabulary** in the **same file format/dir** |
| Breakpoint logic | Reused but entangled with new branch logic | Reimplemented small + clean (per-node) |
| Rollback | Risky (can't un-rewrite replay) | **Trivial** — `FLOW_RUNNER` off ⇒ resolver returns nothing ⇒ DAG path dead |
| Code added | ~same | ~same, but **isolated + independently testable** |

**Why (b):** the linear engine's invariant ("state = one integer over an ordered list") is *load-bearing* and prod-proven; bending it into a DAG would make `replay` simultaneously serve two state models. (b) keeps the battle-tested linear path frozen and puts the genuinely-different scheduling logic in its own never-raise module. Both engines **share**: `data/process_runs/<run_id>.jsonl` journal dir, the `_append_event`/`_read_events` JSONL convention, the EXECUTORS whitelist (`process_library.execute_step` / `check_gate`), the `process_tick` Celery task, and the `growth_process.py` run/approve/status API. We add a **thin dispatch shim** so the API and Celery task call the right engine per run.

### 3.1 Wiring diagram

```
[Explorer builder UI]                    [Server / app]                       [Celery worker]
 nodes+edges (with when: on edges,  --save-->  POST /api/growth/flow  --> data/flow_runner/flows.jsonl
   merge: nodes)                                                              (shared ./data bind-mount)
        |                                                                            |
        |  --run-->  POST /api/growth/process/start {process:"flow:<id>"}            |
        |     -> flow_compiler.compile_flow(flow)  -> kind: "linear" | "dag"         |
        |        linear ->  process_engine.start_run  (UNCHANGED)                    |
        |        dag    ->  dag_engine.start_run      (NEW)                          |
        |                     -> journal data/process_runs/<run_id>.jsonl           |
        |                                                       process_tick(run_id):
        |  poll GET .../run/{run_id}                              engine_for(run_id).advance()
        |     -> engine_for(run_id).replay()   <-- (linear: step_index | dag: node_states + ready-set)
        |     -> per-node {pending|running|done|skipped|failed|waiting} -> animate canvas
        |  approve breakpoint --> POST .../run/{run_id}/approve --> engine_for(run_id).approve(node_id)
```

**Single dispatch point** = `app/agents/flow_dispatch.py` (NEW, §4.1): `engine_for(run_id) -> module` reads the run's first journal event (`run_started` carries `engine: "linear"|"dag"`) and returns `process_engine` or `dag_engine`. The API and `process_tick` call **through** the dispatcher, so neither needs to know which engine a run uses. Compile decides which engine a flow needs (`compile_flow` returns `kind`), and `start_run` stamps `engine` into the first journal event.

## 4. Components (each isolated, testable — exact file paths)

### 4.1 Engine dispatcher — `app/agents/flow_dispatch.py` (NEW)
Thin, never-raise router so callers don't branch on engine type.
```python
def engine_for(run_id: str):
    """Return the engine MODULE that owns run_id (reads run_started.engine).
    Default = process_engine (back-compat: pre-Phase-2 runs have no 'engine' key)."""
def start(process_key: str, inputs: dict | None = None) -> dict:
    """Compile-aware start: linear flows/processes -> process_engine.start_run;
    dag flows -> dag_engine.start_run. Returns {ok, run_id, kind, ...}. Never-raise."""
async def advance(run_id: str, max_steps: int = 16) -> dict:
    """Delegate to engine_for(run_id).advance(run_id, ...)."""
def replay(run_id: str) -> dict:        # delegate
def approve(run_id, approved_by="admin", note="", node_id="") -> dict:  # delegate (node_id ignored by linear)
def reject(run_id, by="admin", reason="", node_id="") -> dict:          # delegate
def list_runs(limit=20) -> list[dict]:  # union of both (shared index.jsonl + engine tag)
def journal(run_id, limit=100) -> list[dict]:  # shared reader
```
Implementation note: `engine_for` peeks `run_started`:
```python
def engine_for(run_id):
    from app.agents import process_engine, dag_engine
    for ev in process_engine._read_events(run_id):   # shared file reader
        if ev.get("type") == "run_started":
            return dag_engine if (ev.get("data") or {}).get("engine") == "dag" else process_engine
    return process_engine
```
`start()` resolves the process to learn its kind **before** writing `run_started`:
```python
def start(process_key, inputs=None):
    kind = "linear"
    if process_key.lower().startswith("flow:") and _flow_runner_on():
        from app.automation import flow_store, flow_compiler
        fl = flow_store.get_flow(process_key[5:])
        if fl:
            _proc, _errs, kind = flow_compiler.compile_flow(fl)  # 3-tuple in Phase 2 (§6.0)
    if kind == "dag":
        from app.agents import dag_engine
        return {**dag_engine.start_run(process_key, inputs), "kind": "dag"}
    from app.agents import process_engine
    return {**process_engine.start_run(process_key, inputs), "kind": "linear"}
```

### 4.2 DAG engine — `app/agents/dag_engine.py` (NEW) — the heart
Same JSONL journal dir/format as `process_engine` (`data/process_runs/<run_id>.jsonl`, via its own `_append_event`/`_read_events` copy — kept private, never-raise). State = **per-node**, derived purely by replay.

**Public surface (mirrors process_engine so the dispatcher is trivial):**
```python
def start_run(process_key: str, inputs: dict | None = None) -> dict:
    """Resolve flow -> compiled DAG (graph dict, §5.2). Journal 'run_started'
    with {process, inputs, engine:"dag", graph:<compiled-graph>}. Never-raise.
    The graph is EMBEDDED in run_started so the run is reproducible even if the
    flow is later edited/deleted (same immutability guarantee as linear)."""

def replay(run_id: str) -> dict:
    """Journal -> per-node state. Returns:
      {run_id, status, process, inputs, engine:"dag",
       nodes: {node_id: {"state": "pending|running|done|skipped|failed|waiting",
                          "result": {ok,count,detail} | None, "retries": int}},
       ready: [node_id,...],         # computed: deps satisfied, not yet started
       waiting: node_id | "",        # breakpoint currently blocking (if any)
       last_error, started_at, ended_at}
    Status rollup: any node 'waiting' -> waiting_approval; any 'failed' (terminal) -> failed;
    all terminal (done/skipped) -> completed; else running."""

async def advance(run_id: str, max_steps: int = 16) -> dict:
    """Compute ready-set from replay, execute up to max_steps ready TASK nodes
    (sequentially within a tick — see §7.1 parallelism note), evaluate outgoing
    edge conditions on each result, mark not-taken edges, propagate skips, and
    PAUSE at a breakpoint node. Crash-safe (state only from journal). Never-raise."""

def approve(run_id, approved_by="admin", note="", node_id="") -> dict:
    """Approve the breakpoint at node_id (or the single waiting node if blank)."""

def reject(run_id, by="admin", reason="", node_id="") -> dict:
    """Reject -> that node 'failed' -> run failed."""
```
Reuses `process_library.execute_step(step, inputs)` and `process_library.check_gate(step, result)` verbatim for task nodes (whitelist + deterministic gate preserved).

### 4.3 Edge-condition evaluator — `app/automation/edge_condition.py` (NEW)
Pure, deterministic, **no code/LLM**. One function:
```python
def edge_taken(when: dict | None, source_result: dict) -> bool:
    """Evaluate an edge's `when` against the SOURCE node's result dict.
    when == None / {}  -> True (unconditional edge).
    when shape (§5.3):  {"field": "count", "op": ">=", "value": 1}
                        {"all": [<cond>, ...]}  / {"any": [<cond>, ...]}  (nesting depth<=3)
    field is looked up in source_result (flat key; missing -> None).
    Supported ops: == != > >= < <= in not_in truthy falsy exists.
    Type-coercion: numeric compare if both castable to float, else string compare.
    Never raises -> on any malformed condition returns False (fail-closed: an edge
    you can't evaluate does NOT fire -> branch is skipped, never wrongly taken)."""
```
Fail-**closed** is deliberate: a broken condition must not accidentally trigger a side-effecting branch. (Contrast with the engines' FAIL-OPEN billing meters — here the safe default is "don't proceed".)

### 4.4 Compiler — `app/automation/flow_compiler.py` (EDIT, additive — signature widens to 3-tuple)
`compile_flow(flow) -> (process_or_graph | None, errors, kind)` where `kind ∈ {"linear","dag"}`. Back-compat: linear path returns the **same** `process_dict` as today plus `kind="linear"`; DAG path returns a **graph dict** (§5.2) plus `kind="dag"`. Decision rule + new validations in §6.

### 4.5 Engine resolver hook — `app/agents/process_library.py` (EDIT, additive)
`get_process(key)` already compiles `flow:` → it currently returns only the linear `process` dict. Phase 2: it must NOT be the DAG entry point (DAG graphs aren't `process` dicts). Change: when the compiled `kind=="dag"`, `get_process` returns the **graph dict** too (callers that only understand linear never see DAG flows because the dispatcher routes them to `dag_engine`, which calls the compiler directly). Concretely `get_process` stays the linear resolver; **`dag_engine.start_run` calls `flow_compiler.compile_flow` directly** and embeds the graph — so `process_library` needs only a 1-line tolerant change to ignore the 3rd tuple element:
```python
proc, _errs, _kind = flow_compiler.compile_flow(fl)
return proc if _kind == "linear" else None   # DAG flows resolved by dag_engine, not here
```

### 4.6 API — `app/api/growth_process.py` (EDIT, additive — route through dispatcher)
**No new routes.** Change the 4 lifecycle endpoints to call `flow_dispatch` instead of `process_engine` directly so they transparently serve both engines:
- `POST /process/start` → `flow_dispatch.start(body.process, body.inputs)` then `process_tick.delay(run_id)`.
- `GET /process/run/{run_id}` → `{"state": flow_dispatch.replay(run_id), "journal": flow_dispatch.journal(run_id)}`.
- `POST /process/run/{run_id}/approve` → `flow_dispatch.approve(run_id, approved_by=…, note=…, node_id=body.node_id)`.
- `POST /process/run/{run_id}/reject` → `flow_dispatch.reject(...)`.
- `GET /process/runs` → `flow_dispatch.list_runs(limit)`.
`ProcessApproveIn` gains an optional `node_id: str = ""` (linear ignores it). Flow-CRUD routes (`/flows`, `/flow`, `/flow/{id}`) unchanged; the GET preview now shows `kind` + per-node compile info.

### 4.7 Celery task — `app/tasks/staff_jobs.py` `process_tick` (EDIT, 1 line)
`res = _run_async(process_engine.advance(run_id))` → `res = _run_async(flow_dispatch.advance(run_id))`. Self-requeue condition (`status=="running"` or step-budget note) unchanged — `dag_engine.advance` returns the same shape, and emits the same `note` when it hits `max_steps` of ready nodes. `dag_engine.ensure_alive` mirrors process_engine's watchdog (revive stale RUNNING DAG runs).

### 4.8 Builder UI — `frontend/explorer.html` (EDIT)
- **Edge condition editor:** click an edge → small popover to set `when` (`field` dropdown from a fixed list `count|ok|detail`, `op` dropdown, `value` input). Unconditional = leave blank. Stored on the edge object: `{"f","t","when":{...}}`.
- **Merge node:** new palette item `kind:"merge"` (+ `join:"all"|"any"`, default `all`). Visual diamond.
- **Per-node live status:** poll `replay().nodes[id].state` → color map incl. **`skipped`** (greyed, dashed) — the new state vs Phase 1. Edges show taken (solid) / not-taken (faded).
- **Breakpoint-in-branch:** unchanged UX; the `waiting` node id comes from `replay().waiting`.
- Remove the builder-side "linear only" lint; rely on server compile preview (`runnable` + per-error list).

### 4.9 Flag — reuse `FLOW_RUNNER` (no new flag). Already in `AUTOMATION_FLAGS` (`app/api/growth.py`). DAG path gated by the same env var (`get_process`/`dag_engine.start_run`/CRUD all check it).

## 5. Data model

### 5.1 Flow JSON (builder export) — superset of Phase 1 (back-compat)
Phase-1 flows are valid Phase-2 flows (no `when`, no `merge` ⇒ compiles as `linear`). New optional fields:
```json
{
  "id": "flow_ab12cd34",
  "name": "Branch on lead count",
  "nodes": [
    {"id": "n1", "action": "scrape", "title": "Prospector", "args": {"batch": 3}},
    {"id": "n2", "action": "rescore", "title": "Re-score"},
    {"id": "n3", "action": "harvest", "title": "Harvest more"},
    {"id": "n4", "kind": "merge", "join": "all", "title": "Merge"},
    {"id": "n5", "kind": "breakpoint", "title": "Approve send", "question": "Drafts ready — send?"},
    {"id": "n6", "action": "cadence_run", "title": "Cadence"}
  ],
  "edges": [
    {"f": "n1", "t": "n2", "when": {"field": "count", "op": ">=", "value": 1}},
    {"f": "n1", "t": "n3", "when": {"field": "count", "op": "<",  "value": 1}},
    {"f": "n2", "t": "n4"},
    {"f": "n3", "t": "n4"},
    {"f": "n4", "t": "n5"},
    {"f": "n5", "t": "n6"}
  ],
  "created_by": "admin", "updated_at": "2026-06-20T..."
}
```
**Node kinds:** `task` (default, has `action` ∈ EXECUTORS) · `breakpoint` (has `question`) · `merge` (has `join`). **Edge:** `{f,t,when?}`.

### 5.2 Compiled DAG graph (what `compile_flow` emits when `kind=="dag"`, embedded in `run_started`)
```python
{
  "name": "Branch on lead count",
  "kind": "dag",
  "nodes": {                       # id -> node spec (executor args dropped; data-passing=Phase4)
    "n1": {"id":"n1","kind":"task","action":"scrape","gate":None,"max_retries":1},
    "n3": {"id":"n3","kind":"task","action":"harvest"},
    "n4": {"id":"n4","kind":"merge","join":"all"},
    "n5": {"id":"n5","kind":"breakpoint","question":"Drafts ready — send?"},
    ...
  },
  "edges": [ {"f":"n1","t":"n2","when":{"field":"count","op":">=","value":1}},
             {"f":"n1","t":"n3","when":{"field":"count","op":"<","value":1}}, ... ],
  "in":  {"n2":["n1"], "n3":["n1"], "n4":["n2","n3"], "n5":["n4"], "n6":["n5"]},  # adjacency (precomputed)
  "out": {"n1":["n2","n3"], "n2":["n4"], "n3":["n4"], "n4":["n5"], "n5":["n6"]},
  "roots": ["n1"]                  # indegree-0 nodes (>=1 allowed in DAG mode)
}
```

### 5.3 Edge condition language (SIMPLE + deterministic — §4.3)
- **Leaf:** `{"field": "<key>", "op": "<op>", "value": <scalar>}` evaluated against `source_result` (the dict the executor returned: keys `ok`, `count`, `detail`).
- **Combinators:** `{"all":[leaf,...]}` (AND), `{"any":[leaf,...]}` (OR) — nesting depth ≤ 3 (validated; deeper = compile error).
- **Ops:** `== != > >= < <= in not_in truthy falsy exists`.
- **NOT** allowed: function calls, attribute access, arithmetic, references to other nodes' results, LLM. (Those are Phase 4 / never.)
- Missing `field` → `None`; `truthy/falsy/exists` handle it; relational ops on `None` → `False` (fail-closed).

### 5.4 Journal events (DAG vocabulary — NEW, distinct from linear's)
Same JSONL record shape `{run_id,type,data,at}`, written to the **same file**. Event types:
| type | data | meaning |
|---|---|---|
| `run_started` | `{process, inputs, engine:"dag", graph:{...}}` | start; graph embedded (immutable replay) |
| `node_started` | `{node}` | task node began executing |
| `node_completed` | `{node, result:{ok,count,detail}, ms}` | task node finished + result (result needed to evaluate its out-edges on replay) |
| `node_gate_failed` | `{node, reason, retries}` | deterministic gate failed (bounded retry) |
| `node_skipped` | `{node, reason}` | branch not taken / merge-of-skipped / unreachable |
| `edge_taken` | `{f, t}` | out-edge condition true (recorded so replay reconstructs which branch ran) |
| `merge_ready` | `{node, join, satisfied:[...]}` | merge join satisfied |
| `breakpoint_waiting` | `{node, question}` | human gate hit; run pauses |
| `breakpoint_approved` | `{node, by, note}` | resume past breakpoint |
| `run_completed` | `{}` | all nodes terminal (done/skipped) |
| `run_failed` | `{error, node?}` | a node failed gate after retries / rejected |

### 5.5 Replay derivation (the algorithm — answers "how does state derive without a cursor")
`replay(run_id)` folds events into `nodes: {id: {state, result, retries}}`:
1. `run_started` → load `graph`; every node `state="pending"`, `result=None`.
2. `node_started` → `nodes[n].state="running"`.
3. `node_completed` → `state="done"`, store `result`. `node_gate_failed` → bump `retries` (stay `running`/`pending` per retry budget); exceed → engine emits `run_failed`.
4. `node_skipped` → `state="skipped"`.
5. `breakpoint_waiting` → that node `state="waiting"`; run status rolls up to `waiting_approval`. `breakpoint_approved` → node `state="done"` (breakpoints have no result; out-edges are unconditional or evaluate against `{}`).
6. `edge_taken` is **informational** for the UI; the authoritative "did this edge fire" is re-derivable but recording it makes replay O(n) and UI-truthful.
7. **`ready` set (computed, NOT stored):** a `pending` node `x` is *ready* iff its join condition over `in[x]` is met:
   - **`all` (default / task nodes):** every in-edge is *resolved* — source is `done` **and** edge `when` true (so the edge "fired"), **or** every in-edge is dead (source `skipped`, or source `done` but `when` false) ⇒ `x` itself is `skipped` (not ready).
   - **`any` (merge `join:"any"`):** ready as soon as ≥1 in-edge fired; remaining slower in-edges' eventual results are ignored.
   A node with ≥1 fired in-edge **and** all other in-edges already resolved (fired or dead) → ready. A node whose every in-edge is dead → emit `node_skipped`.
8. **Status rollup:** `waiting` node ⇒ `waiting_approval`; any terminal `run_failed` ⇒ `failed`; all nodes terminal ⇒ `completed`; else `running`.

This is the per-node analogue of linear's `step_index`: **the cursor is replaced by the ready-set, recomputed from the journal every tick** — same crash-safety, same single-source-of-truth property.

### 5.6 Data-passing seam (Phase 4 — NOT designed here)
`node_completed.result` is journaled per node, so Phase 4 can build an input-map (`{downstream_field: {from_node, source_key}}`) **without** a journal schema change — it already has every node's output recorded. Phase 2 executors still receive only the **run-level `inputs`** (identical to Phase 1). **Do not wire result→input here.**

## 6. Compiler + validation rules (`flow_compiler.compile_flow`, EDIT)

### 6.0 Decision rule (linear vs dag)
A flow compiles as **`linear`** (Phase-1 path, unchanged output) iff: no edge has a `when`, no node is `kind:"merge"`, and every node has indegree ≤ 1 **and** outdegree ≤ 1 with exactly one root. Otherwise → **`dag`** path. (So existing Phase-1 flows are bit-identical; only new shapes hit the new code.)

### 6.1 DAG validation rules (all must pass; deterministic; return `errors`)
1. **Non-empty:** ≥1 node.
2. **Unique ids; edge integrity:** every `f`/`t` references a real node (no dangling). *(reused from Phase 1)*
3. **Whitelist:** every `task` node `action` ∈ `process_library.EXECUTORS`. *(reused)*
4. **Acyclic:** Kahn's algorithm topological sort over `out`; if any node remains → `["cycle detected: <nodes>"]`. **Loops rejected** (Phase 2 = strict DAG).
5. **Reachability:** every node reachable from some root (indegree-0). Unreachable node → error (no orphan branches).
6. **Single terminal-or-explicit-merge for joins:** any node with indegree ≥ 2 **must** be `kind:"merge"` (forces the builder to declare join semantics — no accidental implicit joins). A `task`/`breakpoint` with 2 incoming edges → error: "use a merge node before 'n4'".
7. **Condition validity:** each edge `when` (if present) passes `edge_condition.validate(when)` — known op, scalar value, combinator depth ≤ 3, `field` is a non-empty string. Invalid → compile error (caught at save, not run).
8. **Branch determinism guard (soft, WARN not error):** if a node has ≥2 out-edges and they are not mutually-exclusive-looking (e.g. two unconditional out-edges), that's a **parallel fan-out** (allowed). If multiple conditional out-edges can be simultaneously true, **all true branches run in parallel** (documented semantics — n8n "IF" = at most one; n8n "Switch"/multi = many). We adopt **"every edge whose `when` is true fires"** — simplest deterministic rule, no priority ordering needed.
9. **Breakpoint nodes:** unchanged; may appear anywhere, including inside a branch.

### 6.2 Output
`(graph_dict (§5.2), [], "dag")` on success; `(None, errors, "dag")` on failure. Linear flows: `(process_dict, errors, "linear")` exactly as Phase 1.

## 7. Engine changes (`dag_engine.advance` — the scheduler)

### 7.1 One tick =
```
st = replay(run_id)
if status in (completed, failed): return "already ended"
if status == waiting_approval:   return "human approval pending"
ready = st["ready"]                      # computed in replay (§5.5)
if not ready and no running nodes:
    # nothing ready, nothing running, not waiting -> all remaining unreachable -> skip them, complete
    skip_unreachable(); emit run_completed; return completed
done = 0
for node_id in ready:                    # SEQUENTIAL within a tick (see note)
    if done >= max_steps: break
    node = graph["nodes"][node_id]
    if node.kind == "breakpoint":
        emit breakpoint_waiting(node); return waiting_approval     # PAUSE whole run
    if node.kind == "merge":
        emit node_completed(node, result={"ok":True,"count":1,"detail":"merged"})  # passthrough
    else:                                # task
        emit node_started
        result = await execute_step(node, inputs)  with wait_for(_STEP_TIMEOUT_S)
        ok, reason = check_gate(node, result)
        if not ok: emit node_gate_failed; (retry budget like linear) -> maybe run_failed; continue
        emit node_completed(node, result)
    # evaluate out-edges on this node's result, mark fired/dead:
    for e in graph["out"].get(node_id, []):
        if edge_condition.edge_taken(e.get("when"), result_of(node)):
            emit edge_taken(f=node_id, t=e.t)
        # (dead edges are implicit — not emitted; replay treats absent edge_taken as dead once source done)
    propagate_skips()                    # any node whose in-edges are all dead -> node_skipped
    done += 1
requeue if any node still pending/running (process_tick self-requeues on status==running)
```
**Parallelism note (§ important):** "parallel branches" are modeled as **ready-set concurrency across ticks**, executed **sequentially within a single tick** (one `await` at a time). True wall-clock parallelism (two executors at once) is NOT added in Phase 2 — it needs `asyncio.gather` with per-node timeouts and complicates crash-replay. The DAG still *expresses* parallel branches and runs both; they just interleave per-tick. This keeps the never-raise + crash-safe + free-stack invariants and is honest about cost (executors hit free LLM/HTTP — serial is safer for rate-limits anyway). **Documented as the Phase-2 semantic; gather-parallelism = future.**

### 7.2 Breakpoints inside branches
A breakpoint pauses the **entire run** (matches Phase-1 mental model + draft-safety). When approved, `breakpoint_approved` marks that node `done`; its out-edges evaluate against `{}` (unconditional edges only after a breakpoint — compiler rule 6.1.7 can forbid `when` on a breakpoint's out-edges, or treat missing field as fail-closed). Other branches that were ready continue on the next tick. (Phase 2 keeps it simple: **one breakpoint blocks all**; concurrent independent breakpoints are out of scope — compiler may warn if two breakpoints are in parallel branches.)

### 7.3 Failure semantics
A task node failing its gate after `max_retries` → `run_failed` (whole run, like linear). No partial-DAG "continue other branches on failure" in Phase 2 (that's error-routing, Phase 6). Deterministic and safe.

## 8. Safety & compliance (unchanged invariants from Phase 1)
- **Flag-gated** `FLOW_RUNNER=1` (default OFF → resolver returns nothing, DAG path dead, routes 503). Reused — **no new flag**.
- **Admin-only** (`require_admin` on every route — unchanged).
- **Whitelist executors only** — `dag_engine` calls the SAME `process_library.execute_step`; unknown action rejected at compile (rule 6.1.3). No arbitrary code/HTTP/LLM in conditions (§5.3).
- **Draft-safe** — all executors draft/gated; side-effecting branches gated behind explicit `breakpoint` nodes; TRAI/DLT/DND/WhatsApp gates remain server-side in the engines, untouched.
- **Fail-CLOSED conditions** — an unevaluable edge does NOT fire (§4.3) — a broken condition can never trigger a send.
- **Never-raise** everywhere (dispatch/dag_engine/edge_condition/compiler/API) — import-safe.
- **No new deps / container / DB** — reuses `./data` JSONL + existing Celery `process_tick`.
- **Linear back-compat** — `process_engine.py` byte-unchanged; the 3 prod processes run on the exact same path. Pre-Phase-2 runs (no `engine` key) default to linear in `engine_for`.

## 9. Testing plan
- `tests/test_edge_condition.py` — leaf ops (numeric vs string coercion), `all`/`any`, missing field → fail-closed, malformed `when` → False + `validate()` rejects, depth>3 rejected.
- `tests/test_flow_compiler_dag.py` — linear flow still → `kind="linear"` + identical steps (regression); branch flow → `kind="dag"` + correct `in`/`out`/`roots`; cycle rejected; indegree≥2 non-merge rejected; unreachable node rejected; dangling edge rejected; unknown action rejected.
- `tests/test_dag_engine.py` — (stub one EXECUTOR, no network): IF true-branch runs / false-branch `skipped`; parallel two-branch both `done` then merge `done`; merge `join:"any"` completes on first; breakpoint-in-branch pauses → approve → resumes; gate-fail → `run_failed`; **replay crash-safety**: re-run `replay` mid-flight reproduces identical node states.
- `tests/test_flow_dispatch.py` — `engine_for` picks dag vs linear from `run_started`; pre-Phase-2 run (no `engine` key) → linear; `start` routes by compiled `kind`.
- `tests/test_flow_runner_api.py` (EXTEND) — flag-off → 503; create branch flow → save → run → poll replay shows per-node states incl `skipped`; approve node-scoped breakpoint.
- Regression: existing `tests/test_flow_compiler.py` / `test_flow_store.py` / `test_flow_runner_api.py` stay green (linear unchanged). `scripts/explorer_sync.py --check` green (add `dag_engine.py·edge_condition.py·flow_dispatch.py` to the flow_runner node `files:`). `.venv\Scripts\python.exe scripts/prod_check.py` ALL PASSED.

## 10. File touch-list
**New:** `app/agents/dag_engine.py` · `app/agents/flow_dispatch.py` · `app/automation/edge_condition.py` · `tests/test_edge_condition.py` · `tests/test_flow_compiler_dag.py` · `tests/test_dag_engine.py` · `tests/test_flow_dispatch.py`
**Edit (additive):** `app/automation/flow_compiler.py` (3-tuple return + DAG path/validations) · `app/agents/process_library.py` (1-line: ignore 3rd tuple element, return `None` for dag in `get_process`) · `app/api/growth_process.py` (route 5 lifecycle endpoints through `flow_dispatch`; `ProcessApproveIn.node_id`) · `app/tasks/staff_jobs.py` (`process_tick`: `process_engine.advance` → `flow_dispatch.advance`; add dag `ensure_alive` to watchdog) · `frontend/explorer.html` (edge-condition popover + merge palette item + `skipped` state color + remove linear-only lint + node `files:` list) · `tests/test_flow_runner_api.py` (extend)
**No new:** route-mount (reuses `growth_process.py`), worker job (reuses `process_tick`), flag (`FLOW_RUNNER`), container, DB, dependency. **`process_engine.py` NOT edited.**

## 11. Open questions
1. **Parallel within a tick vs across ticks:** spec chooses across-ticks (serial-per-tick) for crash-safety + rate-limit safety (§7.1). Confirm acceptable vs adding `asyncio.gather` now. (Recommendation: defer gather — serial is safe + simpler; revisit only if a flow needs genuine wall-clock parallelism.)
2. **Multiple simultaneous breakpoints** in parallel branches: Phase 2 blocks the whole run at the first encountered. Acceptable, or do we need a "waiting set" + approve-each? (Recommendation: one-blocks-all for Phase 2; compiler WARN on parallel breakpoints.)
3. **`merge join:"any"` and the losing branch:** when `any` fires on branch A, branch B may still be running. Do we cancel B (skip its remaining nodes) or let it finish into a no-op? (Recommendation: let B finish — simpler, no cancellation; its eventual completion is ignored by the already-satisfied merge. Document it.)
4. **Breakpoint out-edge conditions:** forbid `when` on edges leaving a breakpoint (breakpoint has no result dict) — compiler error, or silently treat as unconditional? (Recommendation: compiler error — clearer.)
5. **Should `edge_taken` events be emitted, or fully re-derived on replay?** Spec emits them (O(n) replay, UI-truthful). Confirm the small journal-size cost is fine (it is — runs are short).
