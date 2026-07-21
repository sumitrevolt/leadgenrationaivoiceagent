# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN

## Last verified timestamp
2026-07-21T14:04Z (production running `7ce4d97`, verified via `/health` + `/health/ready`).

## Production SHA
`7ce4d97` (`7ce4d979120da42cca9348320aae36640a2fdb27`) - deployed and PRODUCTION-PROVEN.
Rollback target: `0ff5d06` (`0ff5d06c56ed0786bd47e1a364ce213ec9b96426`).
Deploy workflow run: `29834863683` (deploy-vps.yml, workflow_dispatch on `main`). Deploy status: successful; rollback: not used.
Full deployment evidence: `PRODUCTION_DEPLOYMENT_RECORD_7ce4d97.md`.
Label: PRODUCTION-PROVEN

## Origin/main
`7ce4d97` == production. Recent merges: PR #68 (deployment-credential hardening), PR #69 (production-state docs), PR #70 (skill-tree consolidation / Phase 12).
Label: CODE-PRESENT

## Production health
`/health` 200, `/health/ready` 200, environment `production`, scheduler count 1, no mixed SHA, no OOM.
`/health/ready` checks green: database, redis, llm (gemini), disk, memory. Uptime resets seen externally are uvicorn
per-worker reporting (WEB_CONCURRENCY=2), not container restarts.
Label: PRODUCTION-PROVEN

## Migration
Live Alembic head: `022_add_request_depth`. The `7ce4d97` deploy ran `alembic upgrade head` as a no-op (already at head).
(Note: `008` is NOT the head - it is one revision in the 008..022 chain.)
Label: PRODUCTION-PROVEN

## Routes
0 route collisions (prod_check on the deployed release: ALL CHECKS PASSED in the deploy gate on exact `7ce4d97`).
Label: PRODUCTION-PROVEN

## Deployment architecture (hardened path - PRODUCTION-PROVEN)
The proven canonical deployment path is:

```
GitHub Actions
  -> leadgen-deploy (dedicated SSH user, VPS_DEPLOY_USER; NOT root, no docker group)
  -> VPS_SSH_KEY_DEPLOY (dedicated ed25519 key)
  -> root-owned /usr/local/sbin/leadgen-deploy-release wrapper (scoped NOPASSWD sudo, strict 40-hex SHA validation, flock)
  -> immutable exact-SHA anonymous GHCR pull (no docker login, no registry secret)
  -> docker compose (celery profile) up
  -> alembic upgrade head (hard-gated)
  -> /health/ready gate
  -> automatic rollback to the previously-running immutable image on migration or health failure
```

- The old root-based GitHub deploy path is retired. `GHCR_PAT` is retired; the registry package is public and pulled anonymously by exact SHA.
- The emergency root key is retained OUTSIDE GitHub (operator machine / VPS recovery) for break-glass only.
- `DEPLOY_ENABLED` defaults unset (off); a push to `main` runs the gate job only. Deploy requires operator-set `DEPLOY_ENABLED=true` + `workflow_dispatch`.
Label: PRODUCTION-PROVEN (run `29834863683`)

## Secret state (GitHub Actions)
Retained: `VPS_HOST`, `VPS_DEPLOY_USER`, `VPS_SSH_KEY_DEPLOY`.
Retired (deleted from GitHub Actions after the proven hardened run): `GHCR_PAT`, `VPS_USER`, `VPS_SSH_KEY`.
Emergency root key remains outside GitHub for operator recovery. (Names/state only; no values recorded.)
Label: PRODUCTION-PROVEN

## Skill architecture (canonical registry - PRODUCTION-PROVEN)
`.claude/skills` is the single canonical tracked skill root; `.agents/skills` is removed.
- Canonical project skills: `208`
- Additional/external skills (`data/skills_extra`, bind-mounted runtime source): `181`
- Runtime loader total: `389` = 208 project + 181 extra + 0 agents (all uniquely named; deterministic)
- Duplicate canonical skill IDs: `0`
- Decision record: ADR-131 (`docs/adr/ADR-131-canonical-skill-registry.md`).
- Duplicate-regression CI guard: `tests/test_skill_tree_canonical_guard.py`.
Label: PRODUCTION-PROVEN

## OpenClaw
Source present on main; production flag OFF (`OPENCLAW_ENABLED` unset -> default 0, fail-closed). Owner OS is sole authority; RED lane refusal intact. Unchanged by the `7ce4d97` deploy.
Label: CODE-PRESENT | PRODUCTION-PROVEN (OFF)

## Calling
HARD OFF. Voice agents `swara`/`ananya` remain RED lane. No dial job queued; calling queue empty. `DND_FAIL_OPEN=0` (fail-closed). Unchanged by the `7ce4d97` deploy.
Label: PRODUCTION-PROVEN

## Deployment gate
`DEPLOY_ENABLED` unset (disarmed). No deployment workflow running.

## Repository cleanliness
Main clone working tree has pre-existing local edits (jiya ledgers, `_ws4_ship/`) that are intentionally untracked/uncommitted and excluded from all work.

## Paying customers
1 - Jiya Makeover (`jiya-makeover`)

## Working customer workflows
- OpenClaw Owner Copilot - merged to main (PR #65), production flag OFF
- Delivery assurance / identity - unchanged

## Top next actions
1. Resume the next product/business execution workstream (e.g. Hot Queue -> second paying customer). No deployment is pending.
2. Any future deploy: operator-gated via the proven hardened path (set `DEPLOY_ENABLED=true`, dispatch `deploy-vps.yml`, then unset).
