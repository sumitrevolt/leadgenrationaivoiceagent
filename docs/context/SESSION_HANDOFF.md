# SESSION_HANDOFF — 2026-08-12 (Cursor: 31-agent STAFF bus setup)

## Done this session
- Isolated worktree/branch `cursor/31-agent-bus-setup-20260812` @ origin/main tip.
- Canonical STAFF bus package `app/platform/staff_bus/` (manifest/envelope/bridge/runtime/canary).
- Manifest validates **exactly 31** from `team.STAFF` + 7-team topology; Comb absent.
- Flag `STAFF_BUS_ENABLED` registered (OFF default) + automation_flag_manifest entry.
- Synthetic **31/31 GO** canaries: `docs/evidence/staff_bus_canary_20260812.json` run_id `254971bb491b`.
- Control-agent correlated canaries **5/5 SUCCESS** nonce `CNY20260812104913-63660547` (Fizz/Honey/Bumble/Comb/Boss) with e-tag correlation; Boss reply `… GO`.
- Hosted relay HTTPS 200; local `:3100` NIP-11 200; 5× buzz-acp live.
- Tests: `tests/test_staff_bus_2026_08_12.py` green.
- Runbook: `docs/runbooks/STAFF_BUS_31.md`.
- Prod read-only; no deploy/merge; UPI dirty files untouched.

## WAIT
- **Comb NIP-OA:** managed-agents `auth_tag=null` (AGENT_OWNER fallback). Correlated reply works; mandate still marks Desktop-minted NIP-OA as open WAIT.
- Draft PR merge/deploy = owner only.
- Buzz workspace canvas superset publish for all domain channels = optional follow-up if hosted membership edits needed.

## Do not
- Merge/deploy without owner
- Arm `STAFF_BUS_ENABLED` / `BOSS_DECISION_GOVERNANCE` in prod without AUTH
- Invent new Boss/STAFF keypairs or export auth tags
- Touch UPI/WA/email/calling/voice / prod DB

## Next
1. Owner Desktop Save on Comb to mint NIP-OA `auth_tag` (or accept WAIT)
2. Review Draft PR → AUTH-MERGE when ready
3. Optional: canvas/superset publish for #staff-pulse roster
