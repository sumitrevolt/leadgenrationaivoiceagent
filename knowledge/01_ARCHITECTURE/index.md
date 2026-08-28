# Architecture — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
System architecture: services, APIs, DBs, queues, Redis, providers, deployment, auth, tenant isolation.

## Authoritative sources (read these, not duplicates)
- CLAUDE.md ## 2 ARCHITECTURE MAP   — canonical stack map (auto-loaded)
- knowledge/architecture/agent-os.md
- knowledge/architecture/knowledge-stack.md
- knowledge/architecture/omniroute.md
- knowledge/architecture/tenant-isolation.md
- docs/ARCHITECTURE.md / docs/ARCHITECTURE_BLUEPRINT.md
- deploy/ + docker-compose.vps.yml  — container topology
- app/ (graphify-out/graph.json)    — code knowledge graph
- memory/integrations.md            — external deps, rate limits

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
