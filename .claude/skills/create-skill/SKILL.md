---
name: create-skill
description: Create Agent Skills for Claude Code and Cursor. Use when authoring SKILL.md, skill structure, or migrating workflows to .claude/skills/.
---
# Create Skill (LeadGen repo)

## Location

| Scope | Path |
|-------|------|
| **Project (preferred)** | `.claude/skills/<name>/SKILL.md` |
| Cursor-only duplicate | `.cursor/skills/<name>/SKILL.md` (optional mirror) |
| Packed extras | `data/skills_extra/<name>.md` (no rebuild) |

Never write to `~/.cursor/skills-cursor/` (Cursor internal).

## SKILL.md template

```markdown
---
name: my-skill
description: Third-person WHAT + WHEN triggers (max 1024 chars).
---

# Title

## Steps
1. ...
```

## Rules

- **Concise** — agent smart hai; sirf project-specific context.
- **<500 lines** in SKILL.md; detail → `reference.md`.
- Description = third person + trigger keywords.
- User verbatim text → copy as-is, don't paraphrase.
- After add: update `SKILLS_PARITY.md` or `skills-index.md` if platform skill.

## Verify

Skill discoverable via `find-skills` / `grep description` in folder.
