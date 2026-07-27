# Runbook — External Agent Runner (unattended Cursor/Claude slice)

Flags (both required, both default OFF):

- `EXTERNAL_AGENT_ORCHESTRATOR=1`
- `EXTERNAL_AGENT_RUNNER=1`

ADR: ADR-148 (orchestrator foundation) · this slice = runner v1.

## What it does

Local/Windows canary that, for one GREEN mission:

1. Checks eligibility + Owner OS-style GREEN authorization evidence
2. Allocates/verifies dedicated branch + worktree under `EXTERNAL_AGENT_WORKTREE_ROOT`
3. Claims lease, starts mission, emits heartbeats
4. Invokes **Cursor Agent CLI** (`agent -p --print --trust --workspace …`)
5. Validates result manifest → `submit_result`
6. Invokes **Claude Code CLI** read-only review → `submit_review`
7. Stops at PR/CI / owner-decision boundaries (does not merge/deploy)

## What it does NOT do

- Production deploy
- Enable calling / billing / outreach
- Run inside VPS containers (Cursor desktop stays Windows-hosted)
- Arbitrary shell / executable override
- Auto-open OAuth

## Local canary

```bat
set EXTERNAL_AGENT_ORCHESTRATOR=1
set EXTERNAL_AGENT_RUNNER=1
set EXTERNAL_MISSION_DIR=%TEMP%\ext_missions
set EXTERNAL_MISSION_CAS=filelock
set EXTERNAL_AGENT_WORKTREE_ROOT=C:\Users\Ratanshila\Documents\_leadgen_worktrees
.venv\Scripts\python.exe scripts\external_agent_runner.py --mission-id msn_...
```

Credential boundary: child processes inherit only an allowlisted env plus `CURSOR_*` /
`CLAUDE_*` (including `CURSOR_API_KEY` when set). Prefer short-lived operator tokens;
never bake secrets into images.

Admin: `/dev-control` missions card shows runner ENABLED/OFF badge.

API: `POST /api/dev-tasks/missions/{id}/run-runner` (admin, dual-flag gated).

## Deployment-readiness package (NOT executed)

| Item | Truth |
|------|--------|
| Host split | VPS = mission store + Redis CAS + admin UI; Windows = Cursor Agent + Claude Code executors |
| Credentials | Claude OAuth on Windows operator; Cursor Agent login / `CURSOR_API_KEY`; never bake into image |
| Flags | Orchestrator OFF · Runner OFF · `DEPLOY_ENABLED=false` until separate owner auth |
| Limits | timeout 900s · output 512KiB · heartbeat 25s · GREEN only |
| Kill switch | unset `EXTERNAL_AGENT_RUNNER` (and/or orchestrator) |
| Canary | Windows local first → observe 1 dogfood mission → then consider VPS coord-only deploy of code |
| Rollback | unset flags; cancel mission; remove worktree |

## Dogfood evidence (local only)

- Mission `msn_b2a592093c484efa` → `REVIEW_PASSED` (Cursor implement + Claude review)
- Artifact: `tests/fixtures/external_agent_runner/STATUS.txt` = `RUNNER_DOGFOOD_OK`
- Worktree `lg-dogfood-a061f8` (do not merge)

## Owner gates remaining

1. Merge runner PR
2. Deploy code (still flag OFF)
3. Windows/local canary enablement
4. Production orchestrator enablement
5. Production runner enablement
