# Distributed Cancellation (Agent Runtime)

**Status:** Redis-backed cross-process cancellation is **production-proven** on SHA `d4b248f5` (Pranav-only). See `DISTRIBUTED_CANCELLATION_PRODUCTION_PROOF.md`.

**Why (historical):** process-local `_CANCELLED_AGENTS` only worked inside one process. Owner OS / API
cancellation was invisible to Celery workers → previously `cancellation_cross_process: not_supported`.

## Architecture

```text
Owner OS / API
  → agent_runtime.request_cancel_run / owner_agent_execution.request_cancel_running(art_*)
  → Redis CancellationStore (agentrt:cancel:<agent_id>:<runtime_run_id>)
  → worker run_task checkpoints
  → cooperative ctx.raise_if_cancelled() | non-cooperative classification
  → terminal AgentResult + Owner OS audit
```

## Identity

Preferred target: **`runtime_run_id`** (`art_…` task id).

Emergency agent-wide cancel enumerates **currently registered** `_ACTIVE_TASKS` only —
no permanent agent marker; future runs are unaffected.

## Redis record

- Namespace: `agentrt:cancel:<agent_id>:<runtime_run_id>`
- TTL: `AGENT_RUNTIME_CANCEL_TTL_S` (default 3600)
- Schema v1 JSON (no secrets, reason ≤200 chars)
- Backend: Redis in production (`cancellation_backend: redis`, `fallback_active: false`)
- Tests may set `AGENT_RUNTIME_CANCEL_BACKEND=memory|file` explicitly

## Checkpoints (bounded Redis GETs per run)

1. `evaluate_policy` (when run id exists)
2. Before concurrency slot
3. After slot / before durable
4. After durable / before engine
5. Immediately before `cap.fn`
6. Cooperative engine checkpoints (`AgentExecutionContext.raise_if_cancelled`)
7. After engine return (non-coop classification)

Expected ops ≈ **5–8 GET** + 0–1 SET per cancelled lifecycle. No `KEYS *`, no scan loops.

## Terminal semantics

| Situation | Status / reason |
|---|---|
| Cancel before engine | `cancelled` / `cancel_requested` |
| Cooperative in-flight | `cancelled` / `cancel_requested` |
| Non-coop engine finishes | `succeeded` / `cancel_requested_but_engine_completed` |
| Redis store down at check | `blocked` / `cancellation_store_unavailable` |
| Agent-wide, nothing running | `no_running_tasks` (ok) |

## Redis outage

Must **not** mean “not cancelled”. Fail-closed before engine. No silent memory fallback in production.

## Owner OS response (art_* runs)

```json
{
  "ok": true,
  "command_id": "ocmd_…",
  "status": "cancel_requested",
  "agent_id": "pranav",
  "targeted_run_ids": ["art_…"],
  "cancellation_backend": "redis",
  "requested_count": 1,
  "already_requested_count": 0
}
```

Legacy staff-job cancel (`owner_os:cancel_request:`) remains for non-`art_*` ids (Isha loops).

## Idempotency backend truth (co-verified, not redesigned)

| | |
|---|---|
| Module | `app/billing/idempotency.py` |
| Prefix | `idem:` |
| Primary | Redis `SET NX EX` |
| Fallback | **per-process memory FAIL-OPEN** on Redis error |
| Why Nikhil canary saw empty `idem:*` | fail-open memory path, different DB/index, TTL, or keys forgotten after blocked/cancelled paths |

Do not claim Redis-only idempotency without live key proof. Cancellation **is** Redis-authoritative when backend=redis.

## Rollback

Unset/disable deploy of this SHA; process-local cancel is removed — restore previous image if emergency. Flags stay OFF by default.

## Production proof (NOT executed in this PR)

Pranav-only after owner auth: API cancel → Redis key → worker observes → no engine → flags OFF.
