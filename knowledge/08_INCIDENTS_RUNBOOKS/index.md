# Incidents & Runbooks — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Incident taxonomy, previous incidents, symptoms, root causes, fixes, validation, rollback, prevention.

## Authoritative sources (read these, not duplicates)
- memory/incidents.md               — postmortem archive (authoritative)
- docs/runbooks/                    — 9+ runbooks (RB-xxx)
- docs/OPERATIONAL_RUNBOOKS.md      — RB-001..013 quick reference
- docs/runbooks/RUNBOOK_BILLING_INCIDENT.md
- ops/runbooks/                     — normalized registry (THIS upgrade)
- docs/SECURITY_PLAYBOOK.md

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
