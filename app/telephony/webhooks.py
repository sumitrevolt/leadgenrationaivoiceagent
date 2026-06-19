"""
Telephony Webhooks
FastAPI routes for handling telephony provider callbacks.

Security: Twilio routes require a valid X-Twilio-Signature (verified via
app.api.webhooks dependencies). Answering-machine detection (AMD) on the Twilio
voice callback avoids wasting call credits on voicemail. Vobiz answer/status
callbacks are public, minimal handlers (no signed payload from Vobiz).
(Exotel removed 2026-06-18 — provider is now Vobiz.)

Handlers + the shared CallManager are lazy-initialised so importing this module (to
mount the router) can never crash app startup — CallManager() raises on an unknown
provider, so it must not run at import time.
"""

import os
from xml.sax.saxutils import escape as _xml_escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response

# Signature-verification dependencies live in the payments/webhooks module.
from app.api.webhooks import verify_twilio_signature
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

# --------------------------------------------------------------------------- #
# Lazy singletons (no heavy work at import time)
# --------------------------------------------------------------------------- #
_voice_agent = None
_call_manager = None


def _get_voice_agent():
    global _voice_agent
    if _voice_agent is None:
        from app.voice_agent.agent import VoiceAgent

        _voice_agent = VoiceAgent()
    return _voice_agent


def _get_call_manager():
    global _call_manager
    if _call_manager is None:
        try:
            from app.telephony.call_manager import CallManager

            _call_manager = CallManager()
        except Exception as e:  # unknown provider / config — don't crash the webhook
            logger.error(f"CallManager init failed: {e}")
            return None
    return _call_manager


# Machine AMD: Twilio AnsweredBy values that mean "not a live human".
_MACHINE_ANSWERS = {"machine_start", "machine_end_beep", "machine_end_silence", "machine_end_other", "fax"}


def _amd_twiml(call_id: str, answered_by: str) -> str:
    """Decide voicemail-drop vs hang-up for a machine-answered call (saves credits)."""
    from app.voice_agent.amd import AnsweringMachineDetector

    detector = AnsweringMachineDetector()
    leave_vm = os.getenv("AMD_LEAVE_VOICEMAIL", "0").strip().lower() in ("1", "true", "yes", "on")

    # Only a post-beep machine is safe to leave a message on; everything else
    # (greeting still playing, silence, fax, carrier) -> hang up immediately.
    if answered_by == "machine_end_beep" and leave_vm:
        client_name = os.getenv("VOICEMAIL_CLIENT_NAME", "") or "our team"
        callback = os.getenv("VOBIZ_CALLER_ID", "") or None
        ctx = None
        cm = _get_call_manager()
        if cm is not None:
            ctx = cm.active_calls.get(call_id)
        if ctx is not None and getattr(ctx, "client_name", None):
            client_name = ctx.client_name
        msg = detector.voicemail_message(client_name=client_name, callback_number=callback)
        logger.info(f"📼 AMD ({answered_by}) -> leaving voicemail for {call_id}")
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Response><Say voice="alice" language="hi-IN">'
            f"{_xml_escape(msg)}</Say><Hangup/></Response>"
        )

    logger.info(f"📼 AMD ({answered_by}) -> hang up {call_id} (no credit waste)")
    return '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>'


