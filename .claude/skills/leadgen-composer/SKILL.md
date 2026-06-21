---
name: leadgen-composer
description: LeadGen AI primary agent brain — context-first edits, Hinglish replies, free-stack, council decisions, deploy verify. Use for ANY task on leadsgenai.in (Claude Code, Cursor Composer, or CLI). Read skills-index.md for deep workflows.
---

# LeadGen Agent Brain (Claude Code + Composer parity)

> **Memory:** `CLAUDE.md` + `AGENTS.md` auto-load. **Deep skills:** `.claude/skills/` — on-demand Read via [skills-index.md](skills-index.md). **Cursor parity:** `.claude/skills/SKILLS_PARITY.md`.

## User rules (non-negotiable)

- **Hinglish Roman** replies — concise, direct.
- **Free stack only** — no paid LLM/STT/TTS suggestions.
- **DO alag products** — Marketing (main) vs Voice Agent (standalone); bundle framing mat use karo.
- **Commit/push** sirf jab user bole.

## Context-first (mandatory har code task)

**Edit se PEHLE:**

```
1. Grep/Glob  → saare touch-points (callers, routes, tests, UI)
2. Read FULL  → jin files ko chhoona hai
3. Plan       → minimal diff
4. Edit       → Windows file-tools; same file parallel MAT
5. Verify     → prod_check + targeted pytest; green = done
```

**FastAPI:** `grep '@router'` pehle — duplicate = first-route-wins shadow. **Windows = truth** — `.venv\Scripts\python.exe`.

## Task router

| User ask | Read skill |
|----------|------------|
| Session bootstrap | `.claude/skills/leadgen-start/SKILL.md` |
| Done / deploy | `.claude/skills/verify-ship/SKILL.md` |
| Deploy / prod | `.claude/skills/leadgen-ops/SKILL.md` |
| New API route | `.claude/skills/duplicate-route-guard/SKILL.md` |
| Windows terminal | `.claude/skills/windows-dev-gotchas/SKILL.md` |
| Pricing / 2 products | `.claude/skills/product-split-adr/SKILL.md` |
| Voice personas | `.claude/skills/voice-roles/SKILL.md` |
| VPS / Docker | `.claude/skills/hostinger-deploy/SKILL.md` |
| Debug | `.claude/skills/systematic-debugging/SKILL.md` |
| Marketing feature | `.claude/skills/marketing-feature/SKILL.md` |
| Council / strategy | `.claude/skills/llm-council-decision/SKILL.md` |
| Voice tune | `.claude/skills/voice-agent-kb/SKILL.md` + `test-agent` |
| PR babysit | `.claude/skills/babysit/SKILL.md` |
| Split PRs | `.claude/skills/split-to-prs/SKILL.md` |
| Recurring task | `.claude/skills/loop/SKILL.md` |
| New skill | `.claude/skills/create-skill/SKILL.md` |

Full index → [skills-index.md](skills-index.md) · Cursor parity → [../SKILLS_PARITY.md](../SKILLS_PARITY.md)

## Verify before "done"

```bat
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe -m pytest tests\test_<relevant>.py -q
```

## Live quick facts

- **URL:** https://leadsgenai.in · VPS `72.61.245.204` · Docker `leadgen_app`
- **Council:** `POST /api/agents/council` · UI `/app/agents`
- **Payments:** UPI primary (`UPI_VPA`)
