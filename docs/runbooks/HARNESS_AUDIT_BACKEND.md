# Runbook — Durable Harness Audit Backend

Capability for a durable, multi-worker-safe harness audit + shadow-dedup store. **Inert by default.**
See `docs/adr/ADR-139-durable-harness-audit-backend.md`.

## Default (no action needed)

`HARNESS_AUDIT_BACKEND` unset or `jsonl` → append-only file at `HARNESS_RUN_LOG`
(`data/harness_runs.jsonl`), exactly as before. No cross-worker dedup. This is the current
production baseline (2 records; checksum `660fdb599092bed637773887a096d758509c41f86ad09d88e3a15e6bf4f5999e`).

## Configuration

| Env var | Default | Meaning |
|---|---|---|
| `HARNESS_AUDIT_BACKEND` | `jsonl` | `jsonl` \| `redis` |
| `HARNESS_DEDUP_TTL_S` | `1209600` (14d) | atomic dedup claim lifetime |
| `HARNESS_AUDIT_MAXLEN` | `1000000` | approximate stream capacity guard (`0`=no trim) |
| `HARNESS_AUDIT_MAX_BYTES` | `16384` | per-event hard size cap |
| `HARNESS_RUN_LOG` | `data/harness_runs.jsonl` | jsonl sink path |

Redis is reused from the app client (`app.cache.get_redis` / `app.infrastructure.redis_client`).

## Activate the durable backend (requires separate owner authorization)

> Do **not** activate without owner sign-off. Activation is config-only; no code change.

1. Confirm Redis health: `harness.status` → `result.audit_backend.health.healthy == true`.
2. Decide migration (ADR §Migration): **Option A** (idempotent import of the 2 historical records)
   or **Option B** (baseline boundary, durable starts at 0, JSONL kept immutable).
3. Set `HARNESS_AUDIT_BACKEND=redis` in the environment and recreate the app/worker containers.
4. Verify `harness.status.result.audit_backend.backend == "redis"`, `fallback_active == false`.
5. Verify counts increment on the next real observation; `duplicates_suppressed` behaves under
   deliberate replay.

## Monitor

`harness.status` exposes (read-only, no secrets): `backend`, `health.healthy`, `fallback_active`,
`counts.total`, `counts.by_family`, `counts.by_mode`, `counts.duplicates_suppressed`,
`counts.backend_errors`, `oldest/newest_event_id`.

Alert thresholds (suggested): `backend_errors > 0` (page), `health.healthy == false` (page),
`fallback_active == true` while backend intended `redis` (misconfig), stream length approaching
`HARNESS_AUDIT_MAXLEN` (raise cap or add Postgres sink).

## Failure semantics (production honesty)

- **Redis unavailable (redis mode):** observation **fails closed** — dropped, `backend_errors`
  incremented, `logger.error` emitted. **No** silent fallback to process-local dedup or file. The
  legacy business result is unaffected (the audit layer never alters or re-runs legacy execution).
- **Claim ok then append crash:** treated as a failed write (fail-closed); no partial evidence
  claimed as durable. The dedup claim TTL lets a later retry of the *same* logical event resolve
  consistently.
- **This dedups evidence, not business execution.** Never cite audit dedup as exactly-once business
  execution.

## Rollback

Set `HARNESS_AUDIT_BACKEND=jsonl` (or unset) and recreate containers → immediate revert to the file
sink. No data migration required to roll back; the Redis stream/keys remain for inspection and expire
by TTL / capacity policy.

## Do NOT

- Activate in production without separate owner authorization.
- Enable any `AGENT_HARNESS*` / enforcement flag as part of this (unrelated and must stay OFF).
- Treat capability deployment as activation — deploying this code changes nothing until
  `HARNESS_AUDIT_BACKEND=redis`.
