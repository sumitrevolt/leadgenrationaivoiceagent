# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** (SRE / Reliability) | **1** | `production_canary_proven` |
| Other Wave-A/B read-only pilots (incl. **Nikhil (Revenue Ops)**) | **11** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

Nikhil is **not** `production_canary_proven` until isolated-flag deploy + canary auth.

## Nikhil flag isolation (code)

| | |
|---|---|
| Flag | `DELIVERY_ASSURANCE_AGENT` (default OFF) |
| Lane | GREEN (read-only scan reconciled) |
| Preflight | `agent_canary_preflight.canary_isolation_preflight` |
| Docs | `NIKHIL_FLAG_ISOLATION.md` · `AGENT_FLAG_CENSUS.md` · `CANARY_PREFLIGHT.md` |

## Shared runtime controls

| Control | State |
|---|---|
| pause / stop_claims / drain new-work / kill | `production_proven` (Pranav control-gate) |
| cancellation same-process | `production_proven` |
| cancellation cross-process | `not_supported` |
| race rechecks | `integration_proven` |

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`
