# SESSION_HANDOFF — 2026-08-14 (Cursor: merge unique branches then AUTH-DEPLOY)

## Status
**Landing unique shippable work onto main, then VPS deploy.** ADR-180 INERT. Hygiene archive included. WIP/rejected shims NOT merged. Voice FROZEN.

## Facts
- Prod last probed = `2326c931` (re-probe after deploy)
- Unique MERGE: `cursor/archive-duplicate-playbooks-deploy-wrappers` (hygiene `8bad08df` + ADR-180 `d84d1ff5`) onto `origin/main` `da9ea10e`
- SKIP: WIP lg00/freebuff, checkpoint `817173bf` (gitlinks + ledger), customer-auth shims `f5a232e3` (rejected by #352)
- Stash kept: `hygiene leftovers pre-main-merge 20260814` (refuse-bat stubs)

## Do not
- Arm `HARNESS_SESSION_EVENTS` / `AGENT_HARNESS` / `STAFF_BUS_ENABLED` / `GSC_ENABLED` / `DUNNING_ENGINE` / `BOSS_DECISION_GOVERNANCE`
- Vendor `deepseek-ai/deepseek-harness`
- Edit Voice/Swara
- `git worktree remove` registered `.freebuff` trees
- Recreate containers without `APP_VERSION=<sha>`

## Next
1. PR-merge to main → `deploy_vps.sh` with kill fence
2. Hot Queue `/app/inbox` still 2nd-paid blocker
