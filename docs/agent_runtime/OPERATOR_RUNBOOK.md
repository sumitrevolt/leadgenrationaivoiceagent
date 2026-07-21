# Agent Runtime Wave-B — operator runbook

## Flags

| Flag | Default | Effect |
|---|---|---|
| `AGENT_RUNTIME` | unset/0 | Master gate — OFF = all runtime dispatch skipped |
| `AGENT_RUNTIME_LLM` | unset/0 | Isha LLM brief (free stack); OFF = template |
| Per-agent primary flags | mostly OFF | `SRE_AGENT`, `INFRA_HANDLER`, `MCP_ENGINEER`, … |
| `OPENCLAW_ENABLED` | unset/0 | Copilot edge OFF |
| `PLATFORM_DIAL_DAILY` | 0 | Calling HARD OFF |

## Rollback

1. Unset `AGENT_RUNTIME` on VPS `.env` → recreate `app` (+ workers if needed)
2. Optional code rollback: revert `PILOT_AGENTS` widen / workforce module
3. OpenClaw: keep `OPENCLAW_ENABLED` unset
4. Per-agent: Owner OS pause / drain / kill switches

## Canary order

1. Read-only Wave-B with `AGENT_RUNTIME=1` + one engineer flag (e.g. `SRE_AGENT=1`)
2. Prove Owner OS Runtime board + OpenClaw `runtime.status` / `agents.unhealthy`
3. Expand flags one agent at a time
4. Never enable Swara/calling via runtime

## DLQ

`data/agent_runtime_dlq.jsonl` — Owner OS Runtime tab tail. Bounded 500 lines.
