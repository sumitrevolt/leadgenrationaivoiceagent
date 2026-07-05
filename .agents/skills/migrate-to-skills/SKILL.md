---
name: migrate-to-skills
description: Convert Cursor rules (.mdc) and slash commands (.md) to Agent Skills (SKILL.md). Use when consolidating rules/commands into .claude/skills/.
disable-model-invocation: true
---
# Migrate to Skills

**CRITICAL:** Copy body **verbatim** — no reformat.

## Sources

| Source | Destination |
|--------|-------------|
| `.cursor/rules/*.mdc` (has `description`, NOT alwaysApply) | `.claude/skills/<name>/SKILL.md` |
| `.cursor/commands/*.md` | `.claude/skills/<name>/SKILL.md` |
| `.claude/commands/*.md` | same name skill optional |

Skip: rules with only `globs` + no description. Ignore `~/.cursor/worktrees`, `skills-cursor/`.

## Rule → SKILL

Remove `globs`/`alwaysApply`; add `name:`; keep body exact.

## Command → SKILL

Add frontmatter:
```yaml
name: verify
description: Run prod_check and tests
disable-model-invocation: true
```

## LeadGen already migrated

- `/verify` → see `.claude/commands/verify.md` + `leadgen-ops` skill
- Project rules → `CLAUDE.md` + `.cursor/rules/leadgen-composer.mdc`

After migrate: update `SKILLS_PARITY.md`.
