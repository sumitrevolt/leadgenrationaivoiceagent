---
name: leadgen-composer
description: LeadGen AI project ka primary Composer 2.5 operating skill — context-first edits, Hinglish replies, free-stack, council decisions, deploy verify. Use for ANY task on leadsgenai.in repo (code, debug, deploy, marketing feature, voice, agents). Read skills-index.md for deep .claude/skills workflows.
---

# LeadGen Composer 2.5 — Project Brain

> **Model:** Cursor Composer 2.5 · **Canonical skills:** `.claude/skills/` (Claude Code + Composer share). **Index:** [skills-index.md](skills-index.md) · [SKILLS_PARITY.md](../SKILLS_PARITY.md)

## User rules (non-negotiable)

- **Hinglish Roman** replies — concise, direct.
- **Free stack only** — no paid LLM/STT/TTS suggestions.
- **DO alag products** — Marketing (main) vs Voice Agent (standalone); bundle framing mat use karo.
- **Commit/push** sirf jab user bole.

---

## Composer superpower — context-first (mandatory har code task)

Composer Claude se fast + accurate isliye hai ki pehle poora context uthata hai. **Edit se PEHLE:**

```
1. Grep/Glob  → saare touch-points (callers, routes, tests, UI)
2. Read FULL  → jin files ko chhoona hai (snippet blind edit = bug)
3. Plan       → kaun si files, minimal diff
4. Edit       → Windows file-tools; same file pe parallel edit MAT
5. Verify     → prod_check + targeted pytest; green = done
```

**FastAPI gotcha:** `grep '@router'` pehle — duplicate route = first-route-wins shadow.

**Windows = truth** — sandbox stale ho sakta; verify `.venv\Scripts\python.exe`.

---

## Task router (pehle yeh, phir deep skill Read)

| User ask | Read skill |
|----------|------------|
| Deploy / push / prod error | `.claude/skills/leadgen-ops/SKILL.md` |
| VPS / Caddy / Docker | `.claude/skills/hostinger-deploy/SKILL.md` |
| Debug / bug | `.claude/skills/systematic-debugging/SKILL.md` |
| Naya marketing tab/API | `.claude/skills/marketing-feature/SKILL.md` |
| Multi-agent / council decision | `.claude/skills/llm-council-decision/SKILL.md` |
| Coordinator run | `.claude/skills/coordinator-orchestration/SKILL.md` |
| Voice agent tune | `.claude/skills/voice-agent-kb/SKILL.md` + `test-agent` |
| Session start / orientation | `.claude/skills/leadgen-start/SKILL.md` |
| Non-trivial discipline | `.claude/skills/fable-operating-manual/SKILL.md` |

Full list → [skills-index.md](skills-index.md)

---

## Council decisions (ambiguous / high-stakes)

Trigger: strategy, go/no-go, architecture fork, priority trade-off.

**Composer session protocol** (skill detail: `llm-council-decision`):
1. **Recruit** 2–4 tailored expert lenses (parallel Read/subagent only if disjoint heavy research)
2. **Opinions** — parallel short takes
3. **Peer rank** — Response A/B/C anonymized
4. **Chairman** — one Decision + Kyon + Next action

**LIVE API:** `POST /api/agents/council` (admin) · UI `/app/agents`

Chhote bugfix / exact user instruction → council skip.

---

## Code conventions

- **Additive > rewrite** — working code mat todo.
- **Gated + never-raise** — naye loops env-flag, try/except.
- **Ban-safe** — auto-send/call/post kabhi coordinator se nahi.
- **Pricing truth** — `app/marketing/packages.py` + `test_billing_truth_2026.py`.
- **UI feature** = API + admin tab saath (adhoora mat chhod).

---

## Verify before "done"

```bat
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe -m pytest tests\test_<relevant>.py -q
```

Deploy loop: `leadgen-ops` → push → VPS `docker compose build app && up -d --no-deps app` → `/health` production 2×.

---

## Live facts (quick)

- **URL:** https://leadsgenai.in · VPS `72.61.245.204` · Docker `leadgen_app`
- **DB:** Postgres via PgBouncer · **Scheduler:** Celery worker+beat
- **LLM Council LIVE:** `app/agents/llm_council.py` · `POST /api/agents/council`
- **Payments:** UPI primary (`UPI_VPA`) · Razorpay removed

---

## Anti-patterns (Composer avoid)

- Edit bina Grep/Read ke
- Task subagent har chhoti cheez pe (Composer khud parallel tools use karo)
- "Ho gaya" bina prod_check/pytest
- Duplicate marketing routes
- Secrets in committed files
