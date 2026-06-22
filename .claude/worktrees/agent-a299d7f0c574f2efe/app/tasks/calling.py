"""
Calling Tasks
Background tasks for call management
"""

import asyncio
from datetime import datetime, timedelta

from celery import shared_task

from app.config import settings
from app.models.base import get_db_session
from app.models.call_log import CallLog, CallOutcome
from app.models.lead import Lead, LeadStatus
from app.telephony.call_manager import CallManager, CallRequest
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _run_async(coro):
    """Run an async coroutine in a Celery (sync) task with proper teardown.

    asyncio.run-style cleanup (cancel pending + shutdown_asyncgens before close)
    so leftover transports don't log "Event loop is closed" on GC.
    """
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for t in pending:
                t.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        finally:
            try:
                asyncio.set_event_loop(None)
            except Exception:
                pass
            try:
                loop.close()
            except Exception:
                pass


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
            priority=call_request_data.get("priority", 5),
        )

        # Enqueue the call onto the (compliance-gated, Redis-backed) priority queue.
        # NOTE: CallManager has no `initiate_call`; the public API is `queue_call()`
        # (enqueue) drained by `start_call_processor()` (long-running). The old name
        # raised AttributeError if legacy beat fired this task — fixed to queue_call.
        call_id = _run_async(call_manager.queue_call(request))

        # queue_call returns a sentinel id ("compliance_blocked_*", "out_of_*") when
        # the call was rejected by the compliance/billing gate rather than queued.
        blocked = bool(call_id) and (
            call_id.startswith("compliance_") or call_id.startswith("out_of_")
        )
        logger.info(f"Call enqueued: {call_id} (blocked={blocked})")

        return {
            "status": "blocked" if blocked else "queued",
            "call_id": call_id,
            "outcome": "blocked" if blocked else "queued",
        }

    except Exception as e:
        logger.error(f"Call task failed: {e}")
        raise self.retry(exc=e, countdown=60)


@shared_task
def process_queue(max_seconds: int = 50):
    """
    Drain the call queue for a bounded window (legacy beat path).

    CallManager exposes `start_call_processor()` (an infinite loop), NOT a
    one-shot `process_queue()` — calling the old name AttributeError'd. We run
    the processor under a timeout so a periodic Celery task drains pending calls
    without blocking the worker forever. Each queued call is compliance-gated in
    queue_call(), so this only dispatches already-vetted requests.
    """
    logger.info("Processing call queue")

    call_manager = CallManager()

    async def _drain():
        try:
            await asyncio.wait_for(
                call_manager.start_call_processor(), timeout=max(1, int(max_seconds))
            )
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Expected: the processor loops forever; we stop it after the window.
            pass

    # Run async processing in sync context (proper teardown)
    _run_async(_drain())

    return {"status": "completed", "processed_at": datetime.now().isoformat()}


@shared_task
def process_callbacks():
    """
    Process scheduled callbacks
    """
    logger.info("Processing scheduled callbacks")

    callbacks_queued = 0
    now = datetime.utcnow()

    try:
        with get_db_session() as db:
            # Get leads with scheduled callbacks that are due
            leads_with_callbacks = (
                db.query(Lead)
                .filter(
                    Lead.status == LeadStatus.CALLBACK,
                    Lead.next_call_at <= now,
                    Lead.next_call_at >= now - timedelta(hours=1),  # Within the last hour window
                )
                .limit(50)
                .all()
            )

            for lead in leads_with_callbacks:
                # Queue the callback
                call_request_data = {
                    "lead_id": lead.id,
                    "phone_number": lead.phone,
                    "campaign_id": lead.campaign_id,
                    "niche": lead.niche,
                    "lead_data": {
                        "company_name": lead.company_name,
                        "contact_name": lead.contact_name,
                        "is_callback": True,
                        "previous_notes": lead.notes,
                    },
                    "priority": 3,  # Higher priority for callbacks
                }

                make_call_task.delay(call_request_data)
                callbacks_queued += 1

                # Update lead to prevent re-queuing
                lead.last_called_at = now
                lead.call_attempts += 1

            db.commit()

    except Exception as e:
        logger.error(f"Error processing callbacks: {e}")

    logger.info(f"Queued {callbacks_queued} callbacks for calling")
    return {"status": "completed", "callbacks_queued": callbacks_queued}


@shared_task
def retry_failed_calls():
    """
    Retry failed calls that are eligible for retry
    """
    logger.info("Retrying failed calls")

    retries_queued = 0
    max_retries = settings.call_retry_attempts
    retry_delay = timedelta(minutes=settings.call_retry_delay_minutes)
    now = datetime.utcnow()

    try:
        with get_db_session() as db:
            # Get failed calls eligible for retry
            failed_calls = (
                db.query(CallLog)
                .filter(
                    CallLog.outcome.in_(
                        [CallOutcome.NO_ANSWER, CallOutcome.BUSY, CallOutcome.FAILED]
                    ),
                    CallLog.retry_count < max_retries,
                    CallLog.created_at <= now - retry_delay,  # Wait before retry
                )
                .limit(30)
                .all()
            )

            for call in failed_calls:
                # Get the lead for this call
                lead = db.query(Lead).filter(Lead.id == call.lead_id).first()
                if not lead:
                    continue

                # Skip if lead is already processed
                if lead.status in [
                    LeadStatus.APPOINTMENT,
                    LeadStatus.CONVERTED,
                    LeadStatus.NOT_INTERESTED,
                ]:
                    continue

                # Queue retry call
                call_request_data = {
                    "lead_id": lead.id,
                    "phone_number": lead.phone,
                    "campaign_id": call.campaign_id,
                    "niche": lead.niche,
                    "lead_data": {
                        "company_name": lead.company_name,
                        "contact_name": lead.contact_name,
                        "is_retry": True,
                        "retry_count": call.retry_count + 1,
                        "original_call_id": call.id,
                    },
                    "priority": 7,  # Lower priority for retries
                }

                make_call_task.delay(call_request_data)
                retries_queued += 1

                # Update call retry count
                call.retry_count += 1

            db.commit()

    except Exception as e:
        logger.error(f"Error retrying failed calls: {e}")

    logger.info(f"Queued {retries_queued} calls for retry")
    return {"status": "completed", "retries_queued": retries_queued}


@shared_task
def cleanup_stale_calls():
    """
    Clean up calls that are stuck in 'initiated' or 'ringing' status
    """
    logger.info("Cleaning up stale calls")

    stale_threshold = datetime.utcnow() - timedelta(minutes=10)
    cleaned = 0

    try:
        with get_db_session() as db:
            stale_calls = (
                db.query(CallLog)
                .filter(
                    CallLog.status.in_(["initiated", "ringing"]),
                    CallLog.initiated_at < stale_threshold,
                )
                .all()
            )

            for call in stale_calls:
                call.status = "failed"
                call.outcome = CallOutcome.FAILED
                call.error_message = "Call timed out - no response"
                call.ended_at = datetime.utcnow()
                cleaned += 1

            db.commit()

    except Exception as e:
        logger.error(f"Error cleaning stale calls: {e}")

    logger.info(f"Cleaned up {cleaned} stale calls")
    return {"status": "completed", "cleaned": cleaned}
