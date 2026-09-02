# ADR-149 — External Agent Runner (unattended Cursor/Claude invocation)

- **Date:** 2026-07-27
- **Status:** Accepted for CODE-PRESENT dual-gate (2026-08-03 truth refresh) — **production flags remain OFF**. Runner is not a second Agent-OS.
- **Flags:** `EXTERNAL_AGENT_RUNNER` (default OFF) · requires `EXTERNAL_AGENT_ORCHESTRATOR=1`
- **Deployed/runtime:** CONFIGURED-INERT until owner arms both flags on an approved surface (Windows/local canary first). Orchestrator alone stays records/missions-only.

## Decision

Add a **separate** runner package under `app/dev_control/external_agents/runner/` that can invoke allowlisted Cursor Agent CLI and Claude Code CLI for GREEN missions only, without creating a second control plane, queue, or agent roster.

## Consequences

- Orchestrator remains records-only when runner is OFF.
- Runner cannot run if orchestrator is OFF.
- Production stays OFF; Windows/local canary is the first enablement surface.
- Cursor execution is assumed Windows-hosted; VPS coordinates missions via Redis/shared `./data`.

## Local dogfood proof (2026-07-27 — NOT production)

Continuous unattended slice via `scripts/dogfood_external_agent_runner.py`:

| Field | Value |
|-------|--------|
| Mission | `msn_b2a592093c484efa` |
| Executor | Cursor Agent CLI (`agent.cmd` `-p --print --trust --workspace`) |
| Reviewer | Claude Code CLI (`claude -p … --permission-mode plan`) |
| Branch / worktree | `feat/ext-dogfood-a061f8` / `lg-dogfood-a061f8` |
| Result | STATUS.txt = `RUNNER_DOGFOOD_OK` · `submit_result` → `REVIEW_REQUIRED` |
| Review | `PASS` via `submit_review()` → `REVIEW_PASSED` |
| Heartbeats | executor 1 · reviewer 4 |
| Prod flags | still OFF · `/health` = `f096a08d` · calling HARD OFF |

No merge of dogfood worktree. No deploy. Runner PR is a separate owner gate.
