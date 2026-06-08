"""
Telephony Webhooks
FastAPI routes for handling telephony provider callbacks.

Security: Twilio routes require a valid X-Twilio-Signature and Exotel routes a valid
X-Exotel-Signature (verified via app.api.webhooks dependencies). Answering-machine
detection (AMD) on the Twilio voice callback avoids wasting call credits on voicemail.

Handlers + the shared CallManager are lazy-initialised so importing this module (to
mount the router) can never crash app startup — CallManager() raises on an unknown
provider, so it must not run at import time.
"""

import os
from xml.sax.saxutils import escape as _xml_escape

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import Response

# Signature-verification dependencies live in the payments/webhooks module.
from app.api.webhooks import verify_exotel_signature, verify_twilio_signature
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


@router.post("/exotel/status")
async def exotel_status_webhook(
    request: Request, _sig: bool = Depends(verify_exotel_signature)
):
    """
    Handle Exotel status webhook

    Exotel sends different parameters than Twilio
    """
    form_data = await request.form()

    call_sid = form_data.get("CallSid")
    status = form_data.get("Status")
    form_data.get("Leg")  # which leg of the call
    duration = form_data.get("Duration")
    recording_url = form_data.get("RecordingUrl")

    logger.info(f"Exotel status webhook - SID: {call_sid}, Status: {status}")

    # Extract call_id from metadata or CallSid
    call_id = form_data.get("CallbackData") or call_sid

    try:
        if status == "completed":
            cm = _get_call_manager()
            result = None
            if cm is not None:
                result = await cm.handle_call_completed(
                    call_id=call_id,
                    duration=int(duration) if duration else 0,
                    recording_url=recording_url,
                )

            if result:
                logger.info(f"Exotel call completed - Outcome: {result.outcome}")

        return {"status": "received"}

    except Exception as e:
        logger.error(f"Exotel webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/exotel/voice")
async def exotel_voice_webhook(
    request: Request, _sig: bool = Depends(verify_exotel_signature)
):
    """
    Handle Exotel ExoML voice webhook

    Returns ExoML (similar to TwiML)
    """
    form_data = await request.form()

    digits = form_data.get("digits")
    call_sid = form_data.get("CallSid")

    logger.info(f"Exotel voice webhook - SID: {call_sid}, Digits: {digits}")

    if digits == "9":
        # Opt-out
        exoml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">
        Aapka number hamare calling list se hata diya gaya hai. Dhanyavad.
    </Say>
    <Hangup/>
</Response>"""
    else:
        # Continue conversation
        exoml = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">
        Kripya apna jawab bataiye.
    </Say>
    <Gather action="/api/webhooks/exotel/voice" method="POST" timeout="5"/>
</Response>"""

    return Response(content=exoml, media_type="application/xml")


@router.get("/health")
async def telephony_health():
    """Health check for telephony system"""
    cm = _get_call_manager()
    if cm is None:
        return {"status": "degraded", "provider": None, "stats": {}}
    return {"status": "healthy", "provider": cm.provider.value, "stats": cm.get_stats()}
