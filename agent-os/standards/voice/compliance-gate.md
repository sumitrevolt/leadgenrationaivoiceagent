# Outbound Call Compliance Gate

`app/telephony/compliance.py` = the ONE chokepoint every outbound call passes. **Weakening any gate = ABORT, not a fix.**

- PROMOTIONAL (cold): DND scrub + window + DLT/140 ALL enforced. TRANSACTIONAL (consented): sane window only.
- **Fail-SAFE on internal error:** promotional → BLOCK, transactional → allow.
- DND lookup is fail-CLOSED; `DND_FAIL_OPEN` is IGNORED in production (CRITICAL log + prod_check BLOCKER).
- Promo window 09:00–19:00 IST (conservative subset of TRAI 09–21); overrides CLAMPED to the legal ceiling.
- AI disclosure at call start ("ek AI assistant") — always.
- Config read from env EACH call — VPS flips without redeploy.
- Runtime toggle pattern (dial_gate/platform_dial): explicit env → bind-mounted data-file → conservative default. For promotional dialing, conservative default = OFF/test-mode (also the compliance-correct default).
- 🚨 platform_dial = HARD OFF (user mandate) — re-enable only with user go-ahead + allowlist + bot/IVR detection.
