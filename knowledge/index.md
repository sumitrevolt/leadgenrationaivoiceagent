---
okf_version: "0.1"
title: LeadGen AI Knowledge Bundle
description: Curated project knowledge in Open Knowledge Format v0.1 (draft). Not a retrieval runtime — Qdrant Hybrid RAG remains the large-scale search path (ADR-119).
timestamp: 2026-08-05T00:00:00Z
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

## Runtime surfaces (Phase-1 polish, 2026-08-05)

| Surface | Path | Gate |
|---|---|---|
| Public agent-readable bundle | `GET /okf/` + `GET /okf/{path}` | `OKF_PUBLIC_BUNDLE` (default ON) |
| Admin status / dry-run / recall | `/api/admin/okf/*` | admin auth |
| Qdrant ingest (`namespace=okf`) | `POST /api/admin/okf/ingest` | `OKF_INGEST_ENABLED` OFF default |

Ingest is **not** auto-run on boot. Dry-run is always safe.

## Bundle map

- [Product — Starter plan](product/starter-plan.md)
- [Product — Deliverables](product/deliverables.md)
- [Product — Pricing rules](product/pricing-rules.md)
- [Product — Agency methods](product/agency-methods.md)
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
