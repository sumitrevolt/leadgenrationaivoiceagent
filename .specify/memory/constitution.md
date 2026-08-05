<!--
Sync Impact Report
- Version change: (none) → 1.0.0
- Modified principles: n/a (initial LeadGen ratification)
- Added sections: all
- Removed sections: none
- Follow-up TODOs: none
-->

# LeadGen AI — Spec Kit Constitution

**Constitution Version:** 1.0.0
**Ratification Date:** 2026-08-05
**Last Amended:** 2026-08-05
**Authority:** Owner OS + `EXTERNAL_AGENT_ORCHESTRATOR` (ADR-148 / ADR-156)
**Spec Kit pin:** `v0.15.2` (see `.specify/PIN.md`)

## Purpose

This constitution binds every Spec Kit–shaped task and every PR Factory mission.
It does **not** create a second control plane. Coding missions execute only through
existing `app/dev_control/external_agents` (create → claim → review separation → PR/CI).

## Principle I — One Fix, Zero Regressions

Every task MUST state a single primary fix or feature. Expanding scope mid-mission
is REFUSED. Known-adjacent bugs become new tasks with new idempotency keys.
Shipping with failing targeted tests or weakened compliance gates is FORBIDDEN.

## Principle II — Graphify Before Broad Edits

Non-trivial edits MUST map impact (callers/callees/routes/tests) via Graphify or
an equivalent bounded grep/Read pass **before** writing code. Broad repo-wide
rewrites without an impact map are REFUSED.

## Principle III — One Task, One Owner, One Worktree

One atomic task YAML → one mission → one executor → one dedicated worktree/branch.
Path ownership conflicts cancel the loser. Parallel agents MUST NOT share a
worktree or claim overlapping `allowed_paths`.

## Principle IV — Acceptance Criteria Before Coding

`acceptance_criteria` and `required_tests` MUST be non-empty before `CLAIMED` /
runner start. "Looks good" is not acceptance. Fake completion (stubbed proof,
skipped tests presented as green) is REFUSED.

## Principle V — Protected Paths (mirror policy.PROTECTED_*)

Missions MUST NOT own or mutate these prefixes (fail-closed, mirrors
`app/dev_control/external_agents/policy.py`):

- `.env` (and `.env*`)
- `.github/workflows/deploy*`
- `alembic/versions`
- `app/billing/`
- `app/telephony/`
- `app/voice_agent/`
- `data/voice_gemini_keys.json`
- `docker-compose.vps.yml`

RED intent patterns (secrets, TRAI/DND disable, cold WhatsApp blast, prod flag
flips, deploy from factory) are refused at `create_mission`.

## Principle VI — Mandatory Targeted Tests + Evidence

Every GREEN/AMBER implementation mission MUST run its `required_tests` and attach
evidence (commands, exit codes, summaries). Public revenue/pricing routes need
contract tests. Absence of errors ≠ proof — cite exit codes and `/health` when
claiming production state.

## Principle VII — Rollback + Checkpoint

Every task MUST include a non-empty `rollback_plan` (usually `git revert` of the
squash merge). Long-running work MUST heartbeat the mission lease; stuck leases
use the recovery playbook (`tools/pr_factory/recovery.py` hooks).

## Principle VIII — No Fake Completion

Do not claim "done", "LIVE", or "deployed" without Definition-of-Done evidence:
targeted pytest green, `scripts/prod_check.py` PASS when app code touched, and
for production claims: `/health.version` equality. Placeholders behind explicit
INERT flags are allowed; lying about them is not.

## Principle IX — Production Evidence for Deploy Claims

Deploy remains Owner-gated (`deploy_vps.sh` / `DEPLOY_ENABLED`). PR Factory and
CI-repair Actions MUST NOT hold prod SSH, billing envs, or deploy secrets.
`PR_FACTORY_ENABLED` and `EXTERNAL_AGENT_*` default OFF in production.

## Principle X — Executor ≠ Reviewer

The executor agent MUST differ from the reviewer agent. Same-tool self-review is
REFUSED. Independent review precedes merge-label application.

## Governance

1. **Amendment:** Owner-approved PR updating this file + ADR-156 note; bump
   `CONSTITUTION_VERSION` (MAJOR for removals/redefinitions, MINOR for new
   principles, PATCH for clarifications).
2. **Compliance review:** Wave kickoffs and ADR-148/156 changes MUST re-read
   this constitution.
3. **Conflict:** If this file conflicts with live code policy in
   `external_agents/policy.py`, **code wins** — then amend the constitution.
4. **Prohibited stack (primary orchestrators):** Do not adopt Vibe Kanban,
   Parallel Code as primary orchestrator, or "awesome-orchestrators" as a
   product dependency. Symphony is **spec inspiration only** — implement under
   `tools/pr_factory/`, do not vendor `openai/symphony`.
