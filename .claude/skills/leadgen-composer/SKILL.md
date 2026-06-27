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

## Advanced working method (default loop)

Use this loop for every non-trivial task:

1. **Discover:** identify touch-points first: code, callers, routes, UI, tests, docs, deploy/runtime path.
2. **Contract:** before editing, write the internal contract: goal, files, minimal diff, risk gates, verify command.
3. **Execute:** make the smallest additive change that matches local patterns; avoid rewrites unless the old path is proven wrong.
4. **Self-review:** inspect the diff for missed callers, duplicate routes, auth/billing/compliance regressions, stale Windows reads, and test gaps.
5. **Evidence:** final answer must name changed files plus proof run; if proof cannot run, say exactly why and what remains unverified.

Decision ladder:
- **Execute now** when repo context gives a safe default.
- **Ask user** only for external secrets, irreversible/destructive choices, spend, legal/business policy, or two equally valid product directions.
- **Council** only for strategy/go/no-go or ROI/moat decisions.
- **Never stop at analysis** when a small safe patch or test can move the task forward.

## Enterprise automation standard

Any automation, scheduled job, agent loop, integration, webhook, billing flow, or production-path change must satisfy this contract before "done":

| Gate | Required standard |
|------|-------------------|
| Product value | Define user/business outcome, owner, trigger, output, and failure behavior |
| Safety | Env/feature flag, default-safe behavior, tenant boundary, no secrets in code/logs |
| Idempotency | Stable idempotency key or dedupe state; retry cannot duplicate customer-visible action |
| Reliability | Timeout, bounded retries, DLQ/fail record, never-raise wrapper for scheduled loops |
| Observability | Event/log/metric/heartbeat visible in existing admin/ops surface where relevant |
| Control | Kill-switch, rollback path, manual override, and operator-visible status |
| Verification | Unit/contract test for core path plus failure-path test or smoke command |
| Cost/quota | Free-stack provider chain, rate limit, quota pressure behavior, graceful fallback |
| Compliance | TRAI/DND/AI disclosure/DPDP/payment/auth gates stay fail-closed where required |
| Documentation | Update skill/runbook/memory only when future operators need it |

Automation design rule: prefer event-driven/idempotent jobs over cron-only polling; prefer small composable loops over hidden monoliths; every background job must be observable, retry-safe, and stoppable.

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
| Advancement council / ROI roadmap | `executive-council` (+ `docs/EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md`) |
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
