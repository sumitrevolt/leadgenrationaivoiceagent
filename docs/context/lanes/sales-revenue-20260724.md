# LANE — Sales & Revenue Ops (parallel, non-shared)

> Lane-owned handoff. Do NOT edit shared `SESSION_HANDOFF.md` / `ACTIVE_WORK.md`
> (owned by another active session / PR #116). This file is the only coordination
> surface for this lane.

## Branch
`admin/sales-revenue-parallel-hotqueue`

## Worktree path
`C:/Users/Ratanshila/Documents/_leadgen_worktrees/lg-sales-revenue` (from `origin/main` @ `9752157`)

## Current atomic objective
Wire the dormant `app/billing/entitlement_assurance.py` revenue-leak detector
(paid-no-invoice / invoice-vs-subscription mismatch / unknown-plan / entitlement
drift) to a reachable admin API route, mirroring the already-wired sibling
`/api/admin/delivery-assurance`. Detection existed but had ZERO callers outside
its own module/test → Revenue Ops could not see it. Read-only, never-500.

## Files owned (this lane only)
- `app/api/admin_dashboard.py` (additive: one new GET route)
- `tests/test_admin_entitlement_assurance_route.py` (NEW file)
- `docs/context/lanes/sales-revenue-20260724.md` (this manifest)

## Files EXCLUDED / NO_TOUCH
- ALL `.github/**`, CI/CD, deploy, release automation (PR #120 + infra lane)
- `tests/conftest.py` (PR #120)
- PR #116 (creative-os) committed + uncommitted: `app/api/clientops.py`,
  `app/api/customer_dashboard.py`, `app/api/automation_flags.py`,
  `app/marketing/creative_os/**`, `app/marketing/video_pipeline.py`,
  `app/tasks/video_jobs.py`, `app/worker.py`, `frontend/admin_dashboard.html`,
  `frontend/automation.html`, `memory/decisions.md`,
  `docs/context/SESSION_HANDOFF.md`, `tests/test_creative_os.py`,
  `tests/test_celery_queue_routing.py`
- PR #114: `app/integrations/openclaw/commands.py`, `app/platform/owner_os.py`
- PR #113: omniroute governor files
- `.env`, secrets, requirements*.txt (dependabot PRs #64/#42/#40/#39/#38)
- Jiya ledger JSONL (regression baseline — read-only)

## Overlapping agents / PRs
- PR #120 `fix/ci-aiosqlite-nullpool-20260724` — CI (infra lane) — NO overlap
- PR #116 `feat/creative-automation-os` — touches admin surfaces but NOT
  `app/api/admin_dashboard.py` → NO overlap with owned files
- PR #114 openclaw — NO overlap

## Protected behavior (must not regress)
Jiya Makeover (`jiya-makeover` / alias `d79d690f61b3`, Starter ₹1,999),
tenant isolation, billing truth (Rule-46 immutable ledger), payment idempotency,
activation, approvals, admin auth, calling HARD OFF (`PLATFORM_DIAL_DAILY=0`),
agent schedules.

## Tests required
- `pytest tests/test_admin_entitlement_assurance_route.py`
- `pytest tests/test_entitlement_assurance.py` (regression — module unchanged)
- `python scripts/prod_check.py`
- `python scripts/check_secrets.py`

## Rollback command
`git -C <worktree> revert <commit>`  (single additive commit; route + test only)

## Deferred (collision-blocked)
Admin UI card for entitlement-assurance belongs in `frontend/admin_dashboard.html`
which is owned by PR #116 — deferred to that lane / a follow-up once #116 merges.
API is live + testable now; sibling delivery-assurance card is the copy template.
