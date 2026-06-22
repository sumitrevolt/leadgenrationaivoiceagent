---
name: update-cli-config
description: Update Codex or Cursor CLI configuration files. Use when user asks to change CLI model, permissions, or agent defaults.
disable-model-invocation: true
---
# Update CLI Config

## Locations (typical)

| Tool | Config |
|------|--------|
| Codex | `~/.Codex/settings.json` or project `.Codex/settings.json` |
| Cursor | Cursor Settings UI + `.cursor/` project files |

## Safety

- Never commit API keys
- Project-specific agent behavior → `AGENTS.md` + `.Codex/skills/` (preferred over global CLI hacks)

## LeadGen project

Repo agent behavior is **skills + AGENTS.md**, not CLI JSON. Change product flags via VPS `.env` + `GET /api/growth/infra/flags`.

If user wants CLI model override — document in personal settings only, not repo.
