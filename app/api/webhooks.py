from fastapi import APIRouter, Request, status
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/twilio/incoming")
async def twilio_webhook(request: Request):
    logger.info("Twilio webhook received")
    return {"status": "received"}

@router.post("/exotel/incoming")
async def exotel_webhook(request: Request):
    logger.info("Exotel webhook received")
    return {"status": "received"}
