# SESSION_HANDOFF — 2026-08-14 (Cursor: merge safe PRs + DSH #361 AUTH-DEPLOY)

## Status
**DONE — deploy stream CLOSED.** Prod tip `fb3d0bc2`. All open mergeable PRs for this batch merged (#357 · #354 · #361). DSH CODE-READY/INERT on prod. No DSH/runtime flags armed. Voice FROZEN. Kill fence closed (VLK restored FALSE_TOKEN).

## Facts
- Merged: PR #357 (GTM Hot Queue / honest dashboards) · PR #354 (Dependabot python + pydantic-core pair fix) · PR [#361](https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/361) (hardened DSH runtime, inert)
- Merge tip / deploy SHA: `fb3d0bc28459ef66efe0fa49a150a896d478cd9c` (`fb3d0bc2`)
- Deploy: kill fence `.env.bak-deploy-killfence-20260814_150136` → `VOICE_LAUNCH_KILL=1` → `scripts/deploy_vps.sh fb3d0bc2` → `=== DEPLOYED fb3d0bc2 OK ===` → restore VLK=0 + recreate with `APP_VERSION=fb3d0bc2`
- Prod `/health` (HTTPS ×2 + host): `fb3d0bc2` · `environment:production` · `healthy` (DIRECT_HOST_VERIFIED 2026-08-14 ~15:25Z)
- Activation: `ready_for_first_paid_customer=true` · `payments_ready=true` · `blocker_count=0` · `warn_count=1`
- Skew: 5/5 app-image services `APP_VERSION=fb3d0bc2` · celery=0 · dlq:failed_tasks=0 · **NO dsh-worker container** (profile not started)
- Inert proven in `leadgen_app`: `DSH_RUNTIME_ENABLED` · `DSH_SHADOW_ENABLED` · `HARNESS_SESSION_EVENTS` · `AGENT_HARNESS` · `GSC_ENABLED`
- Rollback tag lineage: `150bf898` (protected) · prior `2326c931` pruned by retention

## Intentionally NOT merged
- Stale remote branches only (docs/lint/archive/ci-debug equivalents already on main or non-prod): left alone
- WIP / freebuff / skipped shims from earlier handoff — still out of scope
- No flag arm · no legacy retirement · no `dsh` compose profile enable

## Do not
- Arm `DSH_RUNTIME_ENABLED` / `DSH_SHADOW_ENABLED` / `HARNESS_SESSION_EVENTS` / `AGENT_HARNESS` / `GSC_ENABLED` / dunning / cold WA
- Start `--profile dsh` without separate owner auth
- Edit Voice/Swara · weaken DND/TRAI/DPDP
- Recreate without `APP_VERSION=<sha>` · bare compose without `-f docker-compose.vps.yml`

## Next
1. **OWNER — Hot Queue `/app/inbox`** (2nd paid blocker; not code-fixable)
2. Optional: remove finished DSH/PR354 worktrees after owner confirms
3. Then: Jiya referral kit, GSC creds (still OFF), B3 DKIM
