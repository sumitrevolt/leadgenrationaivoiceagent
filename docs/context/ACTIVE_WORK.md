# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Video Review Stage 3 — DEPLOYED, AUTH CANARY PENDING
- **ID:** WS-1
- **Release:** PR #97, merge/deploy SHA `510ed7bc1c7834892f81b9db092d1febb50dad48`, workflow run `30002538121` successful.
- **Status:** Exact-SHA five-container production parity and green health/readiness are proven. The first admin impersonation attempt returned 401 because the pre-deploy admin JWT was expired; reload correctly exposed the admin login boundary.
- **Safety:** Customer review, WhatsApp review, publish/social, daily video scheduler, WhatsApp auto-send, and platform dial remain OFF. No customer decision, external send, call, billing mutation, or queue mutation was executed.
- **Next exact action:** Owner signs in through the handed-off Admin Login tab and owner-managed config enables only `VIDEO_CUSTOMER_REVIEW_ENABLED=1` plus `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`; then run one authenticated read-only Jiya Preview canary.

---

## WS-2 GTM Hot Queue /app/inbox — IN PROGRESS
- **ID:** WS-2
- **Status:** Acquire second paid Marketing customer from lead-magnet inquiries with human-controlled outreach.
- **Next exact action:** Continue `/app/inbox` Hot Queue follow-up; platform_dial and WhatsApp auto-send stay OFF.

---

## WS-3 OpenClaw Owner Copilot — PARKED, PROD FLAG OFF
- **ID:** WS-3
- **Status:** No action in this loop; Owner OS remains sole mutation authority.
