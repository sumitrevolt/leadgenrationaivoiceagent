# ADR-155 — desplega-ai/agent-swarm: NO full vendor; patterns-only harvest

- **Date:** 2026-08-04
- **Status:** ACCEPTED (evaluation-complete; no runtime merge)
- **Evaluated:** https://github.com/desplega-ai/agent-swarm (`@desplega.ai/agent-swarm` v1.127.1, MIT)
- **Local eval clone (outside product tree):** `C:\Users\Ratanshila\Documents\_agent_swarm_eval_2026-08-04`
- **Extends:** ADR-148 (external orchestrator ≠ second control plane), ADR-149 (runner ≠ Agent-OS),
  ADR-OPENCLAW-OWNER-COPILOT, ADR-154 (learn patterns / do not vendor foreign OS)

## Context

Owner asked whether agent-swarm is “best” for LeadGen enterprise grade, and whether to
full-clone or add features. agent-swarm is an **internal company coding/ops OS**: Bun + Hono
API, SQLite memory, Docker-isolated workers (Claude Code / Codex / OpenRouter / Devin),
Slack→PR lead/worker swarm. LeadGen is a **customer-facing FastAPI SaaS** with 31 STAFF,
Owner OS sole authority, Celery, free LLM chain, TRAI/DPDP fail-closed.

## Decision

**REJECT full clone / subtree / second runtime island.**

**ALLOW FEATURE_HARVEST only** — copy *ideas* (HITL DAG nodes, drain loops, litmus/judge
gates, persona packaging, compounding memory hygiene) into **existing** Owner OS / STAFF /
`dev_control` / workforce_memory surfaces. Reimplement in Python on Celery + Postgres +
Qdrant. Never import Bun/Hono/sqlite-vec swarm as a product dependency.

Workforce stays **31**. OpenClaw / Boss / Buzz / Coord Hub remain control/edge surfaces —
not a 32nd agent and not a parallel dispatcher.

## Alternatives rejected

1. **Vendor agent-swarm into `/opt/leadgen` or the monorepo** — second control plane,
   Bun+Docker worker tax, paid harness gravity (Anthropic/OpenAI/Codex), conflicts free-stack
   mandate and ADR-148/149.
2. **Replace Celery STAFF with swarm workers** — breaks scheduler kill guard, DLQ,
   `team.STAFF` contract, TRAI/DPDP calling/outreach gates.
3. **Run swarm as “enterprise layer” beside Owner OS** — dual authority = silent policy
   bypass (same class of failure ADR-148 was written to prevent).

## Enterprise requirements (ours — already the bar)

| Need | Canonical home (extend, don’t replace) |
|------|----------------------------------------|
| Action authority | `app/platform/owner_os.py` |
| Lanes GREEN/AMBER/RED | OpenClaw policies + `agent_registry` |
| 31 STAFF roster | `app/platform/team.py` |
| Durable jobs | `app/tasks/staff_jobs.py` + Celery + DLQ |
| Council decisions | `app/agents/llm_council.py` |
| External coding missions | `app/dev_control/external_agents/` (ADR-148) |
| Memory patterns | `workforce_memory` (ADR-154) + Qdrant |
| Compliance | DND fail-closed, consent, dial kill, WA ban gates |

## Consequence

- No Dependabot/npm Bun stack in production compose.
- Eval clone stays **outside** the product repo; delete anytime.
- If a swarm playbook pattern is wanted next, open a **flag-gated** Owner OS / STAFF /
  `dev_control` ticket — not a vendor PR.
- GTM 0→1 (2nd paid customer) remains higher priority than OS cosplay.

## Follow-up shipped (2026-08-04) — Owner OS Litmus harvest

- Code: `app/platform/owner_os_litmus.py` + wire in `parse_intent` / `execute_command`
- Flag: `OWNER_OS_LITMUS` (default **ON**; set `0` to bypass execute block; report still attaches)
- UI: Owner OS command preview shows Litmus PASS/FAIL
- Tests: `tests/test_owner_os_litmus.py`
- Still **not** vendoring agent-swarm runtime

## Rollback

N/A for reject — nothing swarm-runtime shipped.
Litmus rollback = `OWNER_OS_LITMUS=0` + recreate app (or revert commit).
