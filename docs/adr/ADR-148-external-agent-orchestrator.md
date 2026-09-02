# ADR-148 — External Agent Orchestrator (Cursor + Claude missions)

- **Date:** 2026-07-26
- **Status:** ACCEPTED (code-present, INERT by default)
- **Flag:** `EXTERNAL_AGENT_ORCHESTRATOR` (default `0` = fully dormant)
- **Supersedes:** nothing. **Extends:** `app/dev_control` (ADR-era engineering
  control plane), OpenClaw Stage A observe surface, Owner OS authority model.

## Context

Cursor and Claude Code were being coordinated manually. There was no shared,
machine-checkable record of *who owns which files*, *which branch/worktree a
mission runs in*, *who reviewed what*, *what evidence exists*, or *where the
owner must decide*. The two failure modes we actually hit in this repo:

1. Parallel agents editing the same files (documented truncation/clobber
   landmine, `CLAUDE.md` §7) — no lock existed across agent sessions.
2. "Done" claims without evidence, and self-approval by the implementing agent.

The repo already has most of the primitives:

| Need | Existing asset (reused, not rebuilt) |
|------|--------------------------------------|
| Action authority | `app/platform/owner_os.py` |
| Copilot/orchestration edge | `app/integrations/openclaw/*` (GREEN/AMBER/RED lanes) |
| Engineering task ledger | `app/dev_control/*` (DevTask, claims, locks, budgets) |
| File ownership locks | `app/dev_control/locks.py` (Redis or in-memory) |
| Secret redaction | `openclaw/policies.redact_secrets` |
| Admin cockpit | `frontend/dev_control.html` |

## Decision

Add `app/dev_control/external_agents/` as an **extension** of the existing
control plane — not a second control plane, dispatcher, agent registry or
authority.

- `schema.py` — canonical `Mission` (mission_id, executor, reviewer, risk_class,
  allowed/prohibited paths, branch, worktree, base_sha, budgets, retry policy,
  lease, approval_state, rollback_plan, evidence_refs) + a validated 23-state
  lifecycle. `EXECUTOR_DRIVEN_STATES` makes self-completion structurally
  impossible.
- `policy.py` — regex risk lanes (GREEN/AMBER/RED), registry-wins classification
  (a caller may escalate, never de-escalate), always-prohibited protected paths
  (`app/voice_agent/`, `app/telephony/`, `app/billing/`, `.env`,
  `alembic/versions`, deploy workflows, `docker-compose.vps.yml`), path/branch/
  worktree overlap detection, budget and retry checks.
- `store.py` — atomic per-mission JSON + append-only redacted `events.jsonl`
  (mirrors `delivery_ledger`; no new dependency). Compare-and-set lease claim,
  owner-only heartbeat, stale-worker recovery.
- `adapters.py` — `CursorAdapter` (engineering executor; requires branch +
  worktree + changed files + green tests) and `ClaudeAdapter` (admin/review;
  verdict must be PASS/CHANGES_REQUIRED/BLOCKED **with citations**, cannot
  approve its own work). Adapters build bounded packets and validate result
  manifests **in code** — an LLM assertion alone never advances a mission.
- `orchestrator.py` — the only place state changes; GREEN auto-progresses
  through PR/CI/merge, AMBER parks at `OWNER_DECISION_REQUIRED`, RED is refused
  at creation, merge/complete require evidence completeness.

Surfaces:

- Admin API: `/api/dev-tasks/missions*` on the **existing** dev-tasks router
  (`require_admin`, separate 503 gate on `EXTERNAL_AGENT_ORCHESTRATOR`).
- OpenClaw: two **GREEN read-only** commands `external.missions`,
  `external.mission_status`. No new STAFF persona; workforce stays 31 agents.
- Cockpit: a Missions card inside the existing `frontend/dev_control.html`.

## Consequences

- Nothing runs until an operator sets `EXTERNAL_AGENT_ORCHESTRATOR=1`.
- The orchestrator has **no** shell, git, deploy, calling, billing or send path.
  It records missions and evidence; humans/agents execute in their own sessions.
- Calling stays HARD OFF (`PLATFORM_DIAL_DAILY=0`); a test asserts the package
  contains no dial flag, `subprocess`, `os.system` or docker string.
- Rollback = unset the flag (surface returns 503, OpenClaw commands report
  `enabled:false`), or revert the squash merge.

## Alternatives rejected

- **New standalone orchestrator service** — would create a second authority and
  duplicate leases/locks/audit. Rejected by the repo's own invariant.
- **DB table for missions** — `dev_tasks` already exists for the durable ledger;
  a migration for a still-dormant coordination layer adds prod risk for no
  current benefit. JSON+JSONL matches `delivery_ledger` precedent and is
  swappable later behind the same `store` API.
- **Letting agents self-report COMPLETE** — rejected; review separation and
  evidence gates are the entire point.

## Open items (owner decisions, NOT taken here)

1. Optional ruleset hardening (add `test` + GitGuardian contexts, conversation
   resolution) — package in `docs/runbooks/BRANCH_PROTECTION_AMBER_PACKAGE.md`.
   Note: classic branch-protection API returns 404, but ruleset `19718692` is
   already active with three required checks. Do not claim "no floor".
2. Flag flip in production (AMBER).
3. Claude Code OAuth re-auth on the operator machine (required before a real
   Claude dual-agent proof can be recorded).

## Closure note (2026-07-26)

CAS moved from process-local mutex to Redis-or-portalocker (see runbook §4).
Path identity no longer uses `lstrip("./")`. Multiprocess tests added.
Automation boundary remains "foundation", not unattended invocation.
