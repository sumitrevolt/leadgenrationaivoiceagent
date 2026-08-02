# ACTIVE_WORK - max 3 workstreams

---

## WS-1 WAHA QR → live canary - ACTIVE (owner action needed)
- **ID:** WS-1
- **Business outcome:** WORKING WAHA + one allowlisted canary
- **Current state:** Session status **FAILED** (QR timeout — not scanned, 2026-08-02 live probe). Provider fixed: `SCAN_QR_CODE` + real PNG QR; AUTO=0. Frontend now surfaces FAILED/SCAN_QR_CODE/WORKING + QR auto-refresh (ISSUE-01 landed).
- **Next exact action:** Owner opens `/app/whatsapp` → restart session → scan QR before timeout → reply `WAHA CONNECTED` → agent verify + canary
- **Out of scope:** blind wipe loops · Meta Cloud · soak · flipping `WHATSAPP_AUTO_SEND`

---

## WS-2 Estique payment - VERIFY (autopilot says converted)
- **ID:** WS-2
- **Business outcome:** Second paid customer with ledger+browser proof
- **Current state:** Sales autopilot store shows Estique `converted` (only non-owner prospect). Ledger/browser proof of the actual ₹1999 payment NOT independently re-verified this session.
- **Next exact action:** Confirm ledger row + payment evidence; if unpaid, owner private password reset → Billing ₹1999 → reply `PAID`
- **Out of scope:** requesting password in chat · manual mark-paid · fabricating evidence

---

## WS-3 OpenCode issue batch (2026-08-02) - ACTIVE
- **ID:** WS-3
- **Business outcome:** 12 issues fixed local + verified (WAHA UI, CSP PostHog, autopilot idle, staging provenance, context docs, …)
- **Current state:** ISSUE-01 WAHA UI ✅ · ISSUE-02 CSP PostHog allowlist ✅ (3 tests) · ISSUE-03 autopilot idle_reason ✅ (2 tests) · ISSUE-04 staging `:latest` fail-closed ✅ · ISSUE-05 context-docs refresh ✅. Remaining issues in queue.
- **Next exact action:** Continue remaining issues; final verify (pytest targeted + prod_check + secrets scan) before any deploy.
- **Out of scope:** any deploy without owner ask · WHATSAPP_AUTO_SEND · dial cap change
