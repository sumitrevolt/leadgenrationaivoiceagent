---
name: create-hook
description: Create Cursor hooks (.cursor/hooks.json) for agent event automation. Use when user wants pre/post tool hooks, session hooks, or shell gates.
---
# Create Hook (Cursor)

Hooks = JSON stdin/stdout scripts on agent events.

## Locations

- **Project:** `.cursor/hooks.json` + `.cursor/hooks/*` (commit to repo)
- **User:** `~/.cursor/hooks.json`

## Common events

`sessionStart` · `preToolUse` / `postToolUse` · `beforeShellExecution` · `afterFileEdit` · `beforeSubmitPrompt` · `subagentStart`

## Steps

1. Gather: scope, event, fail-open vs fail-closed, matcher (tool name).
2. Write hook script (bash/powershell) + register in hooks.json.
3. Test with minimal payload.

## Claude Code note

Claude Code CLI may not run Cursor hooks — document hook for Cursor users; equivalent guardrails in code (rate limits, `scripts/check_secrets.py`, pre-commit).

LeadGen example: session hook reminding `prod_check` before ship.
