# Engineering — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Coding standards, testing protocol, CI/CD, merge policy, rollback, observability, change management.

## Authoritative sources (read these, not duplicates)
- CLAUDE.md ## 3-6 (COMMANDS/CODE STANDARDS/TESTING PROTOCOL) — canonical
- docs/AGENT_WORK_RULES.md          — 10 anti-mistake rules
- docs/LOOP_ENGINEER.md             — loop-engineer mode spec
- docs/context/AI_OPERATING_PROTOCOL.md
- docs/ADR-104_DEPLOY_RUNBOOK.md
- scripts/prod_check.py             — verify gate
- scripts/check_secrets.py          — secrets scan
- progress.md                       — loop ledger

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