@router.post("/twilio/voice/{call_id}")
async def twilio_voice_webhook(
    call_id: str,
    request: Request,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    From: str = Form(None),
    To: str = Form(None),
    SpeechResult: str | None = Form(None),
    Digits: str | None = Form(None),
    AnsweredBy: str | None = Form(None),
    _sig: bool = Depends(verify_twilio_signature),
):
    """
    Handle Twilio voice webhook

    Called when:
    - Call is answered (with AnsweredBy from Twilio AMD)
    - Speech input is received
    - DTMF digits are pressed
    """
    logger.info(
        f"Twilio voice webhook - Call: {call_id}, Status: {CallStatus}, AnsweredBy: {AnsweredBy}"
    )

    # Answering-machine detection: if Twilio says a machine/voicemail/fax picked up,
    # either drop a short voicemail or hang up instead of running the AI conversation.
    if AnsweredBy and AnsweredBy in _MACHINE_ANSWERS:
        return Response(content=_amd_twiml(call_id, AnsweredBy), media_type="application/xml")

    try:
        from app.telephony.twilio_handler import TwilioWebhookHandler

        webhook_handler = TwilioWebhookHandler(_get_voice_agent())
        twiml = await webhook_handler.handle_voice_webhook(
            call_sid=CallSid, call_id=call_id, speech_result=SpeechResult
        )
        return Response(content=twiml, media_type="application/xml")

    except Exception as e:
        logger.error(f"Voice webhook error: {e}")
        from app.telephony.twilio_handler import TwilioHandler

        handler = TwilioHandler()
        twiml = handler.generate_voice_response(
            text="Sorry, we encountered an error. Please try again later.", gather_input=False
        )
        return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status/{call_id}")
async def twilio_status_webhook(
    call_id: str,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: int | None = Form(None),
    RecordingUrl: str | None = Form(None),
    ErrorCode: str | None = Form(None),
    ErrorMessage: str | None = Form(None),
    _sig: bool = Depends(verify_twilio_signature),
):
    """
    Handle Twilio status callback

    Called when call status changes:
    - initiated, ringing, in-progress, completed, busy, no-answer, canceled, failed
    """
    logger.info(f"Twilio status webhook - Call: {call_id}, Status: {CallStatus}")

    try:
        if CallStatus == "completed":
            cm = _get_call_manager()
            result = None
            if cm is not None:
                result = await cm.handle_call_completed(
                    call_id=call_id, duration=CallDuration or 0, recording_url=RecordingUrl
                )

            if result:
                # Here you would trigger CRM updates, notifications, etc.
                logger.info(f"Call completed - Outcome: {result.outcome}")

        elif CallStatus == "busy":
            logger.info(f"Call {call_id} - Line busy")

        elif CallStatus == "no-answer":
            logger.info(f"Call {call_id} - No answer")

        elif CallStatus == "failed":
            logger.error(f"Call {call_id} failed: {ErrorCode} - {ErrorMessage}")

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Status webhook error: {e}")
        return {"status": "error", "message": str(e)}


# --------------------------------------------------------------------------- #
# Vobiz callbacks (provider since 2026-06-18). Vobiz does not sign callbacks, so
# these are minimal public handlers. The live conversational path is the Vobiz
# stream WS (/api/telephony/vobiz/stream/{token}); call_manager points outbound
# answer_url/status at /api/webhooks/vobiz/answer + /vobiz/status.
# --------------------------------------------------------------------------- #
@router.post("/vobiz/status")
async def vobiz_status_webhook(request: Request):
    """Vobiz status callback — marks a completed call done (minute-metering +
    qualified-lead billing run via CallManager.handle_call_completed). Idempotent
    on call_id. Best-effort; never raises a 500."""
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    call_sid = form_data.get("CallSid") or form_data.get("call_uuid") or form_data.get("id")
    status = (form_data.get("Status") or form_data.get("call_status") or "").lower()
    duration = form_data.get("Duration") or form_data.get("duration")
    recording_url = form_data.get("RecordingUrl") or form_data.get("recording_url")
    call_id = form_data.get("CallbackData") or form_data.get("call_id") or call_sid

    logger.info(f"Vobiz status webhook - SID: {call_sid}, Status: {status}")

    try:
        if status in ("completed", "complete", "answered", "hangup"):
            # Idempotency: dedup on call_id so metering/billing run exactly once.
            try:
                from app.billing import idempotency as _idem

                if call_id and await _idem.seen_before(f"call_done:{call_id}"):
                    logger.info(f"Vobiz duplicate completion skipped: {call_id}")
                    return {"status": "duplicate_skipped"}
            except Exception:
                pass

            cm = _get_call_manager()
            result = None
            if cm is not None and call_id:
                result = await cm.handle_call_completed(
                    call_id=call_id,
                    duration=int(duration) if duration else 0,
                    recording_url=recording_url,
                )
            if result:
                logger.info(f"Vobiz call completed - Outcome: {result.outcome}")

        return {"status": "received"}
    except Exception as e:
        logger.error(f"Vobiz status webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/vobiz/answer")
