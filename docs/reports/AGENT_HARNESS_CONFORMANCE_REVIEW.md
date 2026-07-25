# Agent Harness — Five-Family Conformance & Production-Readiness Review

**Date:** 2026-07-22 · **Branch:** main · **HEAD:** 7ce4d97 (nothing committed) ·
**Verdict:** PARTIAL — five-family conformance validated; global enforcement NOT ready.
All enforcement flags OFF. Nothing committed/pushed/deployed. `.env` untouched.

> This is a runtime-evidence review. Documentation does not equal runtime proof; every
> claim below is backed by a source symbol, a test result, or a real local execution.

## 1. Authoritative architecture

```
Admin -> OpenClaw Copilot -> Kavach (openclaw_harness, non-dispatchable control agent)
  -> Owner OS (SOLE mutation authority) -> Boss / existing dispatchers (staff.run_member,
    dag_engine, coordinator, supervisor/staff_supervisor, batch_harness)
  -> structured action contracts (ToolCall/ActionRequest, CoordinatorActionV1,
    SupervisorDecisionV1) -> CanonicalToolRegistry (sole risk/authority source)
  -> record-only Harness.observe  (SHADOW)   [4 families]
     OR registry-bound executor  (ENFORCE)   [batch only, flag-gated, currently OFF]
  -> audit (JSONL) / harness.explain / stop+budget+kill (StopController)
```

**Enforcement exists ONLY for `batch_harness`** (`enforce.py`, executor binding
`batch.internal.safe_calculation@1.0.0`), and is **OFF** (`AGENT_HARNESS_ENFORCE` unset;
`resolved_batch_mode=off`). Every other family is **record-only shadow**; no executor binding.

## 2. staff_supervisor closure — PROVEN

| field | value |
|---|---|
| dependency | langgraph, langgraph_supervisor, langchain_openai 1.3.3, langchain_core 1.4.8 — all installed |
| feature flag | `USE_LANGGRAPH_SUPERVISOR` (default OFF) + provider key gate |
| real graph constructed | true (`create_supervisor(...).compile()`, `StaffSupervisor.active`) |
| real graph invoked | true (`.run()`, 7 turns, ok=true, 2 samples) |
| model | deterministic local fake (`BaseChatModel`, handoff tool-call to dev) — no network/provider call; real graph preserved |
| selected-agent provenance | MESSAGE_NAME (routed worker message `name` in STAFF, not final supervisor msg) |
| selected target | `dev` (valid STAFF); Kavach not in STAFF so never selectable |
| harness executions | 0 |
| registry comparison | REGISTRY_MATCH (agent.delegate.dev, GREEN) |
| duplicate executions | 0 (per-run graph_run_id — cross-run dedup collision fixed) |
| external effects | 0 · enforcement_applied false |
| test | `tests/test_harness_supervisor_registry.py::test_staff_supervisor_real_graph_registry_match` |

**Verdict: PROVEN** with a fixture model preserving the real graph (honestly labeled — not a
real-provider proof). Two bounded fixes shipped: (a) selection extraction now finds the routed
STAFF-named message, not the final supervisor message; (b) per-run `graph_run_id` removes a
cross-run audit-dedup collision.

## 3. Canonical tool matrix (manifest 1d3b83331cf303e2 — deterministic)

> Manifest fingerprint is now deterministic across PYTHONHASHSEED / process / container (ADR-138). The earlier values `a20e2ede196c30ae` and `697b56f06ed35102` were historical **non-deterministic** fingerprints and are not authoritative.

