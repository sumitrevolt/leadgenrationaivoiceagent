# Sales & Revenue — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
ICP, lead sourcing, qualification, outreach (WA/email/call), follow-ups, payments, close workflow, CRM, revenue verification.

## Authoritative sources (read these, not duplicates)
- docs/GTM_PILOT_PLAYBOOK.md
- docs/Agentic_Customer_Acquisition_Playbook.md
- docs/LEAD_MAGNET_PLAYBOOK.md
- docs/playbooks/Business_Playbook_Hinglish.md
- DAY_0_REVENUE_BASELINE.md / 7_DAY_REVENUE_PLAN.md / REVENUE_BLOCKERS.md
- ops/owner_truth.yaml (revenue section) — canonical revenue truth
- app/billing/packages.py            — pricing single source
- memory/decisions.md                — billing/UPI decisions
- data/hot_queue_*.csv/md            — daily hot-lead packs
- docs/runbooks/RUNBOOK_DUPLICATE_OUTREACH.md / RUNBOOK_BILLING_INCIDENT.md

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
