---
name: update-claude-settings
description: Update project memory and agent settings — CLAUDE.md, AGENTS.md, .cursor/rules. Use when user wants to persist preferences, gotchas, or current-state facts across sessions.
---
# Update Claude / Project Settings

## Source of truth hierarchy

1. **`CLAUDE.md`** — lean auto-loaded memory (current state, blockers, gotchas)
2. **`AGENTS.md`** — duplicate lean memory (some tools load both)
3. **`docs/SESSION_LOG.md`** — dated history (NOT auto-load)
4. **`.cursor/rules/*.mdc`** — Cursor IDE rules

## CLAUDE.md rules

- Token discipline: facts only, 1-2 line milestone max
- **Never** bash-append (corruption risk) — use Edit tool
- No secrets, no build logs
- Pricing truth → `packages.py` not memory alone

## User preferences (LeadGen)

- Hinglish Roman replies
- Free stack only
- Commit/push on user ask only
- DO alag products (Marketing vs Voice)

## Cursor settings

User-level IDE prefs → `update-cursor-settings` in Cursor; project prefs → `create-rule` skill.

After major infra change: update CLAUDE.md + optional SESSION_LOG append.
