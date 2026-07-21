# CURRENT_STATE - LeadGen AI (operational truth)

Evidence labels: PRODUCTION-PROVEN | CODE-PRESENT | TEST-PROVEN | LOCAL-ONLY | PARTIAL | STALE | UNKNOWN

## Last verified timestamp
2026-07-21T11:14Z (production deploy of 0ff5d06 verified; deploy-credential hardening prepared)

## Production SHA
`0ff5d06` (`0ff5d06c56ed0786bd47e1a364ce213ec9b96426`) - deployed and PRODUCTION-PROVEN.
Rollback target: `9c1bb308`. Deploy workflow run: `29823572772`. Image digest: `sha256:163e0a44...`.
Label: PRODUCTION-PROVEN

## Origin/main
`0ff5d06` == production. Includes PR #63 (CI baseline), PR #65 (OpenClaw Owner Copilot), PR #66 (governance/ops truth).
Label: CODE-PRESENT

## Production health
`/health` 200, `/health/ready` 200, environment `production`, restarts 0, no OOM, scheduler count 1,
celery/calling/DLQ queues 0. Uptime resets seen externally are uvicorn per-worker reporting (WEB_CONCURRENCY=2), not container restarts.
Label: PRODUCTION-PROVEN

## Migration
Live Alembic head: `022_add_request_depth`. (Note: `008` is NOT the head - it is one revision in the 008..022 chain.)
Label: PRODUCTION-PROVEN

## Routes
1163 registered, 0 route collisions (prod_check on the deployed release: ALL CHECKS PASSED).
Label: PRODUCTION-PROVEN

## OpenClaw
Source present on main; production flag OFF (`OPENCLAW_ENABLED` unset -> default 0, fail-closed). Owner OS is sole authority; RED lane refusal intact.
Label: CODE-PRESENT | PRODUCTION-PROVEN (OFF)

## Calling
HARD OFF. Voice agents `swara`/`ananya` remain RED lane. No dial job queued; calling queue empty. `DND_FAIL_OPEN=0` (fail-closed).
Label: PRODUCTION-PROVEN

## Deployment gate
`DEPLOY_ENABLED` unset (disarmed). No deployment workflow running.

## Deploy-credential hardening (in review, not merged/deployed)
PR #68 (`fix/deployment-credential-hardening-20260721`): dedicated `leadgen-deploy` identity + ed25519 key,
root-owned validated wrapper, GHCR_PAT eliminated (anonymous public pull). Old root-based secrets retained for rollback
until a proven run through the new path.
Label: CODE-PRESENT | TEST-PROVEN (non-destructive)

## Repository cleanliness
Main clone working tree has pre-existing local edits (jiya ledgers, `_ws4_ship/`) that are intentionally untracked/uncommitted and excluded from all work.

## Paying customers
1 - Jiya Makeover (`jiya-makeover`)

## Working customer workflows
- OpenClaw Owner Copilot - merged to main (PR #65), production flag OFF
- Delivery assurance / identity - unchanged

## Top next actions
1. Review deploy-credential hardening PR #68
2. After review, run one production deploy through the new hardened path (operator-gated), then retire old root/PAT secrets
3. Skill-tree de-duplication (PR #67 remains draft, Phase 11 inventory only) - separate later workstream
