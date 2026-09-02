# Owner Truth — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Canonical project truth: prod version, flags, kill switches, revenue, blockers, priorities, decisions, escalation.

## Authoritative sources (read these, not duplicates)
- ops/owner_truth.yaml            — MACHINE-READABLE canonical truth (read first)
- docs/context/CURRENT_STATE.md   — human narrative current state (auto-loaded)
- docs/context/ACTIVE_WORK.md     — active workstreams
- HERMES_AGENT_ROSTER.yaml        — 31 agents -> 9 Hermes bots
- _tasks_sync.json                — Kanban/task state (REV-xxx)
- memory/decisions.md             — append-only ADR archive

## Live truth routes (verify, don't trust chat claims)
- GET https://leadsgenai.in/health        -> .version == repo SHA
- GET /api/growth/infra/flags             -> runtime feature flags
- GET /api/ops/revenue-summary            -> revenue truth (MCP, admin+Bearer)
- GET /api/ops/hotqueue                   -> hot leads

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
