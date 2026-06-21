---
name: leadgen-composer
description: LeadGen AI primary agent brain — context-first edits, Hinglish replies, free-stack, council decisions, deploy verify. Use for ANY task on leadsgenai.in (Claude Code PRIMARY — read this first; Cursor mirror). Invoke context-first skill before every code edit.
---

# LeadGen Agent Brain (Claude Code PRIMARY)

> **Claude:** Har code task → Read `context-first` skill PEHLE. **Memory:** `CLAUDE.md` auto. **Index:** [skills-index.md](skills-index.md) · **Parity:** [../SKILLS_PARITY.md](../SKILLS_PARITY.md)

## User rules (non-negotiable)

- **Hinglish Roman** — concise, direct
- **Free stack only** — no paid LLM/STT/TTS
- **DO alag products** — Marketing vs Voice standalone; bundle framing mat
- **Commit/push** sirf jab user bole

## Claude superpower — context-first (MANDATORY)

Cursor auto-indexes; Claude must **manually batch parallel Grep/Read** before edit.

```
1. context-first skill → parallel Grep/Glob (routes, callers, tests, UI)
2. Read FULL files to touch
3. Plan minimal diff
4. Edit (Windows tools; same file parallel MAT)
5. verify-ship → green = done
```

**FastAPI:** `grep '@router'` — duplicate = first-route-wins shadow. **Windows = truth** — `.venv\Scripts\python.exe`.

## Task router (Read ONE matching skill)

| User ask | Skill |
|----------|-------|
| **Har code edit** | `context-first` |
| Session start | `leadgen-start` |
| Production ready / launch | `production-ready` |
| Done / deploy | `verify-ship` |
| Deploy / prod error | `leadgen-ops` |
| New API route | `duplicate-route-guard` |
| Windows git/SSH | `windows-dev-gotchas` |
| Pricing / 2 products | `product-split-adr` |
| Voice personas | `voice-roles` |
| VPS / Docker | `hostinger-deploy` |
| Debug | `systematic-debugging` |
| Marketing tab/API | `marketing-feature` |
| Strategy / go-no-go | `llm-council-decision` |
| Voice tune | `voice-agent-kb` + `test-agent` |
| Discipline / audit | `fable-operating-manual` |
| PR babysit | `babysit` |
| Find workflow | `find-skills` |

Full list → [skills-index.md](skills-index.md)

## Production state (2026-06-21)

- **Live:** https://leadsgenai.in · VPS `72.61.245.204` · Docker `leadgen_app`
- **P1 Marketing:** `ready_for_first_paid_customer=true` (UPI live)
- **P2 Voice:** code ready; Vobiz/DLT = owner blocker
- **Scheduler:** Celery worker+beat (`RUN_IN_PROCESS_SCHEDULER=0`)
- **Council:** `POST /api/agents/council` · `/app/agents`
- **Payments:** UPI primary; Razorpay removed

Probe: `curl.exe https://leadsgenai.in/api/activation/summary`

## Verify before "done"

```bat
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe -m pytest tests\test_<area>.py -q
```

Detail: `verify-ship`

## Claude vs Cursor — stay ahead

| Cursor edge | Claude match |
|-------------|--------------|
| Always-on rule | `leadgen-composer` + `context-first` Read each task |
| Parallel tools | **Batch Grep/Read in one turn** |
| Fast iteration | **Don't** subagent small fixes |
| prod_check habit | `verify-ship` mandatory |

## Anti-patterns

- Edit bina Grep/Read
- Subagent har chhoti cheez
- "Ho gaya" bina prod_check
- Duplicate marketing routes
- Secrets in committed files
- SESSION_LOG bash append
