# DAG Engine — Production Shadow Canary Proof

**Date:** 2026-07-22 · **Family:** `dag_engine` · **Mode:** SHADOW (record-only) · **Verdict:** PASS

**Result:** one bounded production DAG node was observed by the canonical harness in
record-only shadow; all tripwires passed; every temporary harness flag was restored OFF.

> Evidence document. Every claim is backed by a production audit record, a runtime read, or the
> exact code boundary exercised. No enforcement was enabled. No second canary was run. Nothing was
> committed, deployed, or recreated to obtain this proof. The `.env` was untouched.

## 1. Environment

| field | value |
|---|---|
| production SHA | `878c13973ce496c05979571e136c0138e95e4256` |
| deployment SHA (image tag / `APP_VERSION`) | `878c1397…` (`ghcr.io/…:878c13973ce496c05979571e136c0138e95e4256`) |
| registry manifest | `1d3b83331cf303e2` (deterministic across seed/process/container — ADR-138) |
| `CODE_EXEC` | `0` (OFF) |
| `AGENT_RUNTIME` | `0` |
| canonical harness | OFF before and after (`AGENT_HARNESS*` empty) |

## 2. Approved scope (single node)

`family=dag_engine` · `tool=workflow.dag.internal_calculation@1.0.0` · `agent=manager` ·
`tenant=__system__` · `nodes=1` · `attempts=1` · `concurrency=1` · `input={"n": 7}` ·
`mode=SHADOW` · enforcement prohibited.

## 3. Temporary flag mechanism (minimum, self-restoring)

The four canary flags were set **only inside a single ephemeral process's own memory**:
`AGENT_HARNESS=1`, `AGENT_HARNESS_SHADOW=1`, `AGENT_HARNESS_CANARY_LOOPS=dag_engine`,
`AGENT_HARNESS_CANARY_AGENTS=manager`, plus the enforce flags held explicitly OFF/empty. No running
service was modified, no `.env` was changed, no container was recreated. Shadow eligibility was
observed `False → True → False` across a `try/finally` that pops every harness flag regardless of
success, error, timeout, or interruption. Because the flags live only in the ephemeral process,
they vanish on exit even if the process is killed mid-run.

## 4. Real execution boundary

`dag_engine.advance(run_id)` → `process_library.execute_step(node, inputs)` →
`process_library.EXECUTORS["internal_calculation"]` (`_exec_internal_calculation`; triangular
number `n·(n+1)//2`). The harness observed the completed node via
`harness/adapters/dag_shadow.observe_dag_action()` → `Harness.observe()` (record-only). That path
registers a tripwire executor which raises if ever invoked — proving the harness never executes.

## 5. Input & deterministic result

`n = 7` → `sum = 7·8/2 = 28`. Legacy result:
`{"ok": true, "count": 1, "detail": "internal_calculation n=7 sum=28", "value": 28}`.

## 6. Execution accounting

| counter | value |
|---|---|
| legacy DAG executions | **1** |
| harness executor executions | **0** |
| duplicate executions | **0** |
| new shadow records | **1** |

## 7. Shadow-record evidence

Persisted as a single line at `/app/data/harness_runs.jsonl`.
File SHA-256: `06e4c34f1eb8590d856e8e7838b9fdea3269662fcab2e0586faeddcbc9e69c85` · size 2415 bytes ·
mtime `2026-07-22T12:22:07Z`.

| field | value |
|---|---|
| `kind` | `shadow` |
| `source_loop` | `dag_engine` |
| `agent` | `manager` |
| `tenant_id` | `__system__` |
| `resolved_tool_name` / `canonical_tool` | `workflow.dag.internal_calculation` |
| `resolved_tool_version` | `1.0.0` |
| `mode` | `shadow` |
| `execution_comparison` | `MATCH` |
| `registry_comparison` | `REGISTRY_MATCH` |
| `enforcement` / `enforcement_applied` | `false` / `false` |
| `retry_scheduled` | `false` |
| `dag_node_status` | `completed` |
| `predicted_lane` / `registry_risk_class` | `GREEN` |
| `authority` | `INTERNAL_AUTONOMOUS` |
| `legacy_status` | `ok` |
| `legacy_result_summary` | `…"detail": "internal_calculation n=7 sum=28", "value": 28…` |

## 8. Tripwire results — 20 / 20 PASS

legacy DAG executions = 1 · harness executor executions = 0 · shadow records = 1 · duplicates = 0 ·
result `sum = 28` · execution comparison = MATCH · registry comparison = REGISTRY_MATCH · manifest =
`1d3b83331cf303e2` (pre and post) · mode = shadow · `enforcement_applied = false` · `enforcement =
false` · tenant = `__system__` · agent = `manager` · tool = `workflow.dag.internal_calculation`
(resolved + canonical) · version = `1.0.0` · `side_effect_class = internal` · external effects = 0 ·
advance status = completed · all harness flags restored OFF · shadow eligibility False after restore.

## 9. External-effect proof

`side_effect_class = internal`; the executor is pure compute — no I/O, no network, no DB or customer
mutation, no WhatsApp/email/outbound, no publishing, no billing, no calling, no code execution. Zero
external effects. The DAG scratch journal was isolated to a throwaway temp directory; **0** canary
runs leaked into the production `data/process_runs` journal.

## 10. Flag-restoration proof

After the run, all five live containers (`leadgen_app` + `leadgen_worker`, `leadgen_worker_heavy`,
`leadgen_worker_video`, `leadgen_scheduler`) reported every `AGENT_HARNESS*` variable empty,
`CODE_EXEC=0`, and `AGENT_RUNTIME=0`. Shadow eligibility evaluated `False` after restoration.

## 11. Health / queue comparison (pre vs post)

| metric | pre-run | post-run |
|---|---|---|
| containers healthy | 5/5 | 5/5 |
| restarts / OOM | 0 / none | 0 / none |
| celery queue depth | 0 | 0 |
| `dlq:dead` | 7 | 7 (unchanged; historical) |
| disk free | ~54% | ~54% |
| production SHA | `878c1397` | `878c1397` |
| harness audit records | 0 | 1 |

## 12. Rollback path

None required — the run was record-only shadow with no enforcement and no deployment. The single
audit record is the only state produced. Standing rollback for the family: with `AGENT_HARNESS*`
empty, `observe_dag_action → None` and the legacy DAG path is authoritative. The new post-canary
audit baseline is **1** record (not 0); future reviews compare against this baseline.

## 13. Remaining limitations

- The audit backend is single-process append-only JSONL (no rotation; not multi-worker-safe).
- Exactly one production shadow sample exists — this proves the **bounded** path, not platform-wide
  production readiness.
- No production enforcement persistence exists; enforcement remains OFF and unproven in production.
- Only **1 / 5** harness families is production-shadow-proven (`dag_engine`). The other four remain
  shadow/registry-proven locally only.

## 14. Authorization boundary

This proof grants **no** standing authorization. It does not authorize enforcement, agent
activation, a second canary, commit-beyond-docs, deployment, or scope expansion. Any further canary
requires separate explicit owner approval.

---

*Raw run output (`CANARY_RESULT` JSON) and the operator harness are retained operator-side and are
intentionally not committed (no credentials, host details, or environment files belong in the repo).*
