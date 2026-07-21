# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts (post safety harden)

| Bucket | Count | Rollout state |
|---|---|---|
| Wave-A + Wave-B read-only pilots | **12** | `canary_ready` (1 may become `canary_proven` after runtime proof) |
| GREEN mutate hold | **7** | `rollout_hold` (manager/lekha/neha/ravi/dev/guru/vikram) |
| AMBER + voice-adjacent hold | **10** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Architecture

```text
Owner/Admin → OpenClaw (OFF default) → Owner OS → agent_runtime → capability → existing engine
```

## Pilot allowlist (dispatchable when AGENT_RUNTIME=1 + primary flags)

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

## First canary candidate

**pranav** / `run_owned_workflow` → `engineer_agents.run_sre`
- GREEN diagnostic, read-only file/KPI checks, no customer contact, no shell/SQL execute, gated `SRE_AGENT`.

## Safety defaults

`AGENT_RUNTIME=0` · `OPENCLAW_ENABLED=0` · `PLATFORM_DIAL_DAILY=0` · Swara voice untouched
