# Providers / APIs / MCP — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Provider inventory, credential references, API contracts, quotas, limits, auth, costs, fallbacks, MCP capabilities.

## Authoritative sources (read these, not duplicates)
- memory/integrations.md            — per-provider purpose/limits/failure modes (authoritative)
- ops/owner_truth.yaml (providers section)
- docs/API.md                        — route inventory (~1295+ routes)
- docs/CONTEXT_MCP.md               — MCP wiring
- knowledge/architecture/omniroute.md
- .mcp.json                         — graphify-mcp + leadgen MCP (54 tools)
- SECRET_REF convention: secrets NEVER in docs — env vars only (.env)

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
