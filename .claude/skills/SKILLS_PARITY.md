# Skills Parity — Cursor/Composer ↔ Claude Code

> **Goal:** Claude Code is **PRIMARY** for this repo — skills encode Cursor's parallel context-first edge explicitly.
> **Start every code task:** `context-first` → `leadgen-composer` → one domain skill.
> **Project skills:** ~93 folders in `.claude/skills/` + ~181 in `data/skills_extra/`.

## Claude loading protocol (MANDATORY)

1. `CLAUDE.md` auto-loads each turn (lean memory).
2. **Any code/debug/edit** → Read `.claude/skills/context-first/SKILL.md` FIRST.
3. Task match → Read **one** domain `.claude/skills/<name>/SKILL.md`.
4. Ambiguous strategy → `llm-council-decision`.
5. Skill missing → `find-skills` → `data/skills_extra/`.
6. **Never** load entire skills folder (token burn).

## P0 — Claude beats Cursor (2026-06-21 update)

| Skill | When |
|-------|------|
| `context-first` | **Every code task — parallel Grep/Read before edit** |
| `leadgen-composer` | Primary brain + task router |
| `verify-ship` | prod_check + deploy gate |
| `production-ready` | launch / readiness / GO certification |
| `duplicate-route-guard` | new FastAPI routes |
| `windows-dev-gotchas` | Windows git/SSH/VPS |
| `product-split-adr` | Marketing vs Voice split |
| `voice-roles` | Swara / Ananya / Riya |

## Cursor built-in → Claude repo skill

| Cursor (`~/.cursor/skills-cursor/`) | Claude (repo) | Notes |
|-------------------------------------|---------------|-------|
| *(leadgen-composer)* | `leadgen-composer/` | Primary brain |
| *(parallel index)* | `context-first/` | **NEW** — Cursor default behavior for Claude |
| `automate` | `automate/` | Celery/scheduler |
| `babysit` | `babysit/` | PR merge-ready |
| `canvas` | `canvas/` | Claude = markdown/HTML |
| `create-hook` | `create-hook/` | `.cursor/hooks.json` |
| `create-rule` | `create-rule/` | rules + CLAUDE.md |
| `create-skill` | `create-skill/` | new SKILL.md |
| `create-subagent` | `create-subagent/` | Task tool |
| `loop` | `loop/` | recurring shell |
| `migrate-to-skills` | `migrate-to-skills/` | rules → skills |
| `review` | `review/` | code review |
| `review-bugbot` | `review-bugbot/` | bug-style review |
| `review-security` | `security-review/` | security |
| `shell` | `shell/` | `/shell` command |
| `split-to-prs` | `split-to-prs/` | multi-PR |
| `sdk` | `agent-sdk/` | Agent SDK |
| `statusline` | `statusline/` | Cursor IDE only |
| `update-cursor-settings` | `update-claude-settings/` | CLAUDE.md |
| `update-cli-config` | `update-cli-config/` | CLI config |

## Slash commands → skills

| Command | Skill equivalent |
|---------|------------------|
| `/verify` | `verify-ship` (quick) |
| `/ship` | `verify-ship` + `leadgen-ops` |
| `/checkpoint` | `memory-vault` |
| `/learn` | SESSION_LOG append (Edit only) |
| `/compact-check` | `leadgen-start` token rules |
| `/optimize` | growth-optimizer |
| `/test-expand` | `tdd-contract-first` |

## VPS

Skills baked in Docker image (`.claude/skills/` COPY). `data/skills_extra/` bind-mount — git pull live, no rebuild.

## Production truth probe

```text
curl.exe https://leadsgenai.in/api/activation/summary
→ ready_for_first_paid_customer, blocker_count, warns
```

Detail: `production-ready` skill.
