# PR Factory (Wave 1)

**Status:** CODE-PRESENT · flags default OFF · ADR-163 · ADR-166
**Branch intent:** factory spine only — honest target after enablement = **10–20 verified PRs per wave**, not “100 PRs in hours.”

## Stack (locked)

| Layer | Choice |
|-------|--------|
| Spec compiler | `github/spec-kit` **pinned `v0.15.2`** — `.specify/PIN.md` + `scripts/setup_spec_kit.ps1` |
| Execution | Symphony **spec only** → `tools/pr_factory/` (do **not** vendor `openai/symphony`) |
| Coding workers | Existing Claude/Cursor runners under `app/dev_control/external_agents/runner/` |
| GitHub CI repair | `.github/workflows/pr-factory-ci-repair.yml` — Wave 1 **read-only diagnosis** (`workflow_dispatch` only; `contents: read`; no coding-agent write). Code repair deferred until mission-bound Wave 3+ |
| Safety authority | Owner OS + `EXTERNAL_AGENT_ORCHESTRATOR` / `EXTERNAL_AGENT_RUNNER` — **not replaced** |
| Merge | Existing `.github/workflows/auto-merge.yml` label train |
| Deploy | Unchanged: Owner-gated `deploy_vps.sh` / `DEPLOY_ENABLED` |

## Wave model

- Up to **8** implementation missions + **2** independent reviewers per wave (see `tools/pr_factory/budgets.py`).
- Concurrency caps: 4 Claude / 4 Cursor / 2 reviewers / 1 CI repair / 1 merge coord.
- Deploy lane stays Owner OS only (never factory-owned).

## Flags (fail-closed)

| Flag | Default | Notes |
|------|---------|-------|
| `PR_FACTORY_ENABLED` | `0` | Factory CLI inert unless also `EXTERNAL_AGENT_ORCHESTRATOR=1` |
| `PR_FACTORY_PILOT_ENABLED` | `0` | Bounded PR-orchestration pilot (ADR-166); requires `PR_FACTORY_ENABLED` + `EXTERNAL_AGENT_ORCHESTRATOR` too — see `docs/PR_ORCHESTRATION_PILOT.md` |
| `EXTERNAL_AGENT_ORCHESTRATOR` | `0` | Canonical mission ledger |
| `EXTERNAL_AGENT_RUNNER` | `0` | Dual-gate for real CLI invocation |

**Do not enable in production in Wave 1.**

## Prohibited as primary orchestrators

- Vibe Kanban
- Parallel Code as primary
- “awesome-orchestrators” style dependency harvest as product control plane
- Vendoring `openai/symphony`
- claw-orchestrator as a second Owner OS (deferred patterns-only; see ADR-172)

## Related coding plane (not a factory replacement)

Interactive Claude Code parallel work uses **native Agent Teams + worktrees**
(ADR-172, `docs/runbooks/CLAUDE_AGENT_TEAMS.md`). That plane does not own missions;
PR Factory remains the only TaskYAML → `create_mission` path.

## Install Spec Kit (dev only)

```powershell
.\scripts\setup_spec_kit.ps1
```

Constitution: `.specify/memory/constitution.md`.

## Dispatcher entry

```text
tools/pr_factory/orchestrator.py   # ONLY entry: TaskYAML -> create_mission / advance
```

Never invent a second mission store — always call `app.dev_control.external_agents.orchestrator`.

## CI

- **Gate A** (non-required): `.github/workflows/pr-factory-gate-a.yml` — ruff/format on changed paths, secrets scan, path-policy stub, optional targeted pytest from task manifest.
- **CI repair** (Wave 1): `.github/workflows/pr-factory-ci-repair.yml` — `workflow_dispatch` only, read-only diagnosis comment. No `issue_comment` trigger, no `contents: write`, no coding-agent push. Checkout pinned to `actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1` (v7.0.1).
- Gate B/C + `merge_group` = Wave 2+ (not built here).
- Native GitHub Merge Queue = after org migration (Wave 4).

## Follow-on waves (documented only)

1. **Wave 2:** live issue→task intake, dependency graph, wave scheduler, Gate B required on path filters
2. **Wave 3:** CI repair loop wired to Action + merge_train dry-run
3. **Wave 4:** org Merge Queue + `merge_group` triggers

## Orchestration pilot (ADR-166)

A bounded, fail-closed repair/verify/cleanup orchestrator (Bernstein-inspired,
**not** vendored Bernstein) ships alongside the factory spine:
`tools/pr_factory/pilot/`. Triple-gated (`PR_FACTORY_PILOT_ENABLED` +
`PR_FACTORY_ENABLED` + `EXTERNAL_AGENT_ORCHESTRATOR`), never merges/deploys,
pins the head SHA, requires fresh CI, caps repair attempts, and owns exactly one
task worktree. Runbook: `docs/PR_ORCHESTRATION_PILOT.md`.

## Runbooks

- External agents: `docs/runbooks/EXTERNAL_AGENT_ORCHESTRATOR.md`
- Workflow notes: `tools/pr_factory/WORKFLOW.md`
