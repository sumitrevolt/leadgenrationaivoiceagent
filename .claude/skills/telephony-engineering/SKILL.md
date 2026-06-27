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

## Enterprise gate (telephony = HIGH-RISK always)
Operating loop — Discover → Contract → Execute → Self-review → Evidence (see `fable-operating-manual`). **Change-risk tier: High-risk always** — koi bhi outbound/inbound call code, webhook, ya stream change compliance + metering + cross-path parity locks; bypass = legal/financial risk.

**Compliance (fail-CLOSED — KABHI disable nahi):**
- **TRAI calling-window 9am–7pm IST** — promotional dial is window ke bahar BLOCK (`compliance.py`; pipeline `CALL_WINDOW` 9-21 sirf upper-bound, promo still 9–7).
- **DND scrub fail-CLOSED** — lookup fail = promotional BLOCK (`dnd_lookup_failed`), transactional looser gate. `CallRequest.call_type` (promo default).
- **AI-disclosure-at-start** — greeting me "ek AI assistant"/"automated AI call" (`latency.build_niche_greetings`, `vobiz_stream._AI_DISCLOSURE`); naye stream path me prepend zaroori.
- **Consent ledger** — press-9 / opt-out = INSTANT cross-channel 90-din suppression; **DPDP 90-din recording retention** (`consent_ledger.py`).
- **Webhook signatures** — prod me secret unset = **503 fail-CLOSED** (Twilio/Vobiz), kabhi open-pass nahi.

**Idempotency / metering:** call complete pe `post_call_hooks.meter_call_completion` = minute-billing + `call.completed` webhook, **idempotent** (Sid-keyed, double-bill na ho). FAIL-OPEN meter (call kabhi billing-error pe na rukke).

**Cross-path parity (non-negotiable):** har call path (`call_manager`/`vobiz_stream`/`phone_stream`) ke `_cleanup` me `meter_call_completion` + `_auto_qualify→apply_qualified_downstream` (CRM/sales/cadence) hona chahiye — naya path bina inke = adhoora. Guard: `scripts/cross_path_audit.py` (wired in `final_integration_check`).

**Reliability:** provider call = timeout + bounded retry; failure → never-raise + DLQ `dlq:failed_tasks`. No keys → simulation/graceful (`base_url=None`).

**Observability:** `/api/webhooks/health` (provider liveness) · `telephony_readiness.py` (Tara, vobiz-only) · Sentry FastApiIntegration global · call-state Redis (in-memory fallback).

**Rollback (NAMED):** offending behaviour env-flag OFF → `docker compose build app` + `up -d --no-deps app` (container recreate, stale .pyc clear) → `/health`=`environment:production`. Provider switch = `TELEPHONY_PROVIDER` + restart.

**Secrets:** sirf `.env` (gitignored); exposed key → rotate (Vobiz dashboard) + `scripts/check_secrets.py`.

**Evidence (done):** `.venv\Scripts\python.exe scripts\prod_check.py` + `.venv\Scripts\python.exe scripts\cross_path_audit.py` green + `pytest tests\ -q -k "telephony or webhook"` + live `/api/webhooks/health` provider=vobiz. Live-VPS deploy = explicit user-auth.
