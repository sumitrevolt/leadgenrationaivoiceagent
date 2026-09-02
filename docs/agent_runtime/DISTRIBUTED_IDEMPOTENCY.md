# Distributed Idempotency (Agent Runtime)

**Status:** implementation + CI — **not** production-proven until authorized deploy + Pranav proof.

**Why:** billing `idempotency.seen_before_sync` is Redis-primary with **memory fail-open**.
When Redis blips, workers execute duplicates; process memory is invisible cross-process.

## Architecture

```text
Owner OS/API
→ atomic Redis claim (agentrt:idem:v1:…)
→ runtime run (after policy + slot)
→ worker execution
→ terminal Redis record (succeeded|failed|cancelled|…)
→ duplicate response (original_run_id + status)
```

## Identity

```text
agentrt:idem:v1:<scope>:<agent_id>:<capability>:<sha256(raw_key)[:32]>
scope = platform | tenant:<id>
```

Raw keys hashed; length-bounded; no secrets/payloads stored.

## TTL

`AGENT_RUNTIME_IDEM_TTL_S` (default 14 days). Terminal records retain TTL (not deleted on success).
Independent of cancellation TTL (`AGENT_RUNTIME_CANCEL_TTL_S`).

## Semantics

| Event | Behavior |
|---|---|
| First claim | `SET NX` → `in_progress` |
| Duplicate in progress | `duplicate_in_progress` + original_run_id |
| Duplicate after success/fail/cancel | `duplicate_suppressed` |
| Control-blocked after claim | `release` (key not burned) |
| Capability skip | `release` |
| Cancel after claim | terminal `cancelled` |
| Non-coop complete | `cancel_requested_but_engine_completed` |
| Redis unavailable | `idempotency_store_unavailable` — **no engine** |
| Terminal Redis write fail after engine | `execution_completed_idempotency_commit_uncertain` |
| Same-key after failure | **not** auto-retried — need new key |

## Backends

```yaml
production: redis (fallback_active: false)
tests: AGENT_RUNTIME_IDEM_BACKEND=memory|file (explicit)
```

Billing webhook idempotency (`app/billing/idempotency.py`) remains fail-open by design for payment events — **out of scope**.

## Ops per lifecycle

claim · (optional running update) · terminal complete · duplicate lookup. No `KEYS *`.

## Rollback

Revert deploy to prior SHA; memory fail-open returns only if old image restored.

## Production proof (NOT executed here)

Pranav-only concurrent duplicate + restart survival + exact-key TTL after owner auth.
