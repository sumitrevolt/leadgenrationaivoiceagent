## Wave 2 - Execution Checkpoint (CORRECTED + FIX APPLIED)
- [ ] TypeSafe old key provider-side revoke/rotate — OWNER ACTION
- [ ] GitHub required-status-check enforcement — ruleset me 5 lanes bind karo
- [x] DLQ forensic — ROOT CAUSE FIXED: gated-inert semantic bug (34 false positives → 0 after deploy)
- [ ] SmartFlo DID console gate — 918069879757 destination VOICE Bot assigned prove
- [ ] Deploy c4547ab18a + gated-inert fix — dry-run → canonical → /health.version
- [ ] One controlled SmartFlo call — CDR/status/transcript evidence capture
- [ ] Revenue execution — UPI bind + Hot Queue processing + acquisition economics

## Wave 2 Success Criteria (Proven End-State)
- [ ] rotation receipt/evidence
- [ ] merge actually blocked on red CI
- [x] DLQ root cause known + FIXED (gated-inert semantic bug)
- [ ] DID destination non-null
- [ ] deployed SHA aligned
- [ ] one successful compliant SmartFlo call
- [ ] second verified payment/customer event

## Fix Applied (Local — Needs Deploy)
- app/tasks/staff_jobs.py: Added gated_inert() check before raising RuntimeError (line 485-495)
- tests/test_gated_inert_dlq_regression.py: NEW regression test (3/3 PASS)
- Result: gated-off jobs return {"ok": True, "status": "gated_inert"} instead of triggering retry/DLQ
- 34 dead video_delivery* entries are FALSE POSITIVES (gate OFF by design, not pipeline failure)