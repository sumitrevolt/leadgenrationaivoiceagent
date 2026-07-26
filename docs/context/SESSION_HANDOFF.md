# SESSION_HANDOFF - overwrite every session end

## Session objective
Turn the manual Cursor + Claude workflow into a policy-driven, evidence-backed mission system under Owner OS / OpenClaw.

## Outcome — External Agent Orchestrator (PR #146, commit `e4cebb1`, base `53b000d0`)
- New `app/dev_control/external_agents/` — mission schema + validated 23-state lifecycle, GREEN/AMBER/RED lanes (registry wins), CAS leases + heartbeat + stale-worker recovery, path/branch/worktree ownership, budgets/retries, Cursor + Claude adapters validated in code, rollback packages.
- OpenClaw: `external.missions`, `external.mission_status` — GREEN read-only only. No new STAFF; workforce still 31.
- Admin: `/api/dev-tasks/missions*` (existing router) + Missions card with filters in `frontend/dev_control.html`.
- Flag `EXTERNAL_AGENT_ORCHESTRATOR` registered in `AUTOMATION_FLAGS`, default OFF → API 503, OpenClaw `enabled:false`.
- ADR-148 + `docs/runbooks/EXTERNAL_AGENT_ORCHESTRATOR.md`.

## Evidence
- `pytest tests/test_external_agent_orchestrator.py -q` → 38 passed
- 5-suite regression (openclaw copilot, dev_control plane, dev_control claims, omniroute governance, new suite) → 132 passed, exit 0
- `scripts/prod_check.py` → ALL CHECKS PASSED (1211 routes, 0 collisions, dev-control invariants checked)
- `scripts/check_secrets.py` → clean; pre-commit detect-secrets/bandit/black/isort/ruff green
- Dogfood: real mission `msn_a1dc6423…` reached REVIEW_REQUIRED; `force merge…` probe refused RED
- Prod truth re-probed during session: `/health` = `f096a08d`, environment `production` (browser cache showed a stale `7cab5f60` — CLI is truth)

## Owner next
1. Watch PR #146 CI → mark ready → merge (GREEN work; no deploy implied)
2. **Decide branch protection:** `main` is currently NOT protected (gh api → 404) while `.github/workflows/auto-merge.yml` can enable auto-merge on a labelled PR. Exact `gh api -X PUT` command is in the runbook; agent did not execute it (AMBER).
3. Optional later: flip `EXTERNAL_AGENT_ORCHESTRATOR=1` in staging first (AMBER)

## Not done / blocked
- Claude Code CLI is installed (v2.1.207) but its OAuth session is expired → non-interactive Claude review mission could not run; independent review was performed by a separate Cursor reviewer agent instead. Re-auth `claude` to restore the Claude executor path.
- Browser GitHub settings verification needs an owner-signed-in session; branch-protection truth came from authenticated `gh` API instead.

## Out of scope (unchanged)
Calling HARD OFF (`PLATFORM_DIAL_DAILY=0`) · WA auto-send · Swara/voice · sales autopilot · any production deploy
