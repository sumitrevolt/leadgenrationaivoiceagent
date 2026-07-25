# SESSION_HANDOFF - overwrite every session end

## Session objective
Continue fixing Automation-Max follow-on problems after cadence starve fix.

## Outcome
### Prod fixes (durable DB / surgical code)
1. **Cadence starve** — verified `run_due(limit=30)` → advanced=30, active 7666→7636, done 100→130. Runs writing to `cadence_runs.jsonl`.
2. **Kavya scheduled_pause** — stale `prod-kavya-canary` / "clear sticky" since 2026-07-22 was blocking `ops` + `watchdog` despite `OPS_WATCHDOG=1`. **Resumed**. Manual watchdog run OK.
3. **Arnav** — same sticky canary pause on `engineer_security`; **resumed**.
4. Journey `ensure_active_defaults` hardened (inquiry_received-specific) + docker-cp'd.

### Repo (PR #135 branch)
- `scripts/vps_clear_stale_canary_pauses.py` + tests
- journey defaults fix + test
- cadence fix already on branch (`c1fe192`)

## Owner next
1. Merge PR #135 when CI green — https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/135
2. Proper deploy with `APP_VERSION=<sha>` (surgical hotfixes evaporate on recreate)
3. GTM Estique human send; Jiya draft approvals

## Out of scope
Cold email · dial · WA auto · Swara/voice
