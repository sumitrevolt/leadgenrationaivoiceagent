# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** + **nikhil** | **2** | `production_canary_proven` (flags OFF — not permanently enabled) |
| Other Wave-A/B read-only pilots | **10** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara (Voice AI) + Ananya (Booking Voice) | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Shared runtime controls

| Control | State |
|---|---|
| pause / stop_claims / drain new-work / kill | `production_proven` |
| cancellation same-process | `production_proven` |
| cancellation cross-process | `production_proven` (SHA `d4b248f5`) |
| cancellation_backend | `redis` (`fallback_active: false`) |
| race rechecks | `integration_proven` |
| idempotency_backend (after this PR) | `redis` fail-closed (code) |
| idempotency_memory_fallback | `false` (agent runtime) |
| idempotency_cross_process | **SUPERSEDED for Pranav** — see `DISTRIBUTED_IDEMPOTENCY_PRODUCTION_PROOF.md` (`PRODUCTION-PROVEN`, Pranav-only). Matrix row below kept historically false until a third agent is proven. |
| idempotency_production_proven | `false` (matrix scope = fleet-wide); Pranav-only proof = **true** per production-proof doc |

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

See `DISTRIBUTED_CANCELLATION.md` · `DISTRIBUTED_IDEMPOTENCY.md` · `DISTRIBUTED_IDEMPOTENCY_PRODUCTION_PROOF.md` · `CANARY_PREFLIGHT.md`.
