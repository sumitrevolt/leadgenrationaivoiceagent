# Runbook — Duplicate / Non-Compliant Outreach

## Scenario
A lead was contacted twice, an **opted-out** lead was contacted, or an outreach loop
over-sent (past the daily cap). This is a compliance + reputation incident (ban risk).

> **Zero-tolerance gate:** outreach must never contact opted-out leads, and scheduler
> retries must not duplicate external side effects.

## Standing controls (the safety net)
- **Consent ledger** (`app/telephony/consent_ledger.py`): opt-out → **instant cross-channel
  suppression** + 90-day recording retention. DSAR/DPDP purge available.
- **DND fail-closed** (`utils/dnd_checker.py` + `telephony/compliance.py`): lookup failure
  → promotional **BLOCK** (`dnd_lookup_failed`). Transactional unaffected.
- **Email outreach caps:** 25/day, MX-verified (`OUTREACH_VERIFY_MX=1`), warmup ramp,
  bounce auto-pause; `_is_bulk_sender()` guard (unknown+bulk = skip).
- **Idempotent side effects:** call/email completion hooks idempotent; cadence/lifecycle
  engines are **draft-only** by default (no unsolicited auto-send).
- **Calling window:** 9am–7pm (conservative vs TRAI 9am–9pm); AI-disclosure at greeting.

## Immediate Response
1. **Stop the bleed:** disable the offending loop via its flag (inert when OFF) —
   e.g. `AUTO_EMAIL_OUTREACH=false`, `CADENCE_ENGINE=false`.
2. Confirm scope: how many recipients, which channel, was anyone opted-out actually contacted?
3. If an opted-out lead was contacted, treat as P1 compliance incident — log it, do not
   send anything further to that contact, confirm the ledger entry exists.

## Diagnosis
- Was the dedupe/suppression checked **before** send? Trace the send path to the
  consent-ledger / DND check.
- Duplicate (same lead twice): missing send-dedupe (per-lead/per-day key) or a retry
  re-firing a non-idempotent send.
- Over-cap: warmup/cap counter not enforced or reset incorrectly.

## Recovery
1. Patch the missing guard (suppression-check-before-send, or per-lead dedupe key).
2. Re-enable the loop only after the guard is verified by a test.
3. If reputation impact (spam complaints), pause warmup and let bounce/complaint
   auto-pause settle before resuming.

## Post-Incident
- RCA + regression: `tests/test_consent_ledger.py`,
  `tests/test_consent_reconsent_cooloff.py`, `test_email_unsub.py`,
  `test_email_warmup_complaints.py`, `test_reply_junk_guard.py`.
- **Never** disable a compliance gate to "ship faster" — these gates are the product's license to operate.
- Record as ADR if the outreach/consent flow changed.
