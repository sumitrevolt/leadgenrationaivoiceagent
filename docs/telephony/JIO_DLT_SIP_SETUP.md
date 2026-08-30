# Jio SIP Trunk + DLT-140 Integration Runbook (LeadGen)

> Additive prep 2026-08-26. App side is READY; this documents exactly what to
> set the moment Jio/any-SIP credentials + DLT-140 number arrive.
> Compliance gates are NEVER weakened — this doc only wires a compliant trunk.

## 1. Goal
Run outbound AI cold-calls (Swara) over a SIP trunk with a DLT-140 caller-id,
unlimited-minutes option, while staying TRAI/TCCCPR compliant.

## 2. Compliance (already in app — do NOT touch)
`app/telephony/compliance.py` gate enforces for PROMOTIONAL calls:
- DND scrub **fail-CLOSED** (unverified lookup => block).
- Calling window 09:00–19:00 IST (clamped to TRAI legal 21:00 ceiling).
- `DLT_APPROVED=1` required.
- Caller-ID (`VOBIZ_CALLER_ID` / settings.vobiz_caller_id) required.
- Opt-out (consent ledger) suppression.
- **New (08-26):** `VOICE_DLT_TEMPLATE_ID` audit field recorded per promo call
  (non-blocking; surfaced in the ComplianceDecision `checks` dict).

## 3. Env to set for Jio SIP (once credentials arrive)
```env
# Provider routing
CALL_PROVIDER=sip            # or however telephony_service selects provider
SIP_PROVIDER=generic         # generic/frejun (not "vobiz")
SIP_HOST=<jio-sip-domain>      # e.g. siptrunk.jio.com / reseller-sip.domain
SIP_USERNAME=<username>
SIP_PASSWORD=<password>
SIP_DID=<140XX caller-id number>   # the DLT-140 number (E.164, +91...)
# Compliance
DLT_APPROVED=1
VOICE_DLT_TEMPLATE_ID=<dlt-template-id>   # registered voice template id
PUBLIC_BASE_URL=https://leadsgenai.in     # for webhooks/answer_url
```
> `telephony_service` providers: `vobiz` (current), `sip` (SIPHandler),
> `simulation` (dev, no real call). Switching to `sip` keeps the compliance gate.

## 4. FreeSWITCH media routing (SIP UA)
- SIPHandler note: real SIP media needs a running FreeSWITCH/Asterisk UA.
- Confirm the outbound route sends the FreeSWITCH via SIP to `SIP_HOST`
  authenticated with `SIP_USERNAME/SIP_PASSWORD`, caller-id = `SIP_DID`.
- Stream/answer path stays `https://leadsgenai.in/api/webhooks/vobiz/answer`
  for the Vobiz flow; for a raw SIP trunk the conversation is driven by the
  `script_callback`/on_answer hook.

## 5. Post-setup verification
1. `scripts/prod_check.py` — `/health` green, caller-id + trunk present.
2. Place ONE test call to an owner/consented number (transactional/allowlist).
3. Confirm hangup_cause is NOT `USER_BUSY` (registered caller-id => connects).
4. Check `/api/telephony/vobiz/status` webhook still 200 (answer/status routing).

## 6. Provider choice (from research 2026-08-26)
- **Jio SIP Trunk**: fixed-rental unlimited domestic, 10ch ₹499/mo / 30ch ₹999,
  140XX DLT numbers, up to 5000 channels. (GST/DLT needed for the number.)
- **FreJun**: DoT-licensed, DLT-140 handled, elastic channels, ₹1,149/user, trial.
- **DIDHub / Plivo (Tata) / VoiceLink**: BYOC alternatives.
- **Vyora / Kedeyo**: no-code agent platforms that pre-register compliant
  numbers (160-series = service; for pure cold-promo need 140).

## 7. GST note (solved)
DLT registration as a **sole proprietor accepts personal PAN + Aadhaar** — no
GST required for the DLT/KYC step. Business GST needed only for carrier billing
or if scaling to a formal entity.
