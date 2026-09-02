# Marketing & Video — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Video generation, content pipeline, approvals, social publishing, asset generation, customer templates, brand constraints.

## Authoritative sources (read these, not duplicates)
- video_renderer/                    — video pipeline
- docs/runbooks/RUNBOOK_DAILY_VIDEO.md
- ADRs: ADR-142 VIDEO DECISIONS (reject terminal / only Changes revises)
- docs/brand/ (brand constraints)
- frontend/ marketing pages           — 28-tab marketing.html
- memory/backlog.md                  — parked video ideas
- Pollinations (AI images/video)     — provider

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
