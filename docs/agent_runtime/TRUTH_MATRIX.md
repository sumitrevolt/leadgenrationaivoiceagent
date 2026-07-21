# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** (SRE) | **1** | `production_canary_proven` (flags OFF after) |
| Other Wave-A/B read-only pilots | **11** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Production canary — PROVEN (flags restored OFF)

| Fact | Evidence |
|---|---|
| Deployed /health version | `41765cfd` (PR #72 merged + deployed) |
| Post-canary flags | `AGENT_RUNTIME=0`, `AGENT_RUNTIME_EXECUTE` unset |
| Idempotency prefix | `idem:` (no secrets) |
| Redis canary keys | `KEY_COUNT=2` — `idem:agentrt:pranav-prod-canary-41765cfd-v1`, `idem:agentrt:pranav-prod-canary-41765cfd-v1-b` |
| DLQ | `dlq:dead=7` (pre-existing; unchanged by canary) |
| OpenClaw / platform_dial / Swara | unset / HARD OFF / FROZEN |

Full write-up: `docs/agent_runtime/PROD_CANARY_EVIDENCE.md`.
Local (pre-prod) proof remains: `docs/agent_runtime/CANARY_LOCAL_PROOF.md`.

## Pilot allowlist (post-PR#72)

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`
