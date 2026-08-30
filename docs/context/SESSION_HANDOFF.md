# SESSION_HANDOFF — 2026-08-20 (CP0 truth reconciliation)

## Status
**VERIFIED (no deploy needed).** Established fresh end-to-end truth at prod `658fc20a` and reconciled stale flag/cred/SHA claims. No app code changed, no flag flipped, no voice triggered, no revenue fabricated.

## Key truth established (DIRECT_HOST_VERIFIED 2026-08-20 ~13:05Z)
- Prod `/health` = `658fc20a` (healthy, environment:production). 5/5 app-image services pinned `658fc20a` zero-skew. Staging `28ba5d4e`. `leadgen_dsh_worker` running but `DSH_RUNTIME_ENABLED=0`.
- Queues clean: celery=0, dlq:failed_tasks=0, dlq:dead=0.
- Runtime-data cutover `RUNTIME_DATA_CUTOVER_ENABLED=1`, canonical `/opt/leadgen-runtime` fresh.
- All scheduler jobs ok & fresh (growth, email, sales_autopilot, social_drain, daily_video, gsc_rank, platform_dial, coordinator, boss-autonomy-sweep).

## Flag + cred drift (older docs were stale)
- BOSS_FULL_AUTONOMY=1 + BOSS_DECISION_GOVERNANCE=1 — governance sweep LIVE, agents UNARMED 30/30 (rollout held).
- CRM_SYNC=1 (Zoho + HubSpot creds present), COORD_PLAN_NODE=1, DAILY_VIDEO_CLIENTS=*, VIDEO_AD_CYCLE=1.
- GSC_ENABLED UNSET but GSC creds present (owner flip needed).
- META + POSTIZ + WAHA creds present (social publish path wired; canary not yet proven).
- Cold WA OFF (SALES_AUTOPILOT_WHATSAPP_ENABLED=0). Voice LIVE (PLATFORM_DIAL_DAILY=1, VOICE_LAUNCH_KILL=0).

## Verification gates run (local)
- prod_check.py → ALL CHECKS PASSED (1335 routes, 0 wiring gaps). check_secrets.py → no secrets. API.md synced (1359).
- graphify_refresh.bat failed (local graphify CLI node arg error — navigation-only, non-blocking).

## Next (Owner Preparation Pack — HUMAN-INPUT REQUIRED only)
1. **Hot Queue blitz** `/app/inbox` → 2nd customer.
2. **UPI bind + bank credit confirm** → `paid_today` registers (only revenue gate).
3. **Flip `GSC_ENABLED=1`** (creds already present) → rank tracking arms.
4. **Boss per-agent arm (mutating canary)** → autonomy rollout.
5. Optional: social/video provider publish canary (creds present).
