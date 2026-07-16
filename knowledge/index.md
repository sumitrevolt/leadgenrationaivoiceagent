---
okf_version: "0.1"
title: LeadGen AI Knowledge Bundle
description: Curated project knowledge in Open Knowledge Format v0.1 (draft). Not a retrieval runtime — Qdrant Hybrid RAG remains the large-scale search path (ADR-119).
timestamp: 2026-07-17T00:00:00Z
---

# LeadGen AI — OKF Knowledge Bundle

This directory is **canonical curated knowledge** (rules, runbooks, agent policy, ADRs summaries).

It is **not**:

- a vector database
- live customer/ledger truth (that is PostgreSQL/APIs)
- a Graphify replacement (code graph stays in `app/graphify-out/`)
- a place for secrets, tokens, passwords, or private phone numbers

## How agents should use this

| Question type | Source |
|---|---|
| Live counts, invoices, delivery status | PostgreSQL / APIs |
| Product rules, runbooks, agent policy | OKF files here (+ `memory/` deep archive) |
| Docs, FAQs, transcripts, approved content | Qdrant Hybrid RAG (`kb_main`) |
| Code/workflow “what depends on what” | Graphify |
| Short-lived chat/task state | Redis TTL |

## Bundle map

- [Product — Starter plan](product/starter-plan.md)
- [Product — Deliverables](product/deliverables.md)
- [Product — Pricing rules](product/pricing-rules.md)
- [Agents — Routing policy](agents/routing-policy.md)
- [Ops — Deployment](operations/deployment-runbook.md)
- [Ops — Incident response](operations/incident-response.md)
- [Ops — Customer onboarding](operations/customer-onboarding.md)
- [Architecture — Agent OS](architecture/agent-os.md)
- [Architecture — OmniRoute](architecture/omniroute.md)
- [Architecture — Tenant isolation](architecture/tenant-isolation.md)
- [Architecture — Knowledge stack](architecture/knowledge-stack.md)
- [Decisions index](decisions/index.md)

Deep history and full ADRs: repo `memory/decisions.md` (append-only). Code wins on conflict.
