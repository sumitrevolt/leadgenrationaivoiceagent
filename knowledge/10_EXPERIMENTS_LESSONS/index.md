# Experiments & Lessons — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Experiments, hypotheses, results, failed approaches, benchmarks, lessons, accepted/rejected decisions.

## Authoritative sources (read these, not duplicates)
- memory/backlog.md                 — parked ideas with why
- memory/decisions.md               — ADR archive (append-only)
- evals/ + eval results             — benchmarks
- docs/ADVANCEMENT_ROADMAP_2026.md
- knowledge/decisions/              — ADR summaries (adr-119, index)
- docs/archived/                    — rejected/rolled-back artifacts

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
