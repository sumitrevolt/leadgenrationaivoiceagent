# Flow Runner — Phase 4: Data-Passing (node output → downstream input) — Design Spec

> **Status:** Approved 2026-06-21. Phases 1 (linear) LIVE; 2 (DAG) + 3 (triggers) + 5 (palette) BUILT on branch `flow-runner-phase2-5-specs`.
> **Decision:** Data-passing is a **dag_engine capability**. Any flow that declares an `inputs_map` compiles as a DAG (like `when`/`merge` already do) and `dag_engine` resolves each node's effective inputs from journaled upstream results before execution. **`process_engine.py` stays byte-unchanged.**
> **Scope discipline:** static `{from, key}` map + literal `{value}` only. NO expressions/templating/transforms/nested-paths/cross-run. Deterministic + fail-closed (edge_condition philosophy).

---

## 1. Why
Today every executor receives only the run-level `inputs` dict (Phase 1 invariant). A flow cannot wire one node's output into another's input — e.g. `scrape` → `crm_queue.leads`, or `brand_pulse` → `seo_blog_draft.topic`. The Phase-5 executors (`http_request`, `crm_queue`, `whatsapp_draft`, `client_report_draft`) read their targets from `inputs` and are the natural first consumers. Phase 2 already journals every `node_completed.result`, so the data is present — Phase 4 just lets a node *read* it (the seam noted in the Phase-2 spec §5.6).

## 2. Goal / Non-goals
**Goal:** A task node carries an optional `inputs_map`; when present, the flow runs on `dag_engine`, which merges the resolved upstream values (+ literals) over the run-level inputs before calling the executor. Deterministic, fail-closed, ancestor-validated at compile.

**Non-goals (defer):** expressions/templating/format-transforms; reading run metadata; nested key paths (result is flat `{ok,count,detail}`); cross-run data; per-node data-passing on the linear `process_engine` (those flows compile as DAG instead). No new flag (reuse `FLOW_RUNNER`), no new module, no journal schema change.

## 3. Architecture (Option A — chosen)
```
flow with any node.inputs_map  --compile-->  kind="dag" (forced, like when/merge)
                                              graph.nodes[id].inputs_map embedded
dag_engine.advance(task node):
   eff = _resolve_inputs(node, run_inputs, replay.nodes)      # {**run_inputs, **resolved}
   execute_step(node, eff)                                    # executor reads merged inputs
```
Rejected alternatives: (B) shared execute_step wrapper — execute_step lacks the journal, so the engine must pre-resolve; for linear that means editing `process_engine` → breaks byte-unchanged. (C) runtime context object — over-engineered. Option A is consistent with Phase 2's "new shape → DAG" rule and touches zero prod-proven linear code.

## 4. Data model
A **task** node gains an optional `inputs_map`:
```json
{
  "id": "n2", "action": "crm_queue",
  "inputs_map": {
    "leads":     {"from": "n1", "key": "detail"},   // upstream node n1's result.detail
    "client_id": {"value": "acme-co"}               // static per-node literal
  }
}
```
- **Source entry** `{"from": <node_id>, "key": <ok|count|detail>}` — pulls `nodes[from].result[key]`.
- **Literal entry** `{"value": <scalar|list|dict>}` — sets a static per-node param (also covers the Phase-5-deferred param editor).
- Compiled graph node spec embeds `inputs_map` verbatim (task nodes only).

## 5. Resolution (dag_engine, runtime)
```python
def _resolve_inputs(node, run_inputs, nodes) -> dict:
    eff = dict(run_inputs or {})
    imap = node.get("inputs_map") or {}
    for tgt, spec in imap.items():
        if not isinstance(spec, dict): continue
        if "value" in spec:
            eff[tgt] = spec["value"]; continue
        src = nodes.get(spec.get("from")) or {}
        res = src.get("result")
        if src.get("state") == "done" and isinstance(res, dict) and spec.get("key") in res:
            eff[tgt] = res[spec["key"]]
        # else: FAIL-CLOSED — omit the key (never inject garbage/None silently)
    return eff
```
Because the compiler guarantees `from` is an **ancestor**, the source node is always `done` by the time this node runs (it's only ready once its in-edges fired). Never raises. No journal change — results come from `replay`.

## 6. Compiler (`flow_compiler.py`, additive)
1. **Decision rule:** `has_inputs_map = any(non-empty node.inputs_map)` → add `not has_inputs_map` to the `is_linear` predicate (so inputs_map flows take the DAG path).
2. **Validation (DAG path):** for each task node's `inputs_map` entry:
   - literal `{"value": ...}` → always valid.
   - source `{"from","key"}` → `from` must be a real node **and a topological ancestor** of this node (reachable backwards via `in`-edges); `key` ∈ `{ok, count, detail}`. Else compile error (`"node 'X' input 'k': 'from' Y is not an ancestor"` / `"... unknown key"`).
3. **Embed:** task node spec carries `inputs_map` (only if non-empty).

## 7. Executors / Engine
- Executors **unchanged** — they already read from `inputs`. Phase-5 consumers benefit immediately.
- `dag_engine.advance` task branch: build `eff` via `_resolve_inputs(node, inputs, nodes)` and pass to `execute_step`. Merge node / breakpoint unaffected. `node_started` event may record the resolved keys (audit, optional) — default no change.

## 8. Builder UI (`explorer.html`, additive)
Selected-node "Inputs" editor (task nodes): rows of `target-key` + mode (From node / Literal); From → `from` dropdown (other nodes) + `key` dropdown (ok/count/detail); Literal → value input. Stored as `node.inputs_map`; included in `_frPayload`. No new palette item, no node-files change (no new module).

## 9. Safety
Deterministic (no code/expr/LLM); fail-closed (missing/not-done source → key omitted); ancestor-only (compile-checked → no forward/cyclic reads); `process_engine.py` untouched; never-raise; additive; reuse `FLOW_RUNNER` (inert until a flow declares `inputs_map`); whitelist executors unchanged.

## 10. Testing
- `tests/test_flow_compiler_phase4.py` — inputs_map → kind dag; literal valid; valid ancestor source compiles + embeds; forward/non-ancestor `from` → error; unknown `key` → error; linear flow w/ inputs_map (single chain) compiles as dag.
- `tests/test_dag_data_passing.py` — `_resolve_inputs` unit (source pull, literal, missing-source fail-closed, not-done fail-closed); e2e: n1(stub returns count/detail) → n2 reads n1.detail into inputs (stub executor asserts it received the upstream value).
- Regression: all existing flow tests green; `prod_check` + `explorer_sync --check` green.

## 11. File touch-list
**New:** `tests/test_flow_compiler_phase4.py` · `tests/test_dag_data_passing.py`.
**Edit (additive):** `app/automation/flow_compiler.py` (decision-rule + validation + embed) · `app/agents/dag_engine.py` (`_resolve_inputs` + wire into advance) · `frontend/explorer.html` (per-node Inputs editor + `_frPayload`). **No new module/flag/route/worker-job. `process_engine.py` NOT edited.**
