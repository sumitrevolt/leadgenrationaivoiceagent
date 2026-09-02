---
name: leadgen-composer
description: LeadGen AI project ka primary Composer 2.5 operating skill — context-first edits, Hinglish replies, free-stack, council decisions, deploy verify. Use for ANY task on leadsgenai.in repo (code, debug, deploy, marketing feature, voice, agents). Canonical copy .claude/skills/leadgen-composer/SKILL.md — keep in sync.
---

# LeadGen Composer 2.5 — Project Brain

> **Canonical:** `.claude/skills/leadgen-composer/SKILL.md` (Claude PRIMARY). **Index:** [skills-index.md](skills-index.md) · [SKILLS_PARITY.md](../../.claude/skills/SKILLS_PARITY.md)

## User rules (non-negotiable)

- **Hinglish Roman** replies — concise, direct.
- **Free stack only** — no paid LLM/STT/TTS suggestions.
- **DO alag products** — Marketing (main) vs Voice Agent (standalone); bundle framing mat use karo.
- **Commit/push** sirf jab user bole.

## Composer superpower — context-first (mandatory har code task)

Composer Claude se fast + accurate isliye hai ki pehle poora context uthata hai. **Edit se PEHLE:**

```
1. Grep/Glob  → saare touch-points (callers, routes, tests, UI) — PARALLEL batch
2. Read FULL  → jin files ko chhoona hai (snippet blind edit = bug)
3. Plan       → kaun si files, minimal diff
4. Edit       → Windows file-tools; same file pe parallel edit MAT
5. Verify     → prod_check + targeted pytest; green = done
```

## Advanced working method (Composer/Claude default)

Use this loop for every non-trivial task:

1. **Discover:** touch-points first: code, callers, routes, UI, tests, docs, deploy/runtime path.
2. **Contract:** goal, files, minimal diff, risk gates, verify command.
3. **Execute:** smallest additive change matching local patterns.
4. **Self-review:** diff-check missed callers, duplicate routes, auth/billing/compliance, stale reads, test gaps.
5. **Evidence:** final includes changed files + verification proof; if not run, state why.

Decision ladder: execute when repo context gives a safe default; ask only for secrets, irreversible/destructive choices, spend, legal/business policy, or equal product directions; council for strategy/go-no-go; never stop at analysis when a safe patch/test can move the task forward.

## Enterprise automation standard

Any automation, scheduled job, agent loop, integration, webhook, billing flow, or production-path change needs: product outcome, owner, trigger/output, env flag, default-safe behavior, idempotency key/dedupe, timeout, bounded retry, DLQ/fail record, metric/event/heartbeat, kill-switch, rollback path, targeted tests, free-stack quota fallback, and compliance/auth gates fail-closed where required.

Automation design rule: event-driven/idempotent > cron-only polling; small composable loops > hidden monoliths; every background job must be observable, retry-safe, and stoppable.

Claude ke liye same: Read `.claude/skills/context-first/SKILL.md` har code task pe.

**FastAPI gotcha:** `grep '@router'` pehle — duplicate route = first-route-wins shadow.

**Windows = truth** — sandbox stale ho sakta; verify `.venv\Scripts\python.exe`.

## Task router (pehle yeh, phir deep skill Read)

| User ask | Read skill |
|----------|------------|
| **Har code edit** | `.claude/skills/context-first/SKILL.md` |
| Deploy / push / prod error | `.claude/skills/leadgen-ops/SKILL.md` |
| Production ready / launch | `.claude/skills/production-ready/SKILL.md` |
| VPS / Caddy / Docker | `.claude/skills/hostinger-deploy/SKILL.md` |
| Debug / bug | `.claude/skills/systematic-debugging/SKILL.md` |
| Naya marketing tab/API | `.claude/skills/marketing-feature/SKILL.md` |
| Multi-agent / council decision | `.claude/skills/llm-council-decision/SKILL.md` |
| Advancement council / ROI roadmap | `.claude/skills/executive-council/SKILL.md` |
| Voice agent tune | `.claude/skills/voice-agent-kb/SKILL.md` + `test-agent` |
| Session start | `.claude/skills/leadgen-start/SKILL.md` |
| Non-trivial discipline | `.claude/skills/fable-operating-manual/SKILL.md` |

Full list → [skills-index.md](skills-index.md)

## Production state (2026-06-21)

- P1 Marketing: **GO** — `ready_for_first_paid_customer=true` live
- P2 Voice: code GO; Vobiz/DLT owner-blocked
- Probe: `curl.exe https://leadsgenai.in/api/activation/summary`

## Verify before "done"

```bat
.venv\Scripts\python.exe scripts\prod_check.py
.venv\Scripts\python.exe -m pytest tests\test_<relevant>.py -q
```

Deploy loop: `leadgen-ops` → push → VPS `docker compose build app && up -d --no-deps app` → `/health` production 2×.

## Live facts (quick)

- **URL:** https://leadsgenai.in · VPS `72.61.245.204` · Docker `leadgen_app`
- **LLM Council LIVE:** `app/agents/llm_council.py` · `POST /api/agents/council`
- **Payments:** UPI primary (`UPI_VPA`) · Razorpay removed

## Anti-patterns (Composer avoid)

- Edit bina Grep/Read ke
- Task subagent har chhoti cheez pe (Composer khud parallel tools use karo)
- "Ho gaya" bina prod_check/pytest
- Duplicate marketing routes
- Secrets in committed files
