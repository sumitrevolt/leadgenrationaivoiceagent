---
type: Architecture
title: Knowledge stack (Hybrid Agentic RAG + OKF)
description: ADR-119 layered knowledge — OKF curated, Qdrant retrieval, Postgres truth, Graphify relations.
tags: [rag, okf, qdrant, architecture]
timestamp: 2026-08-05T00:00:00Z
resource: memory/decisions.md
---

# Knowledge stack

## Decision

**Hybrid Agentic RAG + OKF together.** OKF is never a Qdrant replacement.

```
User / Agent Query
        ↓
Query Router
        ├── Live customer data → PostgreSQL / APIs
        ├── Project rules/runbooks → OKF (knowledge/)
        ├── Documents/content → Qdrant Hybrid RAG
        └── Code/workflow relationships → Graphify
                                      ↓
                       Dense + Sparse → RRF → Reranker
                                      ↓
                       Top evidence + citations → LLM
```

## Components (target)

| Layer | Choice |
|---|---|
| Vector DB | Existing Qdrant `kb_main` |
| Retrieval | Dense + sparse/BM25 hybrid |
| Embedding (target) | BGE-M3 (Hinglish/multilingual; free/local) |
| Embedding (current prod) | `intfloat/multilingual-e5-small` via fastembed |
| Reranker (target) | BAAI/bge-reranker-base (flag OFF until bake+SLA) |
| Fusion | Reciprocal Rank Fusion |
| Knowledge format | OKF v0.1 draft (`knowledge/`) |
| Structured truth | PostgreSQL |
| Code graph | Graphify (`app/graphify-out/`) |
| Short-term memory | Redis TTL |
| Orchestration | FastAPI + free_ai (+ OmniRoute local-dev) |

## Phase-1 status (2026-08-05)

| Item | State |
|---|---|
| OKF scaffold `knowledge/` | SHIPPED |
| Public `/okf/` Markdown | CODE — `OKF_PUBLIC_BUNDLE` default ON |
| Ingest bridge → `kb_main` ns=`okf` | CODE — `OKF_INGEST_ENABLED` OFF default |
| Admin dry-run / status / recall | `/api/admin/okf/*` |
| Hybrid dense+sparse / BGE-M3 / reranker | NOT this slice (later flags) |

Modules: `app/platform/okf_bundle.py`, `app/platform/okf_ingest.py`.

## Tenant isolation (mandatory)

Every customer-scoped Qdrant retrieve must apply server-side `tenant_id` (and/or namespace) filter. Payload fields target: `tenant_id`, `document_type`, `visibility`, `status`, `source_id`, `version`.

OKF ingest uses **internal** namespace `okf` only — never customer `client:<id>` scopes.

## GraphRAG scope

Use Graphify for relationship questions only (agent↔workflow, deploy blast radius, OmniRoute impact). Not for FAQs/captions/support docs.
