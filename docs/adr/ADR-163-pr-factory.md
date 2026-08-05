# ADR-163 — PR Factory Wave 1 (Spec Kit + native dispatcher)

- **Date:** 2026-08-05
- **Status:** ACCEPTED (Wave 1 CODE-PRESENT; flags default OFF)
- **Extends:** ADR-148 (external orchestrator), ADR-149 (runner), ADR-155 (no vendor second OS)

## Context

We need higher verified PR throughput without inventing a second control plane or
vendoring foreign orchestrators (`openai/symphony`, Vibe Kanban, Parallel Code as
primary). Owner OS + `app/dev_control/external_agents` already provide GREEN/AMBER/RED,
leases, path ownership, review separation, and evidence.

## Decision

1. **Spec Kit pinned `v0.15.2`** — constitution at `.specify/memory/constitution.md`;
   install via `scripts/setup_spec_kit.ps1` (dev-operator only; not CI/prod images).
2. **Symphony is spec inspiration only** — implement thin dispatcher under
   `tools/pr_factory/` that **only** calls `create_mission` / `advance` on the
   existing orchestrator. **Do not** vendor `openai/symphony`.
3. **Dual-gate inert default:** `PR_FACTORY_ENABLED=0` and requires
   `EXTERNAL_AGENT_ORCHESTRATOR=1` when armed. Production enablement is out of Wave 1.
4. **GitHub CI repair** — draft workflow pins
   `anthropics/claude-code-action@9db594c7a0e82298c121c18b7f08aa1579ce7341`
   (v1.0.185). Least privilege; no deploy/billing/telephony secrets.
5. **Gate A** — non-required sketch workflow only; do not weaken existing required checks.
6. **Merge** — keep `auto-merge` label train; native Merge Queue later (org migration).
7. **Honest throughput:** Wave 1 ships the spine; target thereafter = 10–20 verified
   PRs per wave, not hour-scale 100-PR claims.

## Alternatives rejected

| Option | Why rejected |
|--------|----------------|
| Vendor openai/symphony | Second runtime + control plane; conflicts ADR-148/155 |
| Vibe Kanban / Parallel Code as primary | Same class of dual authority |
| Floating Spec Kit `latest` | Non-reproducible constitution tooling |
| Auto-deploy from factory | Deploy stays Owner-gated `deploy_vps.sh` |

## Consequences

- Docs: `docs/PR_FACTORY.md`, constitution under `.specify/`
- Flag: `PR_FACTORY_ENABLED` in automation flag registry + manifest (default OFF)
- Tests: `tests/test_pr_factory_task_schema.py`, `tests/test_pr_factory_orchestrator_bridge.py`
- Follow-on waves documented in `docs/PR_FACTORY.md` (intake, Gate B, merge_group)

## Rollback

- Leave flags OFF (default).
- Delete or disable the two draft workflows if noisy.
- Constitution/docs are inert without flag arming.
