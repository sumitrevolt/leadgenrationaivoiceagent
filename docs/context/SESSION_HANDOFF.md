# SESSION_HANDOFF - overwrite every session end

## Session objective
World-class revenue automation (WS-R1/R2/R3) + Owner OS calling badge honesty.

## Shipped on this branch (needs deploy)
- Autopilot refill (`SALES_AUTOPILOT_REFILL` OFF default) + pay-truth `awaiting_payment` + inquiry→Hot Queue bridge
- Owner OS `calling_posture()` — badge LIVE vs OFF from `platform_dial.enabled()` (ENABLE still refused from Owner OS UI)
- API.md sync · tests for revenue automation + owner_os posture

## Owner next
1. Merge PR → deploy with `APP_VERSION=<sha>`
2. Arm `SALES_AUTOPILOT_REFILL=1` on VPS after deploy
3. Estique: password → Billing ₹1999 → reply `PAID` (never fabricate)
4. Optional: `POST /api/sales-autopilot/pay-truth/reconcile` after deploy

## Do not
Flip `WHATSAPP_AUTO_SEND` · weaken DND/TRAI · mark Estique paid without ledger · Owner OS ENABLE dial (use env)
