# ACTIVE_WORK - max 3 workstreams

---

## WS-1 WAHA QR → live canary - ACTIVE (owner scan now)
- **ID:** WS-1
- **Business outcome:** WORKING WAHA + one allowlisted canary
- **Current state:** Provider fixed — `SCAN_QR_CODE` + real PNG QR; AUTO=0
- **Next exact action:** Owner scan → reply `WAHA CONNECTED` → agent verify + canary
- **Out of scope:** blind wipe loops · Meta Cloud · soak

---

## WS-2 Estique credential + payment - ACTIVE
- **ID:** WS-2
- **Business outcome:** Second paid customer with ledger+browser proof
- **Current state:** UPI allowlist ON for `81bd0bbe501d`; login invalidated after chat exposure; unpaid rows=0
- **Next exact action:** Owner private password reset → Billing ₹1999 → reply `PAID`
- **Out of scope:** requesting password in chat · manual mark-paid · soak

---

## WS-3 Immediate acceptance (soak waived) - WAIT gates
- **ID:** WS-3
- **Business outcome:** `TODAY VERDICT: GO` after WA + payment evidence
- **Current state:** Core Marketing green at `3c843517`; soak SUPERSEDED
- **Next exact action:** After both gates pass → infra/boundary acceptance → GO
- **Out of scope:** time-based soak · fabricating delivery/payment
