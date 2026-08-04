# SESSION_HANDOFF - coord-hub Owner OS adapter

## Session objective
Greenfield Coordination Hub as Owner OS thin projection (ADR-150). Recovery of prior Hub: **not found**.

## Isolation
- Worktree: `C:\Users\Ratanshila\Documents\leadgen-wt-coord-hub-2026-08-04`
- Branch: `cursor/coord-hub-owner-os-adapter-2026-08-04`
- Base: `origin/main` @ `4db0ef5f…`
- Primary checkout untouched

## Done
- `coordination_hub*.py` projection + HMAC auth + events + bounded git
- API under `/api/admin/owner-os/coordination-hub/*`
- Owner OS Coord Hub tab; flag `COORDINATION_HUB_ENABLED` default OFF
- ADR-150 + Buzz plane HMAC note; runtime-data store family + allowlist
- Tests: auth / git / projection

## Ship posture
Draft PR only. No merge/deploy/prod flag flip without separate authorize.

## Do not
Second mission registry · shared admin bearer for tools · fabricate Estique PAID
