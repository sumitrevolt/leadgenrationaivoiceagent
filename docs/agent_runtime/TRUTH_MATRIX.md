# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** + **nikhil** | **2** | `production_canary_proven` (flags OFF — not permanently enabled) |
| Other Wave-A/B read-only pilots | **10** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Shared runtime controls

| Control | State |
|---|---|
| pause / stop_claims / drain new-work / kill | `production_proven` |
| cancellation same-process | `production_proven` |
| cancellation cross-process | `production_proven` (PR #77 / SHA `d4b248f5`, Pranav-only) |
| race rechecks | `integration_proven` (+ prod cancel-before-lease) |
| cancellation_backend | `redis` (`fallback_active: false`) |
| idempotency_backend | `redis_primary_with_memory_fail_open` (distributed durability **not_proven**) |

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

See `DISTRIBUTED_CANCELLATION.md` · `DISTRIBUTED_CANCELLATION_PRODUCTION_PROOF.md` · `CANARY_PREFLIGHT.md`.
