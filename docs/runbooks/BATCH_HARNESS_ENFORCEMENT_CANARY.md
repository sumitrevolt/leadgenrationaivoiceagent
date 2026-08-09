# Batch Harness Enforcement Canary — Runbook

> **STATUS: PREPARED, NOT ACTIVE. Enforcement is OFF (`AGENT_HARNESS_ENFORCE=0`).**
> Do NOT activate without explicit Owner approval (see §Owner Approval below).
> This canary is LOCAL/INTERNAL only. No production, customer, external-send,
> calling, billing, or code-execution effect is in scope.

## 1. Exact canary boundary

| field | value |
|---|---|
| tool | `batch.internal.safe_calculation` |
| version | `1.0.0` |
| risk lane | GREEN |
| side-effect | READ_ONLY (deterministic internal calculation; no I/O, no network, no mutation) |
| authority | INTERNAL_AUTONOMOUS |
| agent | `nikhil` (only) |
| tenant scope | `__system__` (only) |
| loop | `batch_harness` (only) |
| max items | 5 |
| external effects | none |
| duration | one bounded run |

The registry-bound executor (`app/agents/harness/enforce.py:_safe_calculation_executor`)
is authoritative in enforce mode. Any caller-supplied `fn` passed to `run_batch`
is IGNORED in enforce mode — it never executes.

## 2. Flags

Inert default (current, and the required end-state of every session):

```env
AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_ENFORCE_AGENTS=
AGENT_HARNESS_ENFORCE_LOOPS=
AGENT_HARNESS_ENFORCE_TOOLS=
```

Future OWNER-APPROVED local canary values (do NOT set without approval):

```env
AGENT_HARNESS=1
AGENT_HARNESS_SHADOW=0
AGENT_HARNESS_ENFORCE=1
AGENT_HARNESS_ENFORCE_AGENTS=nikhil
AGENT_HARNESS_ENFORCE_LOOPS=batch_harness
AGENT_HARNESS_ENFORCE_TOOLS=batch.internal.safe_calculation@1.0.0
```

`AGENT_HARNESS_SHADOW=1` AND `AGENT_HARNESS_ENFORCE=1` together = INVALID → resolves
fail-closed to OFF. No wildcard (`*`) is accepted in agents/loops/tools for the first canary.

## 3. Preflight checks (all must pass before activation)

1. `harness.enforcement` (Kavach GREEN) reports `resolved_batch_mode=off` while flags are still off.
2. `bound_executors` includes `batch.internal.safe_calculation@1.0.0`.
3. `harness.registry` manifest hash matches the reviewed manifest.
4. `pytest tests/test_harness_enforce.py` = green (50 tests).
5. Full harness suite green (187), touched-loop regressions green (41).
6. Redis reachable (kill switch live): `harness.status.kill_switch.redis == true`.
7. `AGENT_HARNESS_ENFORCE_TOOLS` contains EXACTLY `batch.internal.safe_calculation@1.0.0`.
8. STAFF=31, calling = FULL CAMPAIGN LIVE (owner-approved 2026-08-02; bounded caps + compliance spine active — this canary has no calling/code-execution effect), `CODE_EXEC=0`.

## 4. Run (owner-approved only)

Single bounded internal batch, ≤5 items, agent `nikhil`, tenant `__system__`,
`tool_name=batch.internal.safe_calculation`, `tool_version=1.0.0`. No customer
data, no external side effect.

## 5. Success metrics

- registry-bound executor executions == item count
- legacy callable executions == 0
- `enforcement_completed` events == item count
- `enforcement_denied` == 0, `enforcement_duplicate_suppressed` == 0
- aggregate `done` == item count, `failed` == 0
- observed max concurrency == configured concurrency
- zero external side effects; checkpoint file has one line per item

## 6. Stop conditions (abort immediately)

- any `enforcement_denied` on the safe tool, or any `enforcement_failed`
- legacy callable executes even once
- duplicate execution (executor count > item count)
- any non-`__system__` tenant or non-`nikhil` agent appears
- Redis/kill-switch unreachable
- any attempt to enforce a non-GREEN / non-registered / non-allowlisted tool

## 7. Rollback (immediate, no redeploy of code)

```env
AGENT_HARNESS=0
AGENT_HARNESS_SHADOW=0
AGENT_HARNESS_ENFORCE=0
AGENT_HARNESS_CANARY_AGENTS=
AGENT_HARNESS_CANARY_LOOPS=
AGENT_HARNESS_ENFORCE_AGENTS=
AGENT_HARNESS_ENFORCE_LOOPS=
AGENT_HARNESS_ENFORCE_TOOLS=
```

Live kill (no redeploy): `StopController.request_kill("all")` (Redis
`harness:kill:all`) — denies every not-yet-started enforced item.
Proven: with all flags OFF the same batch runs the legacy path, the registry
executor runs 0 times, and 0 enforcement/shadow audit records are written.

## 8. Audit queries / expected events

`harness.explain <ckpt_id>` (Kavach GREEN) returns a `layers` breakdown:
`enforcement_decision`, `enforcement_execution`, `enforcement_denial`,
`shadow_observation`, `legacy_execution`.

Enforcement event sequence per allowed item:
`enforcement_requested → enforcement_evaluated → enforcement_started → enforcement_completed`.
Denied item: `enforcement_requested → enforcement_evaluated → enforcement_denied`
(no `enforcement_started`, executor never called).
Duplicate callback: `enforcement_duplicate_suppressed` (executor NOT re-run).

## 9. Owner approval (REQUIRED before activation)

- [ ] Owner has reviewed this runbook and the ADR (memory/decisions.md ADR-132).
- [ ] Owner explicitly approves activating enforcement for
      `batch.internal.safe_calculation@1.0.0`, agent `nikhil`, tenant `__system__`,
      loop `batch_harness`, ≤5 items, one bounded local run.
- Approved by: ______________________  Date: __________

**Prohibition:** No production use, no customer data, no external effect until this
box is checked by the Owner. The AMBER Kavach command `harness.enforce.enable`
parks through Owner OS — it does not self-activate.
