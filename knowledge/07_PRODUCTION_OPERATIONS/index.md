# Production Operations — Knowledge Domain Index

> LAYER B Agentic Notebook. This index is a **normalized pointer layer**: it maps
> the domain to authoritative existing sources. Live truth lives in code/APIs/DB
> (see Owner Truth); deep archives live in `memory/`; dated docs in `docs/`.
> Updated: 2026-08-28

## What this domain covers
Deployments, VPS, containers, health checks, backups, DR, monitoring, release procedures.

## Authoritative sources (read these, not duplicates)
- CLAUDE.md ## 3 (BUILD+DEPLOY canonical) — deploy_vps.sh ONLY
- docs/ADR-104_DEPLOY_RUNBOOK.md
- knowledge/operations/deployment-runbook.md
- docs/DISASTER_RECOVERY.md
- docs/omniroute/OPERATIONS_RUNBOOK.md
- docs/COMPOSE_GUIDE.md
- deploy/ (compose + scripts)
- monitoring/ (Prometheus/Grafana/Alertmanager/Loki/Tempo obs stack)
- scripts/vps_selfheal.sh            — */10 self-heal cron
- memory/playbooks.md               — deploy/rollback/rotate procedures

## Live truth routes (verify, don't trust chat claims)
- (none — see 00_OWNER_TRUTH)

## Recall rules
- Secrets NEVER live in knowledge files — reference env var NAMES only (SECRET_REF).
- If code and this index disagree, **code wins** — then fix this index.
- Freshness: `last_verified_at` should be bumped whenever this domain is re-verified.
