"""
Webhooks API
Secure webhook endpoints for Twilio and Exotel
"""
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import hmac
import hashlib
import os
import logging

from app.utils.logger import setup_logger

router = APIRouter()
logger = setup_logger(__name__)


async def verify_twilio_signature(
    request: Request,
    x_twilio_signature: Optional[str] = Header(None, alias="X-Twilio-Signature")
) -> bool:
    """Verify Twilio webhook signature"""
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set - skipping signature verification (UNSAFE for production)")
        return True
    
    if not x_twilio_signature:
        raise HTTPException(status_code=401, detail="Missing Twilio signature")
    
    # Get full URL and form data for signature validation
    url = str(request.url)
    form_data = await request.form()
    
    # Build the data string for signature
    data_string = url
    for key in sorted(form_data.keys()):
        data_string += key + form_data[key]
    
    # Compute expected signature
    expected_signature = hmac.new(
        auth_token.encode('utf-8'),
        data_string.encode('utf-8'),
        hashlib.sha1
    ).digest()
    
    import base64
    expected_signature_b64 = base64.b64encode(expected_signature).decode('utf-8')
    
    if not hmac.compare_digest(expected_signature_b64, x_twilio_signature):
        logger.warning("Invalid Twilio signature received")
        raise HTTPException(status_code=401, detail="Invalid Twilio signature")
    
    return True


async def verify_exotel_signature(
    request: Request,
    x_exotel_signature: Optional[str] = Header(None, alias="X-Exotel-Signature")
) -> bool:
    """Verify Exotel webhook signature"""
    api_key = os.environ.get("EXOTEL_API_KEY", "")
    api_secret = os.environ.get("EXOTEL_API_SECRET", "")
    
    if not api_key or not api_secret:
        logger.warning("EXOTEL credentials not set - skipping signature verification (UNSAFE for production)")
        return True
    
    if not x_exotel_signature:
        raise HTTPException(status_code=401, detail="Missing Exotel signature")
    
    # Implement Exotel-specific signature verification
    # https://exotel.com/docs/api/signature-verification
    body = await request.body()
    
    expected_signature = hmac.new(
        api_secret.encode('utf-8'),
        body,
        hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, x_exotel_signature):
        logger.warning("Invalid Exotel signature received")
        raise HTTPException(status_code=401, detail="Invalid Exotel signature")
    
    return True


@router.post("/twilio/incoming")
async def twilio_webhook(request: Request):
    """
    Twilio incoming call/SMS webhook
    Verifies signature in production
    """
    # Verify signature
    await verify_twilio_signature(request)
    
    form_data = await request.form()
    logger.info(f"Twilio webhook received: {dict(form_data)}")
    
    # Process the webhook
    call_sid = form_data.get("CallSid")
    from_number = form_data.get("From")
    to_number = form_data.get("To")
    call_status = form_data.get("CallStatus")
    
    # TODO: Route to appropriate handler based on webhook type
    
    return {"status": "received", "call_sid": call_sid}


@router.post("/twilio/status")
async def twilio_status_webhook(request: Request):
    """
    Twilio call status callback
    """
    await verify_twilio_signature(request)
    
    form_data = await request.form()
    logger.info(f"Twilio status webhook: {dict(form_data)}")
    
    return {"status": "received"}


@router.post("/exotel/incoming")
async def exotel_webhook(request: Request):
    """
    Exotel incoming call webhook
    Verifies signature in production
    """
    await verify_exotel_signature(request)
    
    body = await request.json()
    logger.info(f"Exotel webhook received: {body}")
    
    # Process the webhook
    call_sid = body.get("CallSid")
    from_number = body.get("From")
    
    return {"status": "received", "call_sid": call_sid}


@router.post("/exotel/status")
async def exotel_status_webhook(request: Request):
    """
    Exotel call status callback
    """
    await verify_exotel_signature(request)
    
    body = await request.json()
    logger.info(f"Exotel status webhook: {body}")
    
    return {"status": "received"}

