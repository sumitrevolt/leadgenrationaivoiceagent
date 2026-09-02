# Agent Runtime — Shared Control Semantics

Canonical admission precedence (see also `agent_runtime.evaluate_policy` / module docstring):

1. invalid agent / missing contract
2. RED hard-off / frozen
3. `AGENT_RUNTIME` master flag
4. per-agent `primary_flag`
5. kill switches → `AgentResult.reason` = `kill_switch_engaged:<key>`; `decision.reason_code` = `kill_switch_active`
6. Owner OS stop-claims / drain / pause via `owner_agent_execution.runtime_admission_blocked`
7. distributed run-cancel (`agentrt:cancel:<agent>:<runtime_run_id>`) → `cancelled` / `cancel_requested`
8. capability / tenant / approval / budget policy
9. concurrency slot + durable lease
10. pre-engine re-check (controls + cancel) → engine
11. idempotency claim (after slot) → Redis fail-closed; duplicates skipped

## Pause / drain / stop-claims contract

| Control | Runtime behavior | Reason code |
|---|---|---|
| `manual_pause` (+ V1 `agent_controls` sidecar) | **Reject** submission (no park, no lease) | `agent_paused` |
| `drain` (implies stop_claims + scheduled_pause) | Reject new work; in-flight may finish | `agent_draining` |
| `stop_claims` alone | Reject new work / no lease | `agent_claims_stopped` |

Resume / clear controls restores bounded claims only — **no catch-up flood** (no missed-interval replay).

`claim_allowed()` for staff/scheduler still ignores `manual_pause` (legacy); agent_runtime uses `runtime_admission_blocked()`.

## Cancellation (Redis-backed)

Full contract: `DISTRIBUTED_CANCELLATION.md`.

- Identity: specific `runtime_run_id` (`art_*`). Agent-wide emergency = cancel each **active** run only.
- Before engine: status `cancelled`, reason `cancel_requested`.
- Non-cooperative engine finishes after cancel mid-flight: status `succeeded`, reason `cancel_requested_but_engine_completed`.
- Redis unavailable at check: `blocked` / `cancellation_store_unavailable` (never silent “not cancelled”).
- Process-local `_CANCELLED_AGENTS` **removed**. Primary backend: Redis. Legacy process-local: disabled.

## Idempotency (Redis-backed, fail-closed)

Full contract: `DISTRIBUTED_IDEMPOTENCY.md`.

- Claim after policy + concurrency slot (blocked admissions do not burn success keys).
- Duplicate → `skipped` / `duplicate_suppressed` or `duplicate_in_progress`.
- Redis unavailable → `blocked` / `idempotency_store_unavailable` (no memory fail-open).
- Failed/cancelled terminals retained; same key does not auto-retry (new key required).
- Control-block / capability skip → `release` in-progress claim.

## Race closes

Admission re-checked: (1) in `evaluate_policy`, (2) after policy / before slot, (3) after slot / before durable+idem, (4) immediately before `cap.fn`, plus cancel probes at those boundaries.

## Owner OS command response

`create_command` always exposes top-level `command_id` (+ `status`) while keeping nested `command` for legacy callers. Cancel-running for `art_*` returns structured Redis cancel fields (`targeted_run_ids`, `cancellation_backend`, counts).
