# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM1 Hot Queue → 2nd paid - CODE_READY
- **ID:** WS-GTM1
- **Business outcome:** Operate `/app/inbox` → real ₹1999 UPI ledger-proof → onboard + first-value
- **Current state:** CODE_READY on branch; MERGED/DEPLOYED/LEDGER_PAID = NO. Safe Pack env OFF.
- **Next exact action:** PR CI + review → merge → deploy code-only → owner Hot Queue real UPI
- **Out of scope:** fake PAID · cold WA · open UPI auto-activate · voice · Safe Pack with deploy

---

## WS-AM1 Automation Max safe pack - TOOLING READY / ENV OFF
- **ID:** WS-AM1
- **Business outcome:** Safe engines after ledger proof only
- **Current state:** Canary + MC strip shipped in code; **APPLY not authorized until LEDGER_PAID**
- **Next exact action:** After LEDGER_PAID: DRY_RUN=1 capture → group canary APPLY
- **Out of scope:** all-flags-ON · Creative OS · REPLY_AUTO_SEND · bundle with deploy

---

## WS-R3 Pay-truth / Estique - FREE TRIAL
- **ID:** WS-R3
- **Business outcome:** Ledger-proven 2nd paid customer
- **Current state:** Trial only
- **Next exact action:** Real ₹1999 → PAID (WS-GTM1)
- **Out of scope:** fabricate PAID

---

## Parked
- WS-PRF1 PR Factory Wave 1 — Draft PR #248
- WS-CH1 Coordination Hub
- WS-R1 Autopilot refill — ARMED LIVE observe-only
