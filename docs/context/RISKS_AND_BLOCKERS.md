# RISKS_AND_BLOCKERS

Speculative risks are labeled SPECULATIVE — not confirmed defects.

## B1 — Jiya proof deliverable incomplete
- **Severity:** HIGH (paying customer last 10%)
- **Observed evidence:** ADR-125 left proof HONEST-blocked; Meta Advanced Access for customer pages pending
- **Business impact:** Delivery matrix stuck at ~90%; churn/trust risk
- **Root cause status:** EXTERNAL dependency + pending customer approvals
- **Owner:** Human operator + Meta review
- **Required resolution:** Channel connect / manual publish proof + approvals

## B2 — origin/main ahead of production
- **Severity:** MEDIUM
- **Observed evidence:** prod `/health`=`8ad64db7`; origin=`79ef3dc` (delivery_assurance)
- **Business impact:** Assurance scan cannot run in prod until deploy
- **Root cause status:** Deploy not run after merge
- **Owner:** User authorize deploy
- **Required resolution:** `deploy_vps.sh` with `APP_VERSION` of HEAD after WS-1 commit

## B3 — Stale SHA claims in CLAUDE Current State
- **Severity:** MEDIUM (context poison)
- **Observed evidence:** docs claimed `4fa716cb` while live `8ad64db7`
- **Business impact:** Agents “verify” wrong image; false completion claims
- **Root cause status:** Confirmed — fixed by docs/context + CURRENT_STATE
- **Owner:** any agent updating Current State
- **Required resolution:** Always probe `/health` before writing prod SHA

## B4 — Delivery Command Center At Risk KPI unwired
- **Severity:** MEDIUM
- **Observed evidence:** `renderKpis` expects `at_risk_count` but `loadAll` did not pass it
- **Business impact:** Admin under-sees paid-customer risk
- **Root cause status:** Confirmed code gap — WS-1 fixes
- **Owner:** WS-1
- **Required resolution:** Wire `assurance` into cockpit + UI

## B5 — automation_health ntfy patch uncommitted
- **Severity:** LOW
- **Observed evidence:** local diff only
- **Business impact:** dead-man phone push missing until commit+deploy
- **Root cause status:** LOCAL-ONLY
- **Owner:** parked (not in active 3 until WS slot free)
- **Required resolution:** separate workstream + tests

## SPECULATIVE — coordinator uncapped under 24/7 enablement
Not a current prod defect; `tests/test_coordinator_rate_cap.py` LOCAL-ONLY untracked.
