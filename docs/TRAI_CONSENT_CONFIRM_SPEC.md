# Spec — Roadmap #9: TRAI verbal/DTMF consent-confirm step (launch-ready)

> Status: **SPEC only** — do NOT build yet. Cold-calling is DLT/Vobiz-blocked, so
> there are no live promotional AI calls to verify against, and the touch-points
> are in the contested telephony flow. Build this **just-in-time**, as the launch
> gate, the moment cold-calling is unblocked. Keep behind a flag; verify on the
> FREE web-call path first.

## Why (regulatory)
TRAI TCCCPR **Feb-2025 2nd Amendment** expects AI-driven promotional calls to:
1. Open with a clear **AI disclosure** + company identity. ✅ already wired ("ek AI assistant" greeting).
2. **Obtain a verbal or DTMF confirmation before continuing** the promotional pitch. ❌ **this is the gap.**
3. **Timestamp + log** the consent. (consent_ledger exists.)
4. Honor **opt-out within 24–48h**, DND fail-closed, 10am–7pm, **140-series (promotional) / 1600-series (transactional/service)**. ✅ already wired.

Penalty for violation: ₹1,000–₹1,50,000 per violation; blacklisting on repeat. So #2 is a hard launch gate for the cold-call (Voice Agent) product.

## Design (additive, flag-gated, never-raise)
**Flag:** `CONSENT_CONFIRM=1` (default OFF → zero behaviour change). Only applies to `call_type == "promotional"`; transactional/inbound-callback unaffected.

**Flow (after the AI-disclosure opener, before any pitch):**
1. Greeting already says: "Namaste, main <Company> se ek AI assistant hoon."
2. Add ONE consent turn: *"Kya main aapko hamari service ke baare mein 1 minute mein bata sakti hoon? Haan ke liye 'haan' boliye ya 1 dabaiye."*
3. Capture response:
   - **Verbal**: STT result matches affirmative set (`haan`, ` haan ji`, `ok`, `yes`, `bILkul`, `batao`) → consent = granted.
   - **DTMF**: digit `1` → granted; `2`/`9` → declined/opt-out.
   - No clear yes within 1 retry → treat as **declined** (fail-closed) → polite close + `record_opt_out`-style suppression for promo.
4. On **granted**: `consent_ledger.record_consent(phone, channel="voice", basis="verbal_or_dtmf", call_id=...)` (timestamped) → continue to pitch.
5. On **declined**: log + end call gracefully; suppress further promo (cross-channel via consent_ledger).

## Integration points (file-level)
- `app/voice_agent/telecaller_brain.py` — add a `consent_gate` state at the front of the promotional script (after opener). Keep it as the first ACP step; the existing brain already runs ≤2-sentence/1-question turns, so this is one extra scripted turn.
- `app/voice_agent/vobiz_stream.py` / `phone_stream.py` — DTMF capture: Vobiz/Twilio send DTMF events on the media WS; route digit `1/2/9` into the consent gate. (Contested file → coordinate with the telephony owner.)
- `app/telephony/consent_ledger.py` — ensure a `record_consent(...)` (mirror of `record_opt_out`) exists; add if missing (additive).
- `app/telephony/compliance.py` — gate: if `CONSENT_CONFIRM=1` and promotional and consent not granted → block pitch (fail-closed), like the DND gate.
- Flag registry: add `CONSENT_CONFIRM` to `AUTOMATION_FLAGS` (growth.py) so `/api/growth/infra/flags` shows it.

## Test plan
- Unit: affirmative/negative/empty STT → granted/declined/declined; DTMF 1/2/9 → granted/declined/opt-out. (Pure parser, no telephony.)
- Web-call (`/app/test-call`): manually walk the consent turn on the FREE path before any phone verify.
- `scripts/agent_tester.py`: confirm no double/empty/repeat regression from the extra turn.
- `cross_path_audit` + `eval_guardrail`: green.

## Rollback
`.env` `CONSENT_CONFIRM=0` + app recreate → behaviour reverts to pre-consent-gate (pitch right after disclosure). Code is additive; `git revert` the consent commit if needed.

## Sources
TRAI TCCCPR Feb-2025 2nd Amendment (gazette regulation 12-02-2025); AI-calling India 2026 compliance guides. See `docs/ADVANCEMENT_ROADMAP_2026.md` §9.
