# ACTIVE_WORK — max 3 workstreams

---

## WS-1 Video Review Stage 3 — LOCAL READY, PROD NOT DEPLOYED
- **ID:** WS-1
- **Branch / worktree:** `codex/video-review-stage3` @ `leadgen-video-review-stage3`
- **Base / prod:** `c7d5fa69`
- **Status:** Tenant/path/version-safe media, bearer-to-blob `<video controls>` preview, exact-revision decisions, terminal Reject semantics, stale-ledger refusal, explicit customer allowlist, local Chart.js, and service-worker v5 cache bust are implemented and browser/contract-proven locally.
- **Safety:** All review/WhatsApp/publish/scheduler flags remain OFF in production; no customer decision or external send was executed.
- **Next exact action:** Owner authorizes commit/push/deploy; then enable only `VIDEO_CUSTOMER_REVIEW_ENABLED=1` plus `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover` for one authenticated read-only Jiya preview canary. Keep publish/WA/scheduler OFF.

---

## WS-2 GTM Hot Queue /app/inbox — IN PROGRESS
- **ID:** WS-2
- **Status:** Acquire second paid Marketing customer from lead-magnet inquiries with human-controlled outreach.
- **Next exact action:** Continue `/app/inbox` Hot Queue follow-up; platform_dial and WhatsApp auto-send stay OFF.

---

## WS-3 OpenClaw Owner Copilot — PARKED, PROD FLAG OFF
- **ID:** WS-3
- **Status:** No action in this loop; Owner OS remains sole mutation authority.
