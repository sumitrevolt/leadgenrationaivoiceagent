# SESSION_HANDOFF — 2026-08-14 (Cursor: full DSH arm + Product-1 90d plan artifacts)

## Status
**DONE — DSH FULL AUTHORITY ARMED (owner override ADR-182 wave order).** Prod tip still `fb3d0bc2`. `DSH_RUNTIME_ENABLED=1`, allowlist=29 migratable, `dsh-worker` healthy, `swara`/`ananya` remain `direct`. Rollback drill proven then re-armed. Revenue Phase 0 checklist + 90d capacity plan docs landed (local).

## DSH facts (DIRECT_HOST_VERIFIED 2026-08-14 ~16:12Z)
- Image: `leadgen-dsh:47f94385` built on VPS; worker `leadgen-dsh-worker:fb3d0bc2`
- Env bak: `.env.bak-dsh-fullarm-20260814_155839`
- Proofs: `provider_kavya=dsh` · `provider_swara=direct` · allowlist_len=29 · `/health`=`fb3d0bc2`
- Rollback drill: `DSH_RUNTIME_ENABLED=0` → kavya=`direct` → re-arm → kavya=`dsh` (`ROLLBACK_DRILL_OK` + `REARM_OK`)
- Hotfixes required for arm: `tzlocal==5.4.4` in `requirements-dsh.lock.txt`; lazy `app/tasks/__init__.py`; redis re-attached to `leadgen_dsh_net` with `--alias redis` (stale redis lacked dsh_net DNS)
- Kill: `DSH_RUNTIME_ENABLED=0` + recreate app-image with `APP_VERSION=fb3d0bc2`

## Revenue
- Phase 0 owner checklist: `docs/gtm/HOT_QUEUE_BLITZ_CHECKLIST.md`
- 90d path to 50 paid/day Product-1: `docs/gtm/PRODUCT1_50_PAID_DAY_90D.md`
- Not claiming 50/day live — capacity program only

## Do not
- Arm cold WA / dunning / GSC without creds / harness session events
- Delete legacy direct executor
- Recreate without `APP_VERSION` · bare compose without `-f docker-compose.vps.yml`
- Use `DSH_AGENT_ALLOWLIST=*` (resolves empty → all direct)

## Next
1. Owner: Hot Queue blitz daily until 2nd paid
2. Commit/push surgical fixes (`requirements-dsh.lock.txt`, `app/tasks/__init__.py`) when owner asks
3. Phase 1: ads budget + GSC creds decision
