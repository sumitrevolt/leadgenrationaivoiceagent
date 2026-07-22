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
| cancellation cross-process | `implementation_ready` (CI/file proof; **not** production-proven) |
| race rechecks | `integration_proven` |
| cancellation_backend (after this PR) | `redis` (authoritative) |
| idempotency_backend | `redis_primary_with_memory_fail_open` (truthful; live KEYS proof PARTIAL) |

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

See `DISTRIBUTED_CANCELLATION.md` · `NIKHIL_FLAG_ISOLATION.md` · `CANARY_PREFLIGHT.md`.