async def vobiz_answer_webhook(request: Request):
    """Vobiz answer_url — returns VobizXML when a call connects.

    Default best-effort: AI-disclosure greeting then hang up (the full
    conversational loop runs over the Vobiz stream WS, not this answer_url).
    Press-9 opt-out is persisted cross-channel (TCCCPR) when Vobiz posts a digit.
    """
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    digits = str(form_data.get("digits") or form_data.get("Digits") or "").strip()
    call_sid = form_data.get("CallSid") or form_data.get("call_uuid") or ""

    if digits == "9":
        caller = str(
            form_data.get("From")
            or form_data.get("CallFrom")
            or form_data.get("from")
            or ""
        ).strip()
        if caller:
            try:
                from app.telephony.consent_ledger import record_opt_out

                record_opt_out(
                    caller, reason="ivr_press9", channel="voice", call_id=str(call_sid or "")
                )
            except Exception as _oe:
                logger.error(f"press-9 opt-out persist failed: {_oe}")
        else:
            logger.warning("press-9 opt-out: caller number missing in Vobiz payload")
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Speak>"
            "Aapka number hamare calling list se hata diya gaya hai. Dhanyavad."
            "</Speak><Hangup/></Response>"
        )
    else:
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            "<Response><Speak>"
            "Namaste. Main ek AI assistant bol rahi hoon."
            "</Speak><Hangup/></Response>"
        )

    return Response(content=xml, media_type="application/xml")


@router.post("/vobiz/inbound")
async def vobiz_inbound_webhook(request: Request):
    """Inbound / no-answer / missed Vobiz call → lead capture (+ gated AI callback).

    Wire this as the Vobiz inbound-DID webhook (and/or the no-answer/hangup
    callback on an unanswered inbound call). It captures the caller as a lead
    ALWAYS, and — when MISSED_CALL_CALLBACK=1 + a Vobiz DID is configured —
    triggers a transactional AI callback (caller rang us first, so ban-safe).

    Lead capture works NOW (no DID needed); the callback leg is flag-gated and
    inert without a DID. Best-effort; never raises a 500. Public (Vobiz does not
    sign callbacks). Mirrors the existing admin test route
    POST /api/growth/missed-call → missed_call.handle_missed_call.
    """
    try:
        form_data = await request.form()
    except Exception:
        form_data = {}

    # Vobiz inbound payloads vary; accept the common caller-number field names.
    from_number = str(
        form_data.get("From")
        or form_data.get("CallFrom")
        or form_data.get("from")
        or form_data.get("caller")
        or form_data.get("Caller")
        or ""
    ).strip()
    # Optional context (best-effort): niche/business may be passed as query/extra.
    niche = str(form_data.get("niche") or request.query_params.get("niche") or "general").strip() or "general"
    business = str(form_data.get("business") or request.query_params.get("business") or "").strip()
    status = str(form_data.get("Status") or form_data.get("call_status") or "").lower()

    logger.info(f"Vobiz inbound webhook - From: {from_number}, Status: {status}")

    if not from_number:
        logger.warning("Vobiz inbound webhook: caller number missing in payload")
        return {"status": "received", "captured": False, "reason": "no caller number"}

    try:
        from app.telephony.missed_call import handle_missed_call

        result = await handle_missed_call(from_number, niche, business)
        return {"status": "received", **(result if isinstance(result, dict) else {})}
    except Exception as e:
        logger.error(f"Vobiz inbound webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.get("/health")
async def telephony_health():
    """Health check for telephony system"""
    cm = _get_call_manager()
    if cm is None:
        return {"status": "degraded", "provider": None, "stats": {}}
    return {"status": "healthy", "provider": cm.provider.value, "stats": cm.get_stats()}
