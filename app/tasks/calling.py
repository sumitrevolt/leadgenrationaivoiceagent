"""
Calling Tasks
Background tasks for call management
"""
from celery import shared_task
import asyncio
from datetime import datetime

from app.telephony.call_manager import CallManager, CallRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@shared_task(bind=True, max_retries=3, rate_limit="20/m")
def make_call_task(self, call_request_data: dict):
    """
    Background task to make a single call
    """
    try:
        logger.info(f"Processing call request: {call_request_data.get('lead_id')}")
        
        call_manager = CallManager()
        
        # Create CallRequest from dict
        request = CallRequest(
            lead_id=call_request_data["lead_id"],
            phone_number=call_request_data["phone_number"],
            campaign_id=call_request_data.get("campaign_id"),
            niche=call_request_data.get("niche", "general"),
            client_name=call_request_data.get("client_name", ""),
            client_service=call_request_data.get("client_service", ""),
            script_name=call_request_data.get("script_name"),
            lead_data=call_request_data.get("lead_data", {}),
            priority=call_request_data.get("priority", 5)
        )
        
        # Run async call in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            result = loop.run_until_complete(
                call_manager.initiate_call(request)
            )
        finally:
            loop.close()
        
        logger.info(f"Call completed: {result.outcome if result else 'failed'}")
        
        return {
            "status": "completed",
            "call_id": result.call_id if result else None,
            "outcome": result.outcome if result else "failed"
        }
        
    except Exception as e:
        logger.error(f"Call task failed: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task
def process_queue():
    """
    Process the call queue - runs hourly
    """
    logger.info("Processing call queue")
    
    call_manager = CallManager()
    
    # Run async processing in sync context
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(call_manager.process_queue())
    finally:
        loop.close()
    
    return {"status": "completed", "processed_at": datetime.now().isoformat()}


@shared_task
def process_callbacks():
    """
    Process scheduled callbacks
    """
    logger.info("Processing scheduled callbacks")
    
    # TODO: Get scheduled callbacks from database
    # Queue them for calling
    
    return {"status": "completed"}


@shared_task
def retry_failed_calls():
    """
    Retry failed calls that are eligible for retry
    """
    logger.info("Retrying failed calls")
    
    # TODO: Get failed calls that haven't exceeded retry limit
    # Re-queue them
    
    return {"status": "completed"}
