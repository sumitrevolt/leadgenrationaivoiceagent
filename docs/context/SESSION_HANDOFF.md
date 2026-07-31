# SESSION_HANDOFF - overwrite every session end

## Session objective
Safe production launch canary — Core Marketing live + authorized simulation flags; hard-offs preserved.

## Outcome — IN PROGRESS / WAIT soak
- Runtime before canary recreate: `ff949ae3` healthy, activation GO, 5/5 parity, queues/DLQ=0
- Added `scripts/vps_enable_safe_launch_canary.py` (+ tests); Automation-Max now forces `SELF_IMPROVE_LOOP=0`
- Authorized canary (after pin-safe recreate): `SALES_AUTOPILOT_ENABLED=1`+`DRY_RUN=1`, `CREATIVE_OS_ENABLED=1` (GPU/Comfy=0), `AGENT_RUNTIME=1`, `SELF_IMPROVE_LOOP=0`
- HARD OFF held: dial · WA auto · reply-auto · cold email · UPI auto · sales live channels · video social publish
- Gaps (owner/ops): Postiz container absent → `postiz.leadsgenai.in` 502; WAHA session FAILED earlier; Vobiz balance timeout (dial OFF)

## Verdict target
**WAIT** — Core Marketing launch live after canary arm; stability soak clock resets on flag recreate. Not false PRODUCTION READY until 24h clean soak.

## Head / Prod
- Branch: `ops/safe-launch-canary-20260731`
- Prod baseline: `ff949ae3` (pin for recreate)

## Safety
No live outbound · no dial · no WA auto · no UPI auto-activate · Swara/Voice frozen
