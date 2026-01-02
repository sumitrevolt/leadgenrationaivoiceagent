"""
Telephony Webhooks
FastAPI routes for handling telephony provider callbacks
"""
from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import Response
from typing import Optional

from app.telephony.twilio_handler import TwilioHandler, TwilioWebhookHandler
from app.telephony.exotel_handler import ExotelHandler
from app.telephony.call_manager import CallManager
from app.voice_agent.agent import VoiceAgent
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter()

# Initialize handlers (these would be dependency injected in production)
voice_agent = VoiceAgent()
call_manager = CallManager()


@router.post("/twilio/voice/{call_id}")
async def twilio_voice_webhook(
    call_id: str,
    request: Request,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    From: str = Form(None),
    To: str = Form(None),
    SpeechResult: Optional[str] = Form(None),
    Digits: Optional[str] = Form(None)
):
    """
    Handle Twilio voice webhook
    
    Called when:
    - Call is answered
    - Speech input is received
    - DTMF digits are pressed
    """
    logger.info(f"Twilio voice webhook - Call: {call_id}, Status: {CallStatus}")
    
    webhook_handler = TwilioWebhookHandler(voice_agent)
    
    try:
        # Handle speech result or initial greeting
        twiml = await webhook_handler.handle_voice_webhook(
            call_sid=CallSid,
            call_id=call_id,
            speech_result=SpeechResult
        )
        
        return Response(content=twiml, media_type="application/xml")
        
    except Exception as e:
        logger.error(f"Voice webhook error: {e}")
        # Return error response
        handler = TwilioHandler()
        twiml = handler.generate_voice_response(
            text="Sorry, we encountered an error. Please try again later.",
            gather_input=False
        )
        return Response(content=twiml, media_type="application/xml")


@router.post("/twilio/status/{call_id}")
async def twilio_status_webhook(
    call_id: str,
    CallSid: str = Form(...),
    CallStatus: str = Form(...),
    CallDuration: Optional[int] = Form(None),
    RecordingUrl: Optional[str] = Form(None),
    ErrorCode: Optional[str] = Form(None),
    ErrorMessage: Optional[str] = Form(None)
):
    """
    Handle Twilio status callback
    
    Called when call status changes:
    - initiated, ringing, in-progress, completed, busy, no-answer, canceled, failed
    """
    logger.info(f"Twilio status webhook - Call: {call_id}, Status: {CallStatus}")
    
    try:
        if CallStatus == "completed":
            result = await call_manager.handle_call_completed(
                call_id=call_id,
                duration=CallDuration or 0,
                recording_url=RecordingUrl
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
async def exotel_status_webhook(request: Request):
    """
    Handle Exotel status webhook
    
    Exotel sends different parameters than Twilio
    """
    form_data = await request.form()
    
    call_sid = form_data.get("CallSid")
    status = form_data.get("Status")
    leg = form_data.get("Leg")  # which leg of the call
    duration = form_data.get("Duration")
    recording_url = form_data.get("RecordingUrl")
    
    logger.info(f"Exotel status webhook - SID: {call_sid}, Status: {status}")
    
    # Extract call_id from metadata or CallSid
    call_id = form_data.get("CallbackData") or call_sid
    
    try:
        if status == "completed":
            result = await call_manager.handle_call_completed(
                call_id=call_id,
                duration=int(duration) if duration else 0,
                recording_url=recording_url
            )
            
            if result:
                logger.info(f"Exotel call completed - Outcome: {result.outcome}")
        
        return {"status": "received"}
        
    except Exception as e:
        logger.error(f"Exotel webhook error: {e}")
        return {"status": "error", "message": str(e)}


@router.post("/exotel/voice")
async def exotel_voice_webhook(request: Request):
    """
    Handle Exotel ExoML voice webhook
    
    Returns ExoML (similar to TwiML)
    """
    form_data = await request.form()
    
    digits = form_data.get("digits")
    call_sid = form_data.get("CallSid")
    
    logger.info(f"Exotel voice webhook - SID: {call_sid}, Digits: {digits}")
    
    # Generate ExoML response
    handler = ExotelHandler()
    
    if digits == "9":
        # Opt-out
        exoml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say voice="female" language="hi-IN">
        Aapka number hamare calling list se hata diya gaya hai. Dhanyavad.
    </Say>
    <Hangup/>
</Response>"""
    else:
        # Continue conversation
        exoml = f"""<?xml version="1.0" encoding="UTF-8"?>
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
    stats = call_manager.get_stats()
    return {
        "status": "healthy",
        "provider": call_manager.provider.value,
        "stats": stats
    }
