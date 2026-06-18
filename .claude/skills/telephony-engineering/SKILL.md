---
name: telephony-engineering
description: Wire and operate telephony providers for LeadGen AI voice calls — Vobiz (active, India-native SIP), Twilio, SIP — connect calls, webhooks, provider selection, AMD/DND/DLT compliance, voice-streaming. Use when the user says "telephony", "calling setup", "vobiz/twilio", "voice webhook", "call lagao", "DID/caller-id", "DLT", or integrating/debugging outbound/inbound calls.
---

# Telephony Engineering (Vobiz-active · India-legal)

Provider: `TELEPHONY_PROVIDER` (explicit) ya auto-detect (`telephony_service._detect_provider`: sip→vobiz→twilio) + `DEFAULT_TELEPHONY` (CallManager). **Foreign trunks (Twilio/Telnyx) India-domestic = ILLEGAL** → Vobiz (India-native SIP/CPaaS) active. Exotel hata diya gaya (provider ab Vobiz).

## Vobiz (active provider)
- Handler: `app/telephony/vobiz_handler.py`. India-native SIP/telephony stack — `base_url=None` if unconfigured (graceful).
- `.env`: `VOBIZ_CALLER_ID` (DID/caller-id) + provider creds. Recharge → DID kharido → `VOBIZ_CALLER_ID=+91<DID>` + restart.
- API surface: `app/api/telephony_vobiz.py`. CallManager (`call_manager.py`) outbound place karta; readiness `telephony_readiness.py`.

## Webhooks
`app/api/webhooks.py` + `telephony/webhooks.py` mounted `/api/webhooks` (lazy-init, signature-verified, prod me fail-CLOSED jab secret unset). Health: `GET /api/webhooks/health` (provider). Vobiz answer → `/api/webhooks/vobiz/answer`; status → `/api/webhooks/vobiz/status`.

## Real-time AI voice stream (LIVE)
Simple flows = answer/connect. Live STT/TTS conversation = **Vobiz WS stream** `app/telephony/vobiz_stream.py` — stream WS `/api/telephony/vobiz/stream/{token}`. PCM16 audio → VAD/RMS → parent VAD/STT/LLM/TTS reuse. AI-disclosure greeting prepend. Phone-path = `phone_stream.py` (8k).

## Compliance (TRAI — mandatory)
- **AI-disclosure**: greeting "ek AI assistant" / "automated AI call" (`latency.build_niche_greetings`, `agent.py`).
- **DND fail-CLOSED**: promotional call BLOCK jab DND verify na ho. **AMD**: machine→voicemail-drop/hangup.
- **DLT** (cold/promotional) = ₹10L penalty; Udyam→DLT pending. Inbound + consented callback DLT-free (`CallRequest.call_type=transactional`).

## Blockers (external, user-action)
Vobiz trial ~khatam (recharge → DID → `VOBIZ_CALLER_ID`). DLT (cold-calling) Udyam→re-apply pending; inbound callback ko DLT nahi chahiye. Key exposed in chat → rotate (dashboard).

## Verify
`/api/webhooks/health` provider=vobiz · in-container handler `base_url` reachable · test call → Call Sid + status=completed. Secret rotate after any exposure.
