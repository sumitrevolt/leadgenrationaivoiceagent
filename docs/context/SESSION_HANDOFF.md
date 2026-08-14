# SESSION_HANDOFF — 2026-08-14 (Cursor: all-safe-branches integration + DSH deploy prep)

## Status
**IN PROGRESS — integration authorized by owner.** Current main (`cca7b3bd`) was merged into `cursor/deepseek-harness-migration-20260814`. DSH implementation commit `ab21f015` has passing pre-commit gates; merge conflicts are being resolved as unions. No production flag has been armed and no `.env` value changed.

## Active streams
- `WS-DSH` ACTIVE — code integration/deploy only; runtime/shadow/canary/retirement stay separately gated
- `WS-GTM1` ACTIVE — Hot Queue owner execution remains revenue blocker
- `WS-SEC` ACTIVE — Voice/Swara frozen; compliance gates unchanged

## DSH evidence
- Upstream pin: `deepseek-ai/deepseek-harness` @ `47f943859bef60e4160492346772ded9b24f765a`
- Matching smoke pair binary SHA: `4d2f75728797d7c932c20a09be1ff5042f3758111cde81ec8b7455ce52dfdfc6`
- Fresh smoke: fake MCP/model pass, shutdown `0.516s`, hard cancel `3.094s`
- CycloneDX SBOM: 1,275 components; forbidden runtime dependencies empty
- Canonical evidence: `docs/evidence/DSH_LINUX_CI_EVIDENCE_20260814.json`
- Shadow promotion gate remains closed; runtime/shadow flags OFF; allowlist empty

## Integration inventory
- Main already contains the safe merged worktree batch through PR #359 and docs PR #360.
- PR #357 and PR #354 are being updated independently against current main before merge.
- Patch-equivalent stale remote branches are already represented on main and must not be replayed.
- Debug-only `origin/ci-debug` is not a production merge candidate.

## Mandatory deploy posture
- Use `scripts/deploy_vps.sh` only with exact `APP_VERSION`.
- Close `VOICE_LAUNCH_KILL` fence for deploy, then restore the prior value with exact image version.
- Do not arm `DSH_RUNTIME_ENABLED`, `DSH_SHADOW_ENABLED`, `HARNESS_SESSION_EVENTS`, `AGENT_HARNESS`, `GSC_ENABLED`, dunning, or cold WhatsApp.
- Verify direct HTTPS `/health` twice, version parity, 5/5 image skew, queues/DLQ, and rollback SHA.

## Next
1. Finish merge conflict resolution and run targeted DSH suites + `prod_check.py` + secrets.
2. Push DSH branch, create/merge PR after checks.
3. Merge updated PR #357 and #354 only when required checks are green.
4. Deploy final `origin/main` with canonical script; record exact production evidence.
