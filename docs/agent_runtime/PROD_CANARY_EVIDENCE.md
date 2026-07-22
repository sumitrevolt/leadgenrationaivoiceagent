# Production Pranav Canary Evidence

**Status:** `production_canary_proven`
**When (probe UTC):** `2026-07-21T23:14:22Z` (read-only SSH verify after canary)
**Deployed SHA:** `41765cfd` (`/health.version`, `environment=production`)
**Scope:** Single Pranav SRE read-only workforce canary on live VPS. **No secrets** in this doc.

## What was proven

1. PR #72 workforce runtime is live on prod at `41765cfd`.
2. Pranav owned-workflow path exercised with Redis-backed idempotency (not memory fallback).
3. Idempotency keys retained after canary (duplicate suppress path available).
4. Runtime flags restored to OFF after the canary (fail-closed default).

## Post-canary flag snapshot (read-only)

| Flag | Value |
|---|---|
| `AGENT_RUNTIME` | `0` |
| `AGENT_RUNTIME_EXECUTE` | unset |
| `/health.version` | `41765cfd` |
| `/health.environment` | `production` |
| `/health.status` | `healthy` |

## Redis idempotency evidence (no secrets)

| Field | Value |
|---|---|
| Module prefix | `idem:` (`app.billing.idempotency._PREFIX`) |
| Pattern | `*pranav-prod-canary*` |
| `KEY_COUNT` | `2` |
| Samples | `idem:agentrt:pranav-prod-canary-41765cfd-v1` |
| | `idem:agentrt:pranav-prod-canary-41765cfd-v1-b` |

## Queue / DLQ

| Key | Value | Note |
|---|---|---|
| `dlq:dead` | `7` | Pre-existing; canary did not clear or inflate this counter in the verify probe |

## Truth matrix counts (unchanged buckets)

| Bucket | Count | State |
|---|---|---|
| pranav | 1 | `production_canary_proven` (flags OFF after) |
| Other Wave-A/B read-only pilots | 11 | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent | 17 | `rollout_hold` |
| Swara + Ananya | 2 | `intentionally_disabled` |
| Total STAFF | 31 | |

## Explicit non-claims

- Did **not** enable fleet-wide `AGENT_RUNTIME=1` permanently.
- Did **not** flip OpenClaw, platform_dial, or Swara/voice.
- Did **not** redeploy during this evidence-doc session.
- No customer PII, API keys, or `.env` values recorded here.

## Related

- Local pre-prod proof: `docs/agent_runtime/CANARY_LOCAL_PROOF.md`
- Rollout matrix: `docs/agent_runtime/TRUTH_MATRIX.md`
