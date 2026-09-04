# Synthetic Verification Spec — Telephony Readiness
**Target:** `telephony_readiness.py`

## 1. Success Definition
A successful test call is indicated by:
- Vobiz API status successful (200 OK) for `create_call`.
- No exception raised for `CallerIDNotOwnedByAccount` (which currently results in a silent dial failure).

## 2. Test Number
- **Pattern:** `+919998887776` (Assumed loopback/sink DID within Vobiz testing infrastructure).

## 3. Failure Handling
- Treat ownership errors as high priority events.
- Update `telephony_readiness` state to `FAIL_COMPLIANCE` (instead of the current false-positive).

## 4. Placement
- Function `verify_outbound_connectivity()` added to `app/telephony/telephony_readiness.py`.

## 5. Weighting
- Score Weight: 40/100.
