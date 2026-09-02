# DeepSeek Harness Migration

Status: LOCAL-ONLY contract and tests. No deploy claim. No flag arm.

## Scope

This repo keeps one governed control plane. DeepSeek Harness may replace only the
planning, turn, and tool loop surface inside the existing harness boundary. The
following remain canonical and are not replaced:

- Celery scheduling and workers
- Python domain engines
- `app.platform.agent_registry`
- Owner OS approvals and admin controls
- Tenant isolation, compliance, and billing truth

The 31 named identities stay intact. `swara` and `ananya` remain RED/HARD_OFF
and are permanently excluded from DSH migration. No voice path enters DSH.

## Evidence

Local evidence lives in:

- `docs/evidence/DSH_MIGRATION_CONTRACT_20260814.json`
- `tests/fixtures/dsh_migration_contract.json`
- `tests/test_dsh_migration_contract.py`

Evidence labels used here follow the project vocabulary:

- `LOCAL-ONLY`: generated or verified in this worktree only
- `CODE-PRESENT`: source landed locally
- `TEST-PROVEN`: targeted local tests passed
- `PRODUCTION-PROVEN`: forbidden to claim from this migration slice

## Gates

All DSH flags stay OFF by default. No authority, deploy, or retirement decision
is allowed until all of the following are true:

1. ADR-181 exists and ADR-179 remains intact for stock wheel/direct embedding/default tools/direct provider access.
2. The migration contract JSON is committed and deterministic.
3. Owner OS runtime API fields remain frozen and reviewed.
4. Runtime/workforce import and caller baseline remains non-empty and reviewed.
5. Local targeted tests pass, including registry/workforce parity and `prod_check.py`.
6. Owner explicitly authorizes the hardened source-built Linux follow-up path.

## Rollout Labels

The contract generator emits rollout labels from current source truth:

- `frozen_never_dsh`: `swara`, `ananya`
- `wave_1_read_only`: `kavya`
- `wave_2_draft`: `isha`
- `approved_social_handoff`: `zara`
- `current_green_pilot_read_only`: current GREEN pilot/read-only identities
- `green_internal_mutator`: GREEN internal mutators still held behind the existing runtime boundary
- `amber_customer_touch_final_approval_gated`: AMBER customer-touch identities
- `voice_path_excluded`: non-frozen voice identities preserved in roster but excluded from DSH path

## Hard NO-GO

Do not do any of the following in this migration track:

- Vendor the preview `dsh` package or run a stock wheel path
- Give DSH direct provider access
- Replace Celery, Python engines, or `agent_registry`
- Bypass Owner OS approvals or billing/compliance gates
- Move Swara/Ananya or any voice path into DSH
- Claim production proof from local generation or tests

## Rollback

Rollback is one step: delete the new contract artifacts and generator/test slice,
then revert ADR-181. No runtime flags or production surfaces are armed in this
state, so there is no live rollback action.
