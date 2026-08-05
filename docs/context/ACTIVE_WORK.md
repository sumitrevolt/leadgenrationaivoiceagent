# ACTIVE_WORK - max 3 workstreams

---

## WS-MEM1 Memory Stack ADR-158/161 - MERGE+DEPLOY IN FLIGHT
- **ID:** WS-MEM1
- **Business outcome:** 7-layer memory facade + governance CODE on main; flags OFF until owner arms
- **Current state:** Branch `feat/agent-memory-stack-pr` rebased on main (includes OKF #251)
- **Next exact action:** Push → PR → CI green → merge → `deploy_vps.sh` code-only (`MEMORY_STACK_ENABLED` stays OFF)
- **Out of scope:** arm MEMORY_STACK · Safe Pack · fake PAID · voice persona edits beyond governance gate

---

## WS-GTM1 Hot Queue → 2nd paid - REVENUE PENDING
- **ID:** WS-GTM1
- **Current state:** Prod still pre-deploy; after deploy SHA updates. HQ empty; owner prospect pick
- **Next exact action:** Real ₹1999 UPI → LEDGER_PAID
- **Out of scope:** fake PAID

---

## WS-AM1 Safe Pack - SEPARATE
- **ID:** WS-AM1
- **Next exact action:** After LEDGER_PAID + owner canary
- **Out of scope:** payment-path env flips

---

## Parked
- #248 PR Factory Draft (CI fail)
- Estique `removed`
