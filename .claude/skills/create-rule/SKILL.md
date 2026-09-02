---
name: create-rule
description: Create persistent AI rules — Cursor .mdc rules and CLAUDE.md project memory. Use for coding standards, always-apply conventions, or file-specific patterns.
---
# Create Rule

## Two surfaces (LeadGen)

| Surface | File | When |
|---------|------|------|
| **Claude memory (primary)** | `CLAUDE.md` | Lean current-state facts — auto-loads every turn |
| **Cursor rules** | `.cursor/rules/*.mdc` | IDE-specific; `alwaysApply` or globs |
| **History (not auto-load)** | `docs/SESSION_LOG.md` | Dated milestones only |

## .mdc format

```markdown
---
description: One line trigger
globs: **/*.py   # optional
alwaysApply: false
---
# Rule body
```

## CLAUDE.md edits

- Token discipline: lean facts only — no build logs.
- Edit via Windows file-tools only (sandbox corrupts append).
- Never commit secrets.

## Questions if unclear

- Always apply vs file-specific globs?
- Cursor only vs Claude memory too?

Mirror important rules in both when team uses Cursor + Claude Code.
