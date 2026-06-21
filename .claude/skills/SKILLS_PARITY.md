# Skills Parity — Cursor/Composer ↔ Claude Code

> **Goal:** Jo capabilities Cursor Composer me hain, wahi `.claude/skills/` me documented hon taaki Claude Code bina gap ke kaam kare.
> **Primary brain:** `.claude/skills/leadgen-composer/SKILL.md` (Composer skill ka Claude mirror).
> **Project skills:** ~69 folders in `.claude/skills/` + ~181 in `data/skills_extra/` (skill_pack).

## Cursor built-in → Claude repo skill

| Cursor (`~/.cursor/skills-cursor/`) | Claude (repo) | Notes |
|-------------------------------------|---------------|-------|
| *(leadgen-composer)* | `leadgen-composer/` | Primary LeadGen brain |
| `automate` | `automate/` | LeadGen = Celery/scheduler; Cursor = Automations UI |
| `babysit` | `babysit/` | PR merge-ready loop (`gh`) |
| `canvas` | `canvas/` | Cursor `.canvas.tsx`; Claude = markdown/HTML fallback |
| `create-hook` | `create-hook/` | `.cursor/hooks.json` |
| `create-rule` | `create-rule/` | `.cursor/rules/*.mdc` + `CLAUDE.md` |
| `create-skill` | `create-skill/` | `.claude/skills/<name>/SKILL.md` |
| `create-subagent` | `create-subagent/` | Claude `Task` tool |
| `loop` | `loop/` | Recurring shell sentinel |
| `migrate-to-skills` | `migrate-to-skills/` | Rules/commands → SKILL.md |
| `review` | `review/` | *(existing)* code review |
| `review-bugbot` | `review-bugbot/` | Bugbot-style local review |
| `review-security` | `security-review/` | *(existing)* |
| `shell` | `shell/` | Literal `/shell` command |
| `split-to-prs` | `split-to-prs/` | Multi-PR split |
| `sdk` | `agent-sdk/` | Agent SDK apps |
| `statusline` | `statusline/` | Cursor IDE only (reference) |
| `update-cursor-settings` | `update-claude-settings/` | `CLAUDE.md` / project memory |
| `update-cli-config` | `update-cli-config/` | CLI config |

## P0 — Claude project accuracy (added 2026-06-21)

| Skill | When |
|-------|------|
| `verify-ship` | prod_check + deploy gate |
| `duplicate-route-guard` | new FastAPI routes |
| `windows-dev-gotchas` | Windows git/SSH/VPS |
| `product-split-adr` | Marketing vs Voice split |
| `voice-roles` | Swara / Ananya / Riya |

## LeadGen domain skills (already in `.claude/skills/`)

See `leadgen-composer/skills-index.md` — ops, voice, marketing, agents, infra, business.

## Slash commands → skills

| Command | File | Skill equivalent |
|---------|------|------------------|
| `/verify` | `.claude/commands/verify.md` | leadgen-ops |
| `/ship` | `.claude/commands/ship.md` | deploy + ship-checklist |
| `/checkpoint` | `.claude/commands/checkpoint.md` | memory-vault |
| `/learn` | `.claude/commands/learn.md` | SESSION_LOG append |
| `/compact-check` | `.claude/commands/compact-check.md` | token discipline |
| `/optimize` | `.claude/commands/optimize.md` | growth-optimizer |
| `/test-expand` | `.claude/commands/test-expand.md` | tdd-contract-first |

## How Claude should load skills

1. Har turn: `CLAUDE.md` (auto).
2. Task match → Read **one** `.claude/skills/<name>/SKILL.md` (poora 247 mat load).
3. Ambiguous strategy → `llm-council-decision`.
4. Skill missing → `find-skills` → `data/skills_extra/`.

## VPS

Skills baked in Docker image (`.claude/skills/` COPY). Data-only extras in `./data/skills_extra/` bind-mount — git pull pe live, rebuild NAHI.
