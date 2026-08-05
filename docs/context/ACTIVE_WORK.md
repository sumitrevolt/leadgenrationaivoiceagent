# ACTIVE_WORK - max 3 workstreams

---

## WS-GTM2 Admin Manual Call + Voice Dead-Air Fix - MERGED, DEPLOY PENDING
- **ID:** WS-GTM2
- **Business outcome:** Owner `/app/admin` par number daal kar canonical AI Marketing call place kar sake (SSH/manual script ki zarurat nahi), aur dead OmniRoute gateway live call ko dead-air na kare
- **Current state:** Admin call UI + `omniroute_voice` gateway circuit breaker `TEST-PROVEN` local (115 voice tests + prod_check PASS 1266 routes); merged to `main`; **prod pe deploy NAHI hua** — `/health` abhi purana SHA
- **Next exact action:** owner go-ahead pe `deploy_vps.sh` (kill-switch dance) → admin login canary → ek real call pe `llm_first` latency verify
- **Out of scope:** voice persona/prompt edits · env flips (`OMNIROUTE_VOICE` waisa hi) · automatic retries · compliance bypass · billing FK follow-up

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