| identity | ver | family | risk | side-effect | authority | agents | tenant | approval | idem | sandbox | net | bound |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| batch.internal.safe_calculation | 1.0.0 | batch | GREEN | READ_ONLY | INTERNAL_AUTONOMOUS | nikhil | __system__ | no | no | no | deny | yes |
| workflow.dag.internal_calculation | 1.0.0 | dag | GREEN | NONE | INTERNAL_AUTONOMOUS | manager,nikhil | __system__ | no | no | no | deny | no |
| agent.nikhil.revenue_operations | 1.0.0 | staff | AMBER | EXTERNAL_SEND | APPROVAL_REQUIRED | nikhil | __system__ | yes | yes | no | restricted | no |
| agent.delegate.dev | 1.0.0 | coordinator+supervisor | GREEN | READ_ONLY | INTERNAL_AUTONOMOUS | dev | __system__ | no | no | no | restricted | no |
| agent.delegate.rohan | 1.0.0 | supervisor | AMBER | EXTERNAL_SEND | APPROVAL_REQUIRED | rohan | __system__ | yes | yes | no | restricted | no |

Only `batch.internal.safe_calculation` has an executor binding (the sole enforcement candidate).
`agent.delegate.dev` is shared by coordinator + supervisor (one policy, two orchestrators).

## 4. Registry policy-wins (real evaluations)

rohan/nikhil AMBER -> would_require_approval=true, would_allow=false · claimed-GREEN vs
registry-AMBER -> risk_class_mismatch=true, registry wins (AMBER) · peer -> AGENT_NOT_ALLOWED ·
wrong tenant -> TENANT_NOT_ALLOWED · unknown -> UNREGISTERED_TOOL · wrong version -> VERSION_MISMATCH.
Adapter/model claims never override the registry.

## 5. Safety and authority (verified this session)

STAFF count 31 (build_registry()==CANONICAL_COUNT) · Kavach in STAFF: false · calling HARD OFF ·
platform_dial HARD OFF · CODE_EXEC=0 · SANDBOX_REQUIRED tools deny (no sandbox backend) · Owner OS
sole mutation authority (OWNER_OS_REQUIRED/APPROVAL/ALWAYS_REFUSED never directly execute) · Kavach
never a delegation target · actor != target; tenant not model-forgeable · __system__ only for genuine
internal ops. Kavach commands: 16 GREEN read-only, 12 AMBER (parked through Owner OS);
harness.enforce.*/harness.kill are AMBER.

## 6. Conformance levels (C0-C5, evidence-derived)

| family | level | rationale |
|---|---|---|
| batch_harness | C4 (local/internal) | owner-approved bounded canary done + rolled back; fail-closed; exactly-once; NOT C5 (no prod persistence/multi-worker/monitoring) |
| dag_engine | C2 → **production-shadow-proven** | REGISTRY_MATCH real proof; GREEN; no binding. One bounded production shadow canary passed 2026-07-22 (see `docs/agent_runtime/DAG_SHADOW_PRODUCTION_CANARY_PROOF.md`): legacy=1, harness executor=0, 1 shadow record, MATCH/REGISTRY_MATCH, manifest `1d3b83331cf303e2`, flags restored OFF |
| staff.run_member/Nikhil | C2 (AMBER) | REGISTRY_MATCH real proof; AMBER external-send/approval — never autonomous |
| coordinator | C2 (Dev delegation) | agent.delegate.dev REGISTRY_MATCH on real graph; orchestrator < C3; structured planner shadow/mocked |
| supervisor.py | C2 | dev GREEN + rohan AMBER REGISTRY_MATCH on real LangGraph |
| staff_supervisor | C2 | real graph proven (fixture model); MESSAGE_NAME -> dev REGISTRY_MATCH |

No family is C5. Only batch reached C4 (local). Coverage: shadow 5/5, structured-contract 5/5,
registry-backed 5/5 (all five families now have >=1 REGISTRY_MATCH real proof), enforcement-prepared
1 (batch), canary-proven 1 (batch local), **production-shadow-proven 2 (dag_engine, batch_harness — 2026-07-22)**,
production-enforced 0.

## 7. Rollback (flags OFF)

With every enforcement/canary flag OFF, all five family adapters record nothing (observe_* -> None),
resolve_mode(batch)=off, legacy path authoritative — verified this session for
staff/dag/coordinator/supervisor + batch mode resolution.

## 8. Tests (bounded groups, current tree)

