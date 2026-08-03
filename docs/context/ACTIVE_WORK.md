# ACTIVE_WORK - max 3 workstreams

---

## WS-R1 Autopilot refill - CODE READY (arm on deploy)
- **ID:** WS-R1
- **Business outcome:** Autopilot not idle-only; scored Maps prospects enter store
- **Current state:** Local code ready; Owner OS calling badge honesty fixed. Needs commit/PR/deploy + `SALES_AUTOPILOT_REFILL=1`.
- **Next exact action:** Owner ask → PR/deploy `APP_VERSION=<sha>` → arm refill flag → recreate app/worker/scheduler
- **Out of scope:** WHATSAPP_AUTO_SEND

---

## WS-R2 Speed-to-lead action - CODE READY
- **ID:** WS-R2
- **Business outcome:** Website inquiry → Hot Queue under 5 min
- **Current state:** Bridge + STL fields + Owner OS SLA badge shipped locally
- **Next exact action:** After deploy, test inquiry → `/app/inbox`
- **Out of scope:** auto WA send

---

## WS-R3 Pay-truth / Estique - OWNER PAY
- **ID:** WS-R3
- **Business outcome:** Ledger-proven 2nd paid customer
- **Current state:** Code demotes unpaid converted; Estique still needs real ₹1999
- **Next exact action:** Owner password → Billing ₹1999 → reply `PAID`
- **Out of scope:** fabricate payment / mark-paid
