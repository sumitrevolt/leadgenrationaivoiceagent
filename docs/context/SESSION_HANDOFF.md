# SESSION_HANDOFF — 2026-08-14 (Cursor: ADR-180 dsh pattern steal)

## Status
**LAUNCH/REVENUE = GO** (unchanged). **ADR-179** dsh vendor = NO-GO. **ADR-180** steal #1 = CODE-PRESENT INERT. NO deploy. NO flag arm. Voice FROZEN.

## Facts
- Prod `/health` last probed this session lineage = `2326c931` (do not re-quote without re-probe)
- Activation: `ready_for_first_paid_customer=true`, `blocker_count=0` (2026-08-14)
- 2nd paid still owner Hot Queue `/app/inbox` + UPI confirm

## Changed (ADR-180)
- `app/agents/harness/session.py` — typed SessionEvent + process-local hash-chain
- `audit.record` stamps `seq`/`prev_hash`/`event_hash`/`session_event` only when `HARNESS_SESSION_EVENTS=1`
- `Harness.run()` turn_start/turn_end + optional `pre_step` reject
- Flag in `AUTOMATION_FLAGS` + overlay CANARY_ONLY default 0
- Tests: `tests/test_harness_session_events.py`

## Do not
- Vendor `deepseek-ai/deepseek-harness` / `npx @deepseek-ai/dsh`
- Arm `HARNESS_SESSION_EVENTS` or `AGENT_HARNESS` in prod
- Deploy / arm `STAFF_BUS_ENABLED` / `GSC_ENABLED` / `DUNNING_ENGINE` / `BOSS_DECISION_GOVERNANCE`
- Edit Voice/Swara (FROZEN)
- Commit/push unless owner asks

## Next (owner)
1. Hot Queue blitz `/app/inbox` (15 min/day) — 2nd-paid blocker
2. Approve UPI when payment arrives
3. Review/commit ADR-180 + leftover hygiene stubs if wanted on main
