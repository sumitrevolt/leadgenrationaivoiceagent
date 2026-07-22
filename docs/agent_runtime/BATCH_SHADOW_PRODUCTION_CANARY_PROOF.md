# Batch Harness — Production Shadow Canary Proof

**Date:** 2026-07-22 · **Family:** `batch_harness` · **Mode:** SHADOW (record-only) · **Verdict:** PASS

**Result:** one bounded production batch item was observed by the canonical harness in record-only
shadow; all 39 tripwires passed; the registry-bound executor was never invoked; every temporary
harness flag was restored OFF.

> Evidence document. Every claim is backed by the production audit record, a runtime read, or the
> exact code boundary exercised. No enforcement was enabled. No `.env`/compose/container change was
> made and no container was recreated. This is the second production-shadow-proven family, after
> `dag_engine` (see `DAG_SHADOW_PRODUCTION_CANARY_PROOF.md`).

## 1. Environment

| field | value |
|---|---|
| production SHA | `878c13973ce496c05979571e136c0138e95e4256` |
| registry manifest | `1d3b83331cf303e2` (deterministic; ADR-138) |
| `CODE_EXEC` | `0` (OFF) · `code_exec.enabled()=False` |
| `AGENT_RUNTIME` / `OPENCLAW_ENABLED` | `0` / `0` |
| canonical harness | OFF before and after (`AGENT_HARNESS*` empty) |

## 2. Owner authorization & scope

Exact owner-approved scope: `family=batch_harness` · `tool=batch.internal.safe_calculation@1.0.0` ·
`agent=nikhil` (registry-approved agent for this tool — `manager` would be `AGENT_NOT_ALLOWED`) ·
`tenant=__system__` · `items=1` · `attempts=1` · `concurrency=1` · `input={"id":"canary-batch-1"}` ·
`mode=SHADOW`, enforcement prohibited. Only `batch_harness.run_batch(...)` was invoked; the caller
`fn` implemented solely the deterministic, side-effect-free calculation over that one ID. No Nikhil
revenue-operations action or other staff/business capability was invoked.

## 3. Temporary flag mechanism (minimum, self-restoring)

Flags were set **only inside one ephemeral canary process's `os.environ`**: `AGENT_HARNESS=1`,
`AGENT_HARNESS_SHADOW=1`, `AGENT_HARNESS_CANARY_LOOPS=batch_harness`,
`AGENT_HARNESS_CANARY_AGENTS=nikhil`. No running service, `.env`, compose, GitHub var, or container
was modified. Shadow eligibility was `False → True → False`; a `try/finally` popped every harness
variable regardless of success, error, timeout, or interruption.

## 4. Real execution boundary

`batch_harness.run_batch(...)` → shadow branch `res = await fn(item)` (legacy `fn`, authoritative,
runs once) → `harness/adapters/batch_shadow.observe_batch_item(...)` → `Harness.observe()`
(record-only, after the semaphore releases). The registry-bound executor
(`enforce._safe_calculation_executor`) is reached **only** via `enforce_batch_item` in ENFORCE mode
and was never touched. The shadow path also registers a `_tripwire` executor that raises if invoked.

## 5. Input & deterministic result

`input={"id":"canary-batch-1"}`. The legacy `fn` reproduced the canonical digest
(`digest = Σ (digest*31 + ord(ch)) & 0xFFFFFFFF`; `value = digest % 1000`):
**`value = 321`**, `summary = "calc(canary-batch-1)=321"`.

## 6. Independent execution accounting (two distinct counters)

| counter | symbol | value |
|---|---|---|
| legacy executor calls | wrapped caller `fn` | **1** |
| registry-bound harness executor calls | `enforce._SAFE_CALLS["n"]` delta | **0** |

Output equality alone was not relied upon: the legacy counter and the native production counter
`enforce._SAFE_CALLS` are distinct symbols. Live-process `_SAFE_CALLS` also read `0` post-run.

## 7. Shadow-record evidence

One new line appended to `/app/data/harness_runs.jsonl`.

