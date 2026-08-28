# Swara / Voice — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Voice AI: architecture, telephony, call flow, prompts, states, failure codes, retries, compliance, QA, incidents.

## Authoritative sources (read these, not duplicates)
- CLAUDE.md ## 2 (voice stack) + landmines — canonical
- app/voice_agent/ + app/telephony/  — code
- knowledge/architecture/agent-os.md (Swara section, if any)
- voice_stack/                       — voice assets
- memory/incidents.md                — voice outage postmortems (872-event lesson)
- swara_enterprise.patch             — Voice AI pitch option
- docs/runbooks/RUNBOOK_PROVIDER_OUTAGE.md
- scripts/agent_tester.py            — voice scorecard
- FREEZE: Swara/voice code = FROZEN (edit mana) — read-only domain

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
