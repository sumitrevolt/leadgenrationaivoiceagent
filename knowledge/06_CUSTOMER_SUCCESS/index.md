# Customer Success — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Onboarding, activation, delivery, feedback, escalation, renewal, customer isolation, support.

## Authoritative sources (read these, not duplicates)
- knowledge/operations/customer-onboarding.md
- docs/CLIENT_ONBOARDING_KIT.md
- docs/CUSTOMER_DELIVERY_AUTOMATION_2026_07_05.md
- CLAUDE.md ## 5 (tenant isolation invariant)
- memory/incidents.md                — Jiya delivery lessons

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
