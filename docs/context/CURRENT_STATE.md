# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN

## Last verified timestamp
2026-07-23T11:41Z (production running `510ed7bc`, verified via `/health` + `/health/ready`).

## Production SHA
`510ed7bc` (`510ed7bc1c7834892f81b9db092d1febb50dad48`) - deployed and PRODUCTION-PROVEN.
Deploy workflow run: `30002538121` (`deploy-vps.yml`, workflow_dispatch on `main`). Deploy status: successful; rollback: not used.
Full deployment evidence: `docs/context/PRODUCTION_DEPLOYMENT_RECORD_510ed7bc.md`.
Label: PRODUCTION-PROVEN

## Origin/main
`510ed7bc` == production. Video Review Stage 3 merged in PR #97; implementation commit `a4547e05`.
Label: CODE-PRESENT

## Production health
`/health` 200 and `/health/ready` 200 at exact `510ed7bc`; environment `production`.
All five app-image containers match the exact SHA, are running, and have restart count 0. Ready checks are green for database, redis, LLM configuration, disk, and memory.
Label: PRODUCTION-PROVEN

## Migration
The `510ed7bc` deploy completed its hard-gated transactional Alembic step successfully; this release introduced no migration.
(Note: `008` is NOT the head - it is one revision in the 008..022 chain.)
Label: PRODUCTION-PROVEN

## Routes
0 route collisions (prod_check on the deployed release: ALL CHECKS PASSED in the deploy gate on exact `510ed7bc`).
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
Label: PRODUCTION-PROVEN (run `30002538121`)

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
Source present on main; production flag OFF (`OPENCLAW_ENABLED` unset -> default 0, fail-closed). Owner OS is sole authority; RED lane refusal intact. Unchanged by the `510ed7bc` deploy.
Label: CODE-PRESENT | PRODUCTION-PROVEN (OFF)

## Calling
HARD OFF. Voice agents `swara`/`ananya` remain RED lane. `PLATFORM_DIAL_DAILY=0`; calling queue empty. Unchanged by the `510ed7bc` deploy.
Label: PRODUCTION-PROVEN

## Deployment gate
`DEPLOY_ENABLED=false` (disarmed). Deploy run `30002538121` is completed.

## Repository cleanliness
Main clone working tree has pre-existing local edits (jiya ledgers, `_ws4_ship/`) that are intentionally untracked/uncommitted and excluded from all work.

## Paying customers
1 - Jiya Makeover (`jiya-makeover`)

## Working customer workflows
- OpenClaw Owner Copilot - merged to main (PR #65), production flag OFF
- Delivery assurance / identity - unchanged
- Video Review Stage 3 code - deployed at `510ed7bc`; customer cohort gate remains OFF pending authenticated Jiya canary

## Top next actions
1. In the handed-off Admin Login tab, owner signs in; owner-managed runtime config enables only `VIDEO_CUSTOMER_REVIEW_ENABLED=1` and `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`.
2. Run one authenticated read-only Jiya Preview canary. Keep WhatsApp review, publish/social, daily video scheduler, WhatsApp auto-send, and platform dial OFF.
