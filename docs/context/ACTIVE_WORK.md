# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Video Review Stage 3 — DEPLOYED, AUTH CANARY PENDING
- **ID:** WS-1
- **Release:** PR #97, merge/deploy SHA `510ed7bc1c7834892f81b9db092d1febb50dad48`, workflow run `30002538121` successful (still in production ancestry; current prod tip `7cab5f60`).
- **Status:** Exact-SHA five-container production parity was proven at Stage 3 ship. Customer cohort / WhatsApp review / publish / daily video scheduler remain OFF.
- **Safety:** No customer decision, external send, call, billing mutation, or queue mutation in triage.
- **Next exact action:** Owner signs in; owner-managed config enables only `VIDEO_CUSTOMER_REVIEW_ENABLED=1` plus `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`; then one authenticated read-only Jiya Preview canary.

---

## WS-2 GTM Hot Queue /app/inbox — IN PROGRESS
- **ID:** WS-2
- **Status:** Acquire second paid Marketing customer from lead-magnet inquiries with human-controlled outreach.
- **Next exact action:** Continue `/app/inbox` Hot Queue follow-up; platform_dial and WhatsApp auto-send stay OFF.

---

## WS-3 OpenClaw Admin Dashboard — LIVE Stage A (GREEN only)
- **ID:** WS-3
- **Release:** PR #105 merge `7cab5f609846e2c584edb8322dc684378a15e995` deployed to prod `7cab5f60` via `deploy_vps.sh`.
- **Status:** Admin `#openclawAdminCard` LIVE. Authenticated GREEN canaries SUCCEEDED; AMBER Stage A REJECTED; RED `calling.enable` REJECTED; calling HARD OFF. Gateway token still EMPTY.
- **Next exact action:** Separately reviewed Stage B design for production AMBER approvals — do not enable yet. Optional follow-up: NL phrase `enable calling` → RED (word-order gap).
