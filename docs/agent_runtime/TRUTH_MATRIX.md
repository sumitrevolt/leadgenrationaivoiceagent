# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **Pranav (SRE / Reliability)** + **Nikhil (Revenue Ops)** | **2** | `production_canary_proven` (flags OFF) |
| Remaining Wave-A/B read-only pilots | **10** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara (Voice AI) + Ananya (Booking Voice) | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

Neither Pranav nor Nikhil is `production_enabled` (flags OFF after canary rollback).

## Nikhil isolation

| | |
|---|---|
| Flag | `DELIVERY_ASSURANCE_AGENT` (default OFF) |
| Lane | GREEN |
| Proof | `NIKHIL_PRODUCTION_CANARY_PROOF.md` · deployed `a7410c2d` |
| Preflight | `canary_isolation_preflight` — PRODUCTION-PROVEN |

## Dispatchable flag safety

| | |
|---|---|
| Dispatchable | 12 |
| Explicitly gated | 12 |
| Ungated | 0 |
| Single-agent canary preflight | production_proven |

## Shared runtime controls

| Control | State |
|---|---|
| pause / stop_claims / drain new-work / kill | `production_proven` (Pranav + Nikhil) |
| cancellation same-process | `production_proven` |
| cancellation cross-process | `not_supported` |
| race rechecks | `integration_proven` |
| stable command_id | `production_proven` |

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`
