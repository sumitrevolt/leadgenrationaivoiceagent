# Enterprise Documentation Index — LeadGenAI

> **Purpose:** Single map of the **minimum 10-doc enterprise pack** + supporting docs. Naya owner / investor / enterprise client ko yahi se start karo.
> **Live:** https://leadsgenai.in · **Repo:** github.com/sumitrevolt/leadgenrationaivoiceagent
> **Updated:** 2026-06-21 (SWARA handoff sync + marketing tier features)

---

## Minimum 10 (maintain these)

| # | Document | Path | Status |
|---|----------|------|--------|
| 1 | **PRD** | [`PRD.md`](PRD.md) | ✅ Lean PRD (features, flows, roadmap, priorities) |
| 2 | **Architecture** | [`ARCHITECTURE.md`](ARCHITECTURE.md) | ✅ System + deployment diagrams |
| 3 | **SOP** | [`PROJECT_SOP.md`](PROJECT_SOP.md) | ✅ Engineering + business procedures |
| 4 | **Runbook** | [`OPERATIONAL_RUNBOOKS.md`](OPERATIONAL_RUNBOOKS.md) | ✅ 12 incident playbooks (RB-001–012) |
| 5 | **Agent Registry** | [`AGENT_REGISTRY.md`](AGENT_REGISTRY.md) | ✅ AI staff roles, I/O, permissions |
| 6 | **Prompt Library** | [`PROMPT_LIBRARY.md`](PROMPT_LIBRARY.md) | ✅ Index → full prompts in `AGENT_SYSTEM_PROMPTS.md` |
| 7 | **API Docs** | [`API.md`](API.md) + live OpenAPI `/openapi.json` | ✅ REST reference (update base URL → leadsgenai.in) |
| 8 | **Handoff Package** | [`PROJECT_HANDOFF.md`](PROJECT_HANDOFF.md) | ✅ All-in-one takeover doc |
| 9 | **Client Onboarding Kit** | [`CLIENT_ONBOARDING_KIT.md`](CLIENT_ONBOARDING_KIT.md) | ✅ Setup guide + checklists |
| 10 | **Security Playbook** | [`SECURITY_PLAYBOOK.md`](SECURITY_PLAYBOOK.md) | ✅ Access, secrets, incident response |

---

## Strongly recommended (supporting)

| Document | Path | Covers |
|----------|------|--------|
| Disaster Recovery | [`DISASTER_RECOVERY.md`](DISASTER_RECOVERY.md) | Backup, RTO/RPO, failover |
| Workflow Maps | [`WORKFLOW_MAPS.md`](WORKFLOW_MAPS.md) | Lead → qualify → call → CRM → follow-up |
| KPI Dashboard Spec | [`KPI_DASHBOARD_SPEC.md`](KPI_DASHBOARD_SPEC.md) | Calls, leads, conversion, MRR |
| RACI Matrix | [`RACI_MATRIX.md`](RACI_MATRIX.md) | Human + AI staff accountability |
| Change Log | [`CHANGELOG.md`](CHANGELOG.md) | Releases, features, fixes |
| **Product Handoff + SOP** | [`PRODUCT_HANDOFF_SOP.md`](PRODUCT_HANDOFF_SOP.md) | Product-wise + automation map · mirrors [`/app/explorer`](https://leadsgenai.in/app/explorer) |
| **Swara Voice SOP** | [`SWARA_HANDOFF_SOP.md`](SWARA_HANDOFF_SOP.md) | Deep handoff + tune SOP + voice roadmap (Product 2 / Swara) |
| **AI Handoff** | [`AI_HANDOFF.md`](AI_HANDOFF.md) | Graphify-led session memory: changes, routes, DB/env, tests, pending |
| **Current AI State** | [`CURRENT_STATE.md`](CURRENT_STATE.md) | Short active sprint state for next AI session |
| **Next AI Actions** | [`NEXT_ACTIONS.md`](NEXT_ACTIONS.md) | Graphify-first task queue and end-of-session checklist |
| Activation Runbook | [`SESSION_ACTIVATION_RUNBOOK_2026_06_16.md`](SESSION_ACTIVATION_RUNBOOK_2026_06_16.md) | Env keys + go-live phases |
| **Executive Council prompt** | [`EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md`](EXECUTIVE_ADVANCEMENT_COUNCIL_PROMPT.md) | Strategic ROI roadmap · `/council-advancement` |
| Knowledge / troubleshooting | [`OPERATIONAL_RUNBOOKS.md`](OPERATIONAL_RUNBOOKS.md) + [`SESSION_LOG.md`](SESSION_LOG.md) | Incidents + dated history |

---

## Deep-dive (already exist — don't rebuild)

| Topic | Path |
|-------|------|
| Pricing ADR | `ADR_2026_06_11_Product_Split_Pricing.md` |
| Automation decision tree | `AUTOMATION.md` |
| RAG / agentic | `RAG_KnowledgeGraph_Agentic.md` |
| Dev repo graph (AI coding assistant only) | `GRAPHIFY.md` |
| Telephony plan (pending P3) | `superpowers/plans/PENDING_PLANS.md` |
| Infra hardening | `INFRA_HARDENING_GUIDE.md` |
| Production cutover | `PRODUCTION_CUTOVER.md` |
| Sales / marketing kits | `Sales_Kit_Hinglish.md`, `Marketing_Kit_LeadGenAI.md` |
| Competitor gaps | `Competitor_Top20_Feature_Gap_2026.md` |

---

## Maintenance rule

1. **Code change → update CHANGELOG + relevant doc section** (same PR when possible).
2. **New AI agent → AGENT_REGISTRY + PROMPT_LIBRARY + `app/platform/team.py` STAFF**.
3. **New API route → API.md one-liner OR rely on OpenAPI** (761 routes — OpenAPI = source of truth).
4. **Incident → OPERATIONAL_RUNBOOKS learnings append** (RB section footer).
5. **Quarterly:** PRD priorities sync with `PRIORITIZED_BACKLOG.md` + `CLAUDE.md`.
