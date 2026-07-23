# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Ship queue (ops + main drift + routing + deploy skew) — LOCAL COMPLETE, OWNER PR
- **ID:** WS-1
- **Status:** CODE COMPLETE / LOCAL-TEST-PROVEN — four change-sets ready; push/PR/merge owner-gated
- **Ready branches / sets:**
  1. Primary dirty ops (self-improve failclosed + boot_grace health + invoice-backed paying KPI) — 33 pytest + prod_check
  2. `backport/main-beat-chart-drift` @ `ade4103` — beat deadline 900 + chart race-safe — prod_check green
  3. `fix/agent-routing-honesty` @ `5f3826e` — blog→isha + healthy_idle — 44 pytest
  4. `fix/deploy-skew-compose-resolve` @ `9cd83d5` — compose skew B3 — 22 pytest
- **Next exact action:** Owner authorize commit/push/PR in that order (do not mix with unrelated local HEAD)

---

## WS-2 GTM Hot Queue /app/inbox — IN PROGRESS (0 → 1 ARR)
- **ID:** WS-2
- **Status:** Hot Queue prioritization + 1-click human WhatsApp active (business stream)
- **Next exact action:** Acquire 2nd paid customer from `/site-audit`, `/audit`, `/demo` inquiries; platform_dial + WA auto-send stay OFF

---

## WS-3 Video Review Stage 3 — CLOSED DEPLOYED
- **ID:** WS-3
- **Prod SHA:** `e8bffde3` (PRODUCTION-PROVEN; media route LIVE; unauth 401)
- **Status:** CLOSED DEPLOYED via PR #97/#98 lineage + later prod tip. Customer `<video>` + `/media` on prod. Review/publish flags OFF.
- **Next exact action:** Owner-gated Jiya canary only — `VIDEO_CUSTOMER_REVIEW_ENABLED=1` + `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover` after explicit auth. Do not open redundant video-preview PRs against main for already-shipped media route.
