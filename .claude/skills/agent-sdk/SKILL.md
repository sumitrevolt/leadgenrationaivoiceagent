---
name: agent-sdk
description: Build and verify Python or TypeScript Agent SDK applications. Use when creating agent apps with Claude/OpenAI SDK patterns in this repo.
---
# Agent SDK (LeadGen context)

## This repo's agents (not generic SDK hello-world)

| Pattern | Location |
|---------|----------|
| Voice agent | `app/voice_agent/` |
| Staff / Celery | `app/platform/team.py`, `app/worker.py` |
| Coordinator | `app/agents/coordinator.py` |
| Council | `app/agents/llm_council.py` |
| MCP product | `/api/mcp-product`, `/mcp` |

## External Agent SDK apps

If user builds **standalone** SDK app:
- Python verifier: `agent-sdk-verifier-py` subagent (Task tool)
- TypeScript: `agent-sdk-verifier-ts` subagent

## LeadGen integration path

Prefer **additive** wiring into existing FastAPI routes — not new microservice unless asked.

Env flags default OFF · never-raise handlers · ban-safe drafts only.
