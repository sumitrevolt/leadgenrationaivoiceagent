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
4. Invokes **Cursor Agent CLI** via `node.exe` + `index.js` (never `agent.cmd`) with
   `--print --trust --workspace …` under redirected HOME/USERPROFILE profiles
5. Prefers worktree file `.external_agent_result_manifest.json` for the result
   contract; falls back to Cursor JSON envelope parse → `submit_result`
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

Credential boundary (deny-by-default): child processes receive only an explicit
OS scaffolding allowlist (`PATH`, `SYSTEMROOT`, locale, temp, and profile-dir
keys). There is **no** `CURSOR_*` / `CLAUDE_*` wildcard inheritance. Optional
exact `CURSOR_API_KEY` only when `EXTERNAL_AGENT_PASS_CURSOR_API_KEY=1`.

**Profile containment:** Cursor/Claude children get redirected
`HOME`/`USERPROFILE`/`APPDATA`/`LOCALAPPDATA`/`TEMP` under
`EXTERNAL_AGENT_PROFILE_ROOT` (default: `%TEMP%/leadgen_ext_agent_profiles`).
Claude receives only linked `.credentials.json` (+ optional `settings.json`) —
not projects/history/shell-snapshots. Cursor gets an empty `.cursor` home plus
writable `cursor-compile-cache` (agent binary stays absolute under real install).

**`--trust` decision: KEEP.** Required by Cursor Agent non-interactive print
mode. Containment is worktree + profile redirect + deny-by-default env + path
scope + pushurl disabled — not the `--trust` flag itself.

Claude read-only review disallows `Write,Edit,NotebookEdit,Bash`.

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
