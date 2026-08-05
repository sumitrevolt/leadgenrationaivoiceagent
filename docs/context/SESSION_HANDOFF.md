# SESSION_HANDOFF — 2026-08-05 (Social/Postiz QUEUE unblock)

## Shipped (ops — LIVE now)
- **Root cause:** Postiz Temporal orchestrator was a zombie (pm2 "online", **zero pollers**). API jobs showed `published` but FB posts stayed `QUEUE` for days.
- **Recovery:** `docker compose -f docker-compose.postiz.yml --env-file deploy/postiz/.env up -d --force-recreate --no-deps postiz` (no `--remove-orphans`).
- **Evidence:** Pollers back on task-queue `main`; QUEUE 6→0; Facebook posts PUBLISHED with releaseURL (e.g. Aug 2–4 LeadGen posts).
- Prod `/health` observed during session: `095d10a3` (uptime reset during recreate window).

## Code (this PR)
- `video_ad_cycle.enabled()` now honours `VIDEO_DAILY_SCHEDULER_ENABLED` (prod had this ON while `VIDEO_AD_CYCLE=0` → video cycle inert).
- `POSTIZ_SKIP_PLATFORMS` CSV skip (for X credits-depleted).
- Temporal healthcheck hardened in `docker-compose.postiz.yml`.
- Playbook: Postiz QUEUE / zombie orchestrator recovery.

## Verify
- Targeted: `test_run_cycle_honors_daily_scheduler_alias` + `test_select_skips_platforms_from_env` green.
- `scripts/prod_check.py` → ALL CHECKS PASSED.

## Do NOT
- `docker compose ... postiz ... --remove-orphans` (wipes main stack).
- Claim X posts work — X API `credits depleted` (402); set `POSTIZ_SKIP_PLATFORMS=x` after deploy or top up X credits.

## Next
1. Merge + deploy this PR (`deploy_vps.sh` + kill fence).
2. After deploy: optional `POSTIZ_SKIP_PLATFORMS=x` in app `.env`.
3. Own-brand videos still need approval (3 pending `leadgenai-self`); cycle will generate again once VIDEO_DAILY alias is live.
4. GTM Hot Queue → 2nd paid (WS-R3).
