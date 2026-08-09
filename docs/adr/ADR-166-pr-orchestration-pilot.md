# ADR-166 — Bounded PR-Orchestration Pilot (Bernstein-inspired, not Bernstein)

- **Date:** 2026-08-07
- **Status:** ACCEPTED (CODE-PRESENT; triple-gated, flags default OFF)
- **Extends:** ADR-163 (PR Factory Wave 1), ADR-148 (external orchestrator), ADR-155 (no vendor second OS), ADR-156 (PR Factory thin dispatcher)

## Context

We evaluated **Bernstein** (`sipyourdrink-ltd/bernstein`, Apache-2.0): a
deterministic CLI orchestrator for coding agents that creates per-task worktrees,
runs a continuous autofix daemon, and records an audit chain. Its discipline is
attractive, but adopting it wholesale conflicts with our own architecture rules:

- ADR-148/155: no **second control plane** — Bernstein is its own mission ledger + daemon.
- ADR-163: the repository already has a PR Factory spine (`tools/pr_factory/`) with
  task schema, budgets, worktree manager, CI-repair workflow, and a thin dispatcher.
- Owner OS (`app/dev_control/external_agents`) is the **sole** authority for GREEN/AMBER/RED,
  leases, and review separation.
- A running Bernstein daemon is a long-lived process we do not need on the VPS.

## Decision

Adopt **Outcome B: Bernstein-inspired safety rails built on the existing PR Factory**,
shipped as a new bounded orchestration pilot — **not** a vendored Bernstein copy, and
**not** a second control plane.

1. **New package:** `tools/pr_factory/pilot/` — a fail-closed, manifest-driven
   orchestrator that owns a single task branch and runs bounded repair/verify/cleanup.
2. **Triple-gate inert default** (all three must be `1` to run repair/diagnose/verify):
   - `PR_FACTORY_PILOT_ENABLED=1`
   - `PR_FACTORY_ENABLED=1`
   - `EXTERNAL_AGENT_ORCHESTRATOR=1`
   Production stays OFF. CLI refuses with exit code 3 (`flags_off`) when gated off.
3. **Safety rails (fail-closed, tested):**
   - `expected_head_sha` **pin required** for repair — empty/`PENDING` is refused;
     a moved remote head is a hard `head_sha_mismatch` refusal.
   - **Fresh CI only**: a check run bound to an older SHA never authorizes
     completion (`fresh_ci_required`).
   - **Attempt cap**: max 2 automated repair attempts per head SHA
     (`attempt_cap_exceeded`).
   - **Protected paths are never overridable** (same prefixes as
     `app/dev_control/external_agents/policy.py`): touching them = refusal.
   - **Manifest command allowlist**: pytest/ruff/scripts prefixes only, no shell
     metacharacters; executed via `sys.executable -m …` (no PATH dependence).
   - **Task-owned worktree only**; cleanup refuses any path that is not a registered
     worktree of this repo on the manifest task branch, and refuses dirty worktrees
     (never force-remove).
   - **No merge, no deploy**: `GitHubOps` and `Pilot` expose no merge/auto-merge/deploy
     surface; no network call while the per-task repository lock is held.
   - **Diagnosis-only mode** performs zero worktree/code/push mutation.
4. **Transient/infra retry first**: `gh run rerun --failed` for transient runs
   (bounded) before any code repair; classification distinguishes `code` vs `infra`.
5. **CLI:** `python -m tools.pr_factory.pilot.cli {validate,diagnose,repair,verify,cleanup}`
   with JSON manifest in/out and stable exit codes (0 ok, 1 refusal, 2 usage, 3 flags-off).

## Alternatives rejected

| Option | Why rejected |
|--------|--------------|
| Vendor `sipyourdrink-ltd/bernstein` | Second control plane + own ledger + running daemon; conflicts ADR-148/155 |
| Bernstein as "the" orchestrator above Owner OS | Owner OS is sole authority for risk class / leases / review |
| Run pilot unflagged in prod | Every automation switch is INERT-by-default, canary-only until proven |

## Consequences

- Docs: `docs/PR_ORCHESTRATION_PILOT.md` (runbook), this ADR, `docs/PR_FACTORY.md` updated.
- Flags: `PR_FACTORY_PILOT_ENABLED` registered in `app/api/automation_flags.py` +
  `app/platform/automation_flag_manifest.py` (default OFF).
- Tests: `tests/test_pr_factory_pilot.py`,
  `tests/test_pr_factory_pilot_manifest.py`,
  `tests/test_pr_factory_pilot_guard.py`,
  `tests/test_pr_factory_pilot_workflows.py` (regression guard on existing CI-repair workflow).
- No changes to `.github/workflows/ci.yml`, `deploy-vps.yml`, branch protection,
  or the existing read-only CI-repair workflow.

## Rollback

- Flags stay OFF (default) — pilot is inert without them.
- Remove `tools/pr_factory/pilot/` and the four test files if the pilot is not adopted.
- No workflow changes to revert; no daemon to stop; nothing in prod runtime touched.