Harness-focused (13 files) 384 passed, 0 fail/err/skip. Regressions + STAFF/Owner-OS routing safety
(owner_agent_execution, workflow_fixes_2026, workflow_guards, phase2_upgrades, agent_registry,
agent_os_routing, owner_os) 86 passed, 0 fail. staff_supervisor real-graph test included.

## 9. Change-set quality

Additive only; all defaults inert (enforcement OFF, structured-plan flags OFF, no executor binding
except batch). Known bounded risks: audit is append-only JSONL (single-process; no rotation/multi-worker
— documented, not production persistence); shadow dedup + enforce exactly-once are in-memory
(process-local — documented, NOT multi-worker-safe); real sandbox backend absent (SANDBOX_REQUIRED
denies). Test-only hooks (`_enforce_gate`, tripwire registries) are underscore-prefixed and unreachable
from production APIs (enforce mode is OFF + owner-gated). No secret leakage (redaction + bounded
payloads). No import cycles.

## 10. PR / production readiness

- Local implementation: coherent + testable (470 tests green across harness+regression).
- PR readiness: ready to prepare an isolated reviewable commit/PR (additive, self-contained under
  `app/agents/harness/` + adapters + 5 registry defs + tests + docs).
- CI readiness: not yet run in CI (local only).
- Deployment readiness: NOT deployed; not a goal this session.
- Production enforcement readiness: NOT READY — needs persistent audit backend, multi-worker-safe
  dedup/idempotency, monitoring/alerting, prod sandbox (for CODE_EXEC), per-tool prod allowlist,
  owner-approved prod canary, deployed-SHA + post-deploy health proof.

## 11. Overall verdict

NOT READY FOR GLOBAL ENFORCEMENT. Five families are shadow-covered, structured-contract-covered,
and registry-backed with real REGISTRY_MATCH proofs; exactly one family (batch) is enforcement-prepared
and has completed one owner-approved local canary (rolled back). The previous canary grants no standing
authorization. Next: prepare the accumulated harness implementation for a reviewable isolated commit/PR.

## 12. Production-shadow proof addendum (2026-07-22)

One bounded production shadow canary was run for `dag_engine` (record-only; no enforcement; every
temporary flag restored OFF). Full evidence: `docs/agent_runtime/DAG_SHADOW_PRODUCTION_CANARY_PROOF.md`.

| Family | Shadow code | Structured contract | Registry-backed | Production shadow proof | Enforcement |
|---|---:|---:|---:|---:|---:|
| `dag_engine` | Yes | Yes | Yes | **Proven — 1 bounded run (2026-07-22)** | No |
| `batch_harness` | Yes | Yes | Yes | **Proven — 1 bounded run (2026-07-22)** | Local-only canary; OFF |
| `staff.run_member` | Yes | Yes | Yes | Not proven | No |
| `coordinator` | Yes | Yes | Yes | Not proven | No |
| `supervisor/staff_supervisor` | Yes | Yes | Yes | Fixture/local proof only | No |

A second bounded production shadow canary was run for `batch_harness` (record-only; no enforcement;
`agent=nikhil`, `tenant=__system__`, `batch.internal.safe_calculation@1.0.0`, value 321; registry-bound
executor invoked 0 times; every temporary flag restored OFF). Full evidence:
`docs/agent_runtime/BATCH_SHADOW_PRODUCTION_CANARY_PROOF.md`.

**Production-shadow-proven families: 2 / 5 (`dag_engine`, `batch_harness`). Production-enforced
families: 0 / 5.** These canaries prove the bounded shadow path per family; they are **not**
platform-wide production readiness and grant no standing authorization for enforcement, agent
activation, or a further canary.

Production audit baseline: **2** harness shadow records (dag=1, batch=1, enforce=0). Audit file
SHA-256 `660fdb599092bed637773887a096d758509c41f86ad09d88e3a15e6bf4f5999e`. The original DAG record
remained byte-identical (SHA-256 `85f2b52de060de5355faa0f74dbc3c9d8971f77e60c6143250438972b12c9f0b`).
Any record beyond these two must be investigated.
