# Agent Runtime — Shared Control Semantics

Canonical admission precedence (see also `agent_runtime.evaluate_policy` / module docstring):

1. invalid agent / missing contract
2. RED hard-off / frozen
3. `AGENT_RUNTIME` master flag
4. per-agent `primary_flag`
5. kill switches → `AgentResult.reason` = `kill_switch_engaged:<key>`; `decision.reason_code` = `kill_switch_active`
6. Owner OS stop-claims / drain / pause via `owner_agent_execution.runtime_admission_blocked`
7. soft cancel (`request_cancel`) → `cancel_requested`
8. capability / tenant / approval / budget policy
9. concurrency slot + durable lease
10. pre-engine re-check → engine

## Pause / drain / stop-claims contract

| Control | Runtime behavior | Reason code |
|---|---|---|
| `manual_pause` (+ V1 `agent_controls` sidecar) | **Reject** submission (no park, no lease) | `agent_paused` |
| `drain` (implies stop_claims + scheduled_pause) | Reject new work; in-flight may finish | `agent_draining` |
| `stop_claims` alone | Reject new work / no lease | `agent_claims_stopped` |

Resume / clear controls restores bounded claims only — **no catch-up flood** (no missed-interval replay).

`claim_allowed()` for staff/scheduler still ignores `manual_pause` (legacy); agent_runtime uses `runtime_admission_blocked()`.

## Cancellation

- Before engine: `cancel_requested` (blocked).
- Non-cooperative engine that finishes after cancel was set mid-flight: status may be `succeeded` with reason `cancel_requested_but_engine_completed` (honest — not a fake cancel).

## Race closes

Admission re-checked: (1) in `evaluate_policy`, (2) after policy / before slot, (3) after slot / before durable+idem, (4) immediately before `cap.fn`.

## Owner OS command response

`create_command` always exposes top-level `command_id` (+ `status`) while keeping nested `command` for legacy callers. No fabricated `runtime_run_id` at create time.
