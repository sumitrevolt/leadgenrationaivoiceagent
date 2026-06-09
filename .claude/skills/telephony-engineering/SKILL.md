---
name: telephony-engineering
description: Wire and operate telephony providers for LeadGen AI voice calls — Exotel (active), Twilio, SIP — connect calls, webhooks, provider selection, AMD/DND/DLT compliance, voice-streaming. Use when the user says "telephony", "calling setup", "exotel/twilio", "voice webhook", "call lagao", "DID/exophone", "DLT", or integrating/debugging outbound/inbound calls.
---

# Telephony Engineering (Exotel-active · India-legal)

Provider: `TELEPHONY_PROVIDER` (explicit) ya auto-detect (`telephony_service._detect_provider`: sip→exotel→twilio) + `DEFAULT_TELEPHONY` (CallManager). **Foreign trunks (Twilio/Telnyx) India-domestic = ILLEGAL** → Exotel (Indian CPaaS) active.

## Exotel (LIVE, proven)
- Handler: `app/telephony/exotel_handler.py`. Auth = **API Key : API Token** HTTP Basic (modern; legacy `sid:token` = 401). Host: Singapore = `api.exotel.com` → `EXOTEL_SUBDOMAIN=api` (handler normalize, double `.exotel.com` se bacho).
- `.env`: `EXOTEL_SID` / `EXOTEL_API_KEY` / `EXOTEL_API_TOKEN` / `EXOTEL_SUBDOMAIN=api` / `EXOTEL_CALLER_ID`(exophone) / `EXOTEL_APP_ID`(applet).
- Place call (`/Calls/connect.json`): `From`=lead, `CallerId`=exophone, `Url`=`my.exotel.com/<sid>/exoml/start_voice/<app_id>`. Proven: Call Sid 99a7d455, 44s, AnsweredBy=human.
- **Discover account via API** (instead of asking user): `GET /v1/Accounts/<sid>/IncomingPhoneNumbers.json` → exophone + VoiceUrl→app_id; `GET /v1/Accounts/<sid>.json` → Type/KycStatus. v2 NOT supported (use v1).

## Webhooks
`app/api/webhooks.py` + `telephony/webhooks.py` mounted `/api/webhooks` (lazy-init, signature-verified). Health: `GET /api/webhooks/health` (provider). Exotel applet Url → `/api/webhooks/exotel/voice`; status → `/exotel/status`.

## Compliance (TRAI — mandatory)
- **AI-disclosure**: greeting "ek AI assistant" / "automated AI call" (`latency.build_niche_greetings`, `agent.py`).
- **DND fail-CLOSED**: promotional call BLOCK jab DND verify na ho. **AMD**: machine→voicemail-drop/hangup.
- **DLT** (cold/promotional) = ₹10L penalty; Udyam→DLT pending. Inbound + consented callback DLT-free (`CallRequest.call_type=transactional`).

## Blockers (external, user-action)
Exotel **Trial + KYC notstarted** → non-whitelisted numbers ke liye KYC+recharge. Real-time AI voice (live STT/TTS) = Exotel **voice-streaming (websocket)** product — alag enable; current handler ExoML/connect-based. Key exposed in chat → rotate (dashboard).

## Verify
`/api/webhooks/health` provider=exotel · in-container `ExotelHandler().base_url` + `/Calls.json` → 200 · test call `connect.json` → Call Sid + `/Calls/<sid>.json` status=completed. Secret rotate after any exposure.
