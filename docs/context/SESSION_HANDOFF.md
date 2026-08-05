# SESSION_HANDOFF — 2026-08-05 (PR Factory Wave 1)

## Active branch
`cursor/pr-factory-wave1-2026-08-05` (from `origin/main` @ `9f2ab9f`)

## What landed (local, not necessarily pushed)
- Spec Kit pin **v0.15.2** + `.specify/memory/constitution.md` + `scripts/setup_spec_kit.ps1`
- `tools/pr_factory/*` thin dispatcher → `external_agents.create_mission` only
- Flag `PR_FACTORY_ENABLED` (default OFF, dual-gate with `EXTERNAL_AGENT_ORCHESTRATOR`)
- Draft workflows: `pr-factory-ci-repair.yml` (action SHA `9db594c7…` / v1.0.185), `pr-factory-gate-a.yml` (non-required)
- ADR-156 + `docs/PR_FACTORY.md`
- Tests: `tests/test_pr_factory_task_schema.py`, `tests/test_pr_factory_orchestrator_bridge.py`

## ACTIVE_WORK
- **WS-PRF1** active; **WS-CH1** parked; WS-R1 / WS-R3 unchanged

## Do NOT
- Enable `PR_FACTORY_ENABLED` / `EXTERNAL_AGENT_*` in production
- Vendor openai/symphony
- Claim 100-PR/hour throughput
- Pile onto social/Postiz PR #245

## Next
- Targeted pytest + `prod_check` green → open PR when owner asks
- Wave 2+ = live intake / Gate B / merge_group (docs only for now)

## Related
- Social Postiz queue fix remains on `cursor/fix-social-postiz-queue-2026-08-05` / PR #245 (separate)
