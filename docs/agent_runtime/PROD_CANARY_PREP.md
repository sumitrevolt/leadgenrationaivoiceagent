# Production canary prep — PR #72 (NOT EXECUTED)

Date: 2026-07-21
Status: **BLOCKED — OWNER AUTHORIZATION REQUIRED** for merge/deploy/canary arm.

## Drift

- Class: `SAFE_BEHIND_DOCS_ONLY`
- Prod runtime: `7ce4d979`
- origin/main: `10a3996a` (docs-only ahead)
- PR head: `676c51a`

## Rollback target (if owner later deploys)

- Previous image tag: `7ce4d979120da42cca9348320aae36640a2fdb27`
- Previous `/health.version`: same
- Alembic head (unchanged expected): `022_add_request_depth`
- Flag restore: unset/`0` for `AGENT_RUNTIME`, `SRE_AGENT` if flipped for canary
  (note: prod currently already has both `=1` on **old** image)

## Owner-gated command sequence (DO NOT RUN until auth)

```text
1. gh pr ready 72
2. gh pr merge 72 --merge   # or --squash per house style
3. git fetch origin main && export APP_VERSION=$(git rev-parse origin/main)
4. VPS: git fetch + ff-only main (no reset --hard); APP_VERSION=<full sha>
5. setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
6. Prove /health.version == APP_VERSION; flags OFF first if policy requires
7. Disabled-state proof → arm only AGENT_RUNTIME=1 SRE_AGENT=1
8. Owner OS single Pranav run + Redis idempotency + controls + rollback
```

## What was completed without auth

- PR #72 CI green on latest HEAD
- Drift classification with VPS read-only inspect
- Local Pranav canary (prior)
- Truth matrix / handoff updated