| field | value |
|---|---|
| `kind` | `shadow` |
| `source_loop` | `batch_harness` |
| `agent` | `nikhil` |
| `tenant_id` | `__system__` |
| `resolved_tool_name` | `batch.internal.safe_calculation` |
| `resolved_tool_version` | `1.0.0` |
| `mode` | `shadow` |
| `execution_comparison` | `MATCH` |
| `registry_comparison` | `REGISTRY_MATCH` |
| `registry_risk_class` | `GREEN` |
| `authority` | `INTERNAL_AUTONOMOUS` |
| `enforcement` | `false` |
| `side_effect_class` | `internal` |
| `checkpoint_state` | `completed` |
| `resumed` / `retry_scheduled` | `false` / `false` |
| `actual_executor` | `legacy_fn` |
| `tool_registry_status` | `canonical_registered` |
| `legacy_result_summary` | `…"value": 321 … "summary": "calc(canary-batch-1)=321"…` |

## 8. Tripwire results — 39 / 39 PASS

legacy executions = 1 · harness executor executions = 0 · items = 1 · successful = 1 · skipped = 0 ·
batch ok = true · new records = 1 · new row is batch shadow · batch shadow total = 1 · dag shadow
total = 1 · audit total = 2 · DAG record unchanged · enforcement records = 0 · no dedup/error rows ·
duplicates = 0 · result id = canary-batch-1 · result value = 321 · summary = calc(canary-batch-1)=321 ·
execution MATCH · registry REGISTRY_MATCH · manifest stable `1d3b83331cf303e2` · mode shadow ·
enforcement false · enforcement_applied false · canonical tool + version · agent nikhil · tenant
`__system__` · risk GREEN · authority INTERNAL_AUTONOMOUS · side-effect internal · retry false ·
checkpoint completed · pre-checksum ok · eligibility False→True→False · flags restored OFF.

## 9. External-effect proof

`side_effect_class=internal`; the `fn` is pure compute — no network, no LLM/provider call, no
customer or tenant data, no DB mutation, no WhatsApp/email, no publishing, no billing, no calling,
no code execution. The batch checkpoint was isolated to a throwaway temp directory; `NO_BATCH_RUNS_DIR`
post-run confirms zero production `data/batch_runs/` artifact was created.

## 10. Audit baseline & checksums

| point | records | checksum |
|---|---|---|
| pre-run | 1 (dag=1, batch=0, enforce=0) | `06e4c34f1eb8590d856e8e7838b9fdea3269662fcab2e0586faeddcbc9e69c85` |
| post-run | 2 (dag=1, batch=1, enforce=0) | `660fdb599092bed637773887a096d758509c41f86ad09d88e3a15e6bf4f5999e` |

The original DAG shadow record remained **byte-identical** across the run
(record SHA-256 `85f2b52de060de5355faa0f74dbc3c9d8971f77e60c6143250438972b12c9f0b`, pre and post).

## 11. Flag-restoration & health/queue/container comparison

| metric | pre | post |
|---|---|---|
| `AGENT_HARNESS*` across 5 containers | empty | empty |
| `CODE_EXEC` / `AGENT_RUNTIME` | 0 / 0 | 0 / 0 |
| `/health` · `/health/ready` | healthy | 200 · 200 |
| containers healthy | 5/5 | 5/5 |
| restarts / OOM | 0 / none | 0 / none |
| celery / dlq:dead | 0 / 7 | 0 / 7 |
| production SHA | `878c1397` | `878c1397` |
| `_SAFE_CALLS` (live) | 0 | 0 |

## 12. Rollback path

None required — record-only shadow, no enforcement, no deployment. Standing rollback for the family:
with `AGENT_HARNESS*` empty, `observe_batch_item → None` and the legacy batch path is authoritative.
The post-canary audit baseline is **2** records; future reviews compare against it.

## 13. Remaining limitations

- Audit backend is single-process append-only JSONL (no rotation; not multi-worker-safe) — a durable
  multi-worker backend is being prepared in a separate isolated runtime PR (inert by default).
- Two production shadow samples exist (dag, batch) — this proves the **bounded** shadow path per
  family, not platform-wide production readiness.
- No production enforcement persistence; enforcement remains OFF and unproven in production.
- Production-shadow-proven families: **2 / 5**. The remaining three (`staff.run_member`,
  `coordinator`, `supervisor/staff_supervisor`) remain shadow/registry-proven locally only.

## 14. Authorization boundary

This proof grants **no** standing authorization. It does not authorize enforcement, agent
activation, a third canary, commit-beyond-docs, deployment, or scope expansion.

---

*Raw run output (`BATCH_CANARY` JSON) and the operator harness are retained operator-side and are
intentionally not committed (no credentials, host details, or environment files belong in the repo).*
