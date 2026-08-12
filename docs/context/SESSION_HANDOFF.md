# SESSION_HANDOFF — 2026-08-12 (Cursor LANE B: revenue-ready evidence + truth sync)

## Status
**REVENUE AUDIT COMPLETE** — Money path READY, 2 owner actions blocking 2nd paid this week. NO deploy. NO flag arm.

## Facts
- `origin/main` = `23ea2d46` (includes #333 staff-bus, #334/#335 docs)
- **Prod `/health` = `9c47647c`** (DIRECT_HOST_VERIFIED 2026-08-12 07:39 UTC) — includes PR #332 ADR-177, #330 Boss governance, #329 rollback retention
- **Drift corrected:** `UPI_AUTO_ACTIVATE` docs said `=0`, actual prod `=1` (containment intact via allowlist)
- Evidence: `docs/evidence/REVENUE_READY_20260812.md` (GO matrix + owner actions)
- Active streams: WS-GTM1 (Hot Queue), WS-UPI304 (guest bind), WS-SEC (gates intact)

## Do not
- Deploy / arm `STAFF_BUS_ENABLED` / `GSC_ENABLED` / `DUNNING_ENGINE` / `BOSS_DECISION_GOVERNANCE`
- Edit Voice/Swara (FROZEN)
- Weaken compliance gates
- Quote stale SHA from docs without re-probe

## Next
1. **Owner:** Daily Hot Queue blitz at `/app/inbox` (15 min/day, 1-2 conversions target)
2. **Owner:** Approve UPI when payment arrives (admin queue)
3. **Optional:** Simulate guest UPI proof (staging or wait for real)
4. **Lane C (if needed):** Deploy readiness (after owner OK; gate `VOICE_LAUNCH_KILL=1`)
