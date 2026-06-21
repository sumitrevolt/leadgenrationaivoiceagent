---
name: create-subagent
description: Launch Task subagents for parallel or isolated work. Use when exploring codebase, shell tasks, or Bugbot-style review needs a separate context.
---
# Create Subagent (Claude Code Task tool)

## When

- Broad repo exploration → `subagent_type: explore`
- Shell/deploy → `subagent_type: shell`
- PR CI investigate → `ci-investigator`
- Bug review → `bugbot` (readonly)
- Security diff → `security-review` (readonly)

## Rules

- **Parallel** independent tasks in one message (multiple Task calls).
- Narrow question → Grep/Read directly, no subagent.
- Pass full context in prompt (subagent has no chat history).
- `readonly: true` for review agents.

## LeadGen

- Deploy: shell subagent with Git ssh one-liners
- Explore: `grep '@router'` marketing routes before new feature
- Don't spawn subagent for every small edit — token cost

## vs Coordinator

Product multi-agent = `POST /api/agents/council` or `coordinator-orchestration` skill — not the same as Task subagent.
