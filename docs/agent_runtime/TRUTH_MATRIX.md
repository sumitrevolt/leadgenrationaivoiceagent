# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts (unchanged by control-admission work)

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** (SRE) | **1** | `production_canary_proven` (PR #72 / SHA `41765cfd`) |
| Other Wave-A/B read-only pilots | **11** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Shared runtime controls (system-level — not an agent count)

| Control | State |
|---|---|
| pause | `code_wired` — production proof pending owner auth deploy |
| drain | `code_wired` — production proof pending owner auth deploy |
| stop_claims | `code_wired` — production proof pending owner auth deploy |
| kill_switch | `production_proven` (Pranav canary) |
| cancellation | `accurately_classified` (incl. `cancel_requested_but_engine_completed`) |

After control-gate deploy + Pranav re-proof, promote pause/drain/stop_claims → `production_proven`.
Do **not** start Nikhil until that proof lands.

Canonical semantics: `docs/agent_runtime/CONTROL_SEMANTICS.md`.

## Pilot allowlist

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

## Local proof

`docs/agent_runtime/CANARY_LOCAL_PROOF.md` — real `run_sre`, idempotency, cancel, RED refuse.
