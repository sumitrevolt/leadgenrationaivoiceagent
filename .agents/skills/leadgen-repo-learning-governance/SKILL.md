---
name: leadgen-repo-learning-governance
description: External open-source repos se SEEKHNE ka governance — pattern extract karo, copy mat karo. Use jab FastAPI-template, n8n, LangGraph, Temporal, Mautic, listmonk, Twenty CRM, Chatwoot, PostHog, Sentry, Grafana, Keycloak jaise repos study kar rahe ho bina incompatible code copy kiye ya duplicate architecture banaye.
---

# LeadGen Repo Learning Governance

> Enterprise audit skill. Open-source repos = TEACHERS, random code-donors nahi. Pattern extract → gap compare → sirf wahi implement jo existing LeadGenAI architecture me fit ho. Pehle `context-first`.

## Mission
Repos se pattern/data-model/test-strategy seekho; license-safe rakho; LeadGenAI-native (FastAPI/Celery/Postgres/Redis/Qdrant) plan me translate karo.

## Workflow
1. Learning goal define: workflow-reliability / CRM-model / marketing-journey / email-safety / observability / auth / testing.
2. Smallest relevant repo/reference chuno.
3. Extract: architecture pattern · data-model concept · test strategy · UI behavior · operational guardrails.
4. **License check** — AGPL/fair-code/proprietary se code COPY mat karo jab tak explicitly allowed+compatible. (Pattern seekhna OK; code lift nahi.)
5. Pattern ko LeadGenAI-native plan me translate (current stack reuse, duplicate architecture nahi).

## Repo pattern map
- FastAPI Full-Stack Template → structure, Docker, auth, tests, CI/CD.
- n8n → workflow execution, credentials, retries, run-history.
- LangGraph → stateful agents, human-approval, durable state.
- Temporal → durable execution, retries, idempotency.
- Mautic → campaigns, segments, lead-scoring, journeys.
- listmonk → email lists, campaign-safety, SMTP discipline.
- Twenty CRM → CRM objects, custom fields, permissions.
- Chatwoot → omnichannel inbox, support ops.
- PostHog → analytics, feature-flags, funnels, session-replay.
- Sentry/Grafana → errors, metrics, logs, dashboards, alerts.
- Keycloak → RBAC, SSO, identity architecture.

## Repo truth (existing learning system)
- Research docs: `docs/Automation_Marketing_Repos.md` · `docs/Architecture_Research_RAG_Agents_MCP.md` · `docs/RAG_KnowledgeGraph_Agentic.md`.
- **skill_pack** (`platform/skill_pack.py`, `SKILL_PACK=1`): 241 skills, `data/skills_extra/*.md` (data-only = git-pull pe live, NO rebuild).
- **code_upgrader** (Vikram, `CODE_UPGRADER=1`): signals → free-LLM patch PROPOSALS (`data/code_patches.jsonl` + admin approve) — core code KABHI auto-apply nahi.
- Memory: `CLAUDE.md` lean working-memory + `docs/SESSION_LOG.md` dated history. New learning → SESSION_LOG append, CLAUDE.md 1-2 line.

## Output
Pattern extraction note · license risk note · LeadGenAI gap mapping · native implementation plan + tests.

## Related repo skills (duplicate mat banao)
`memory-vault` (memory governance) · `self-improve-control` (improvement safety) · `migrate-to-skills` (skill authoring) · `using-superpowers` (skill system) · `leadgen-test-guardian` (native-plan tests).
