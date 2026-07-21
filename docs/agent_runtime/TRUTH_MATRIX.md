# 31-Agent Truth Matrix (Wave-B read-only canary scope)

Source: `team.STAFF` · `agent_registry` · `agent_runtime.PILOT_AGENTS` · `agent_runtime_workforce`.

## Counts (post local Pranav canary)

| Bucket | Count | Rollout state |
|---|---|---|
| **pranav** (SRE) | **1** | `canary_proven` — **LOCAL real-engine only**; prod NOT proven |
| Other Wave-A/B read-only pilots | **11** | `canary_ready` |
| GREEN mutate + AMBER/voice-adjacent hold | **17** | `rollout_hold` |
| Swara + Ananya | **2** | `intentionally_disabled` |
| **Total STAFF** | **31** | Boss=`manager` counted once |

## Production canary — BLOCKED

- Prod `/health.version` = `7ce4d97` — **behind** `origin/main` `10a3996`
- Branch tip `18b8d3e` (**not** deployed)
- `AGENT_RUNTIME` **not set** on prod
- Do **not** claim prod canary until deploy auth + drift cleared and flag set intentionally

## Architecture

```text
Owner/Admin → OpenClaw (OFF default) → Owner OS → agent_runtime → capability → existing engine
```

## Pilot allowlist (dispatchable when AGENT_RUNTIME=1 + primary flags)

`kavya, isha, zara, hermes, pranav, vidya, arnav, kabir, diya, aryan, arya, nikhil`

## First canary (proven locally)

**pranav** / `run_owned_workflow` → `engineer_agents.run_sre`
- GREEN diagnostic, read-only file/KPI checks, no customer contact, no shell/SQL execute, gated `SRE_AGENT`
- Local: `canary_proven` (real engine). Prod: still blocked (see above).

## Safety defaults

`AGENT_RUNTIME=0` · `OPENCLAW_ENABLED=0` · `PLATFORM_DIAL_DAILY=0` · Swara voice untouched
