# Architecture Assessment — LeadGen AI Platform (leadsgenai.in)

**Author:** 阿奇 (Archi) · System Architect, Engineering Assurance Team
**Status:** In-Progress

---

## 1. Synthetic Telephony Verification Specification (Draft)

This specification addresses the identified architectural flaw where `telephony_readiness.py` only performs an empty-string check on `VOBIZ_CALLER_ID`. To ensure the outbound revenue path is functional, we require a verifiable synthetic outbound test.

### 1.1 Success Definition
A successful test call is defined by the following state sequence:
1. **Initiation:** The `telephony_service` successfully calls the provider's `place_call` endpoint with the configured `VOBIZ_CALLER_ID`.
2. **Acceptance:** The provider acknowledges receipt (no auth error/403/ownership error).
3. **Termination:** The call is either connected or rejected (Busy/No Answer) within 5 seconds without raising an unhandled exception or platform crash.
4. **Finality:** The call state is logged in `call_log`.

### 1.2 Test Target Number
- **Suggest:** A reserved non-dialable test number managed by the provider or a dedicated "sinking" test account, e.g., `+919999900000` (or similar, per Vobiz API documentation for loopback).
- **Requirement:** This number MUST NOT be a real customer number to prevent nuisance and DLT compliance issues.

### 1.3 Failure Handling & Circuit Breaking
- **Ownership/Auth Errors:** If the provider returns `403 Forbidden` or `Unauthorized` regarding caller ID, the check MUST fail immediately and log a specific `CALLEE_OWNERSHIP_FAILURE` event, triggering an admin alert.
- **Network Errors:** Transient errors (5xx) must be retried with exponential backoff (2 attempts max). Persistent errors mark the score as `0` for the `telephony_readiness` watchdog.

### 1.4 Readiness Check Placement
- **Integration Point:** `app/telephony/telephony_readiness.py` should incorporate a `verify_telephony_connectivity()` function.
- **Workflow:** This check runs as a periodic job (Celery beat, low priority, e.g., every 6 hours) outside the critical path of outbound marketing dials to avoid quota wastage.

### 1.5 Weighting
- **Score Weight:** 40/100 (This is the most critical path in the platform).
- **Impact:** Failure of this check MUST block the `dialer` service from attempting any further outbound campaigns.

---

## 2. Evidence Log

| # | Area | How verified | Status |
|---|------|--------------|--------|
| E1 | Caller ID Logic | `app/telephony/telephony_readiness.py` (L66) | VERIFIED |
| E2 | Fail-Open Pattern | `app/telephony/trunks.py` (fail-open) | VERIFIED |
