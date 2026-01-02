"""
Call Manager
Unified call orchestration for Twilio and Exotel
"""
import asyncio
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
import uuid

from app.config import settings
from app.telephony.twilio_handler import TwilioHandler
from app.telephony.exotel_handler import ExotelHandler
from app.voice_agent.agent import VoiceAgent, CallStatus, CallContext
from app.utils.logger import setup_logger
from app.utils.dnd_checker import DNDChecker

logger = setup_logger(__name__)


class TelephonyProvider(Enum):
    """Supported telephony providers"""
    TWILIO = "twilio"
    EXOTEL = "exotel"


@dataclass
class CallRequest:
    """Request to make a call"""
    lead_id: str
    phone_number: str
    campaign_id: str
    niche: str
    client_name: str
    client_service: str
    script_name: str
    lead_data: Dict[str, Any]
    priority: int = 5  # 1 = highest, 10 = lowest
    retry_count: int = 0
    scheduled_time: Optional[datetime] = None


@dataclass
class CallResult:
    """Result of a completed call"""
    call_id: str
    lead_id: str
    phone_number: str
    status: str
    duration_seconds: int
    outcome: str  # interested, not_interested, callback, appointment, no_answer
    lead_score: int
    qualification_data: Dict[str, Any]
    transcript: List[Dict[str, str]]
    recording_url: Optional[str]
    appointment_details: Optional[Dict[str, Any]]
    callback_time: Optional[str]
    completed_at: datetime


class CallManager:
    """
    Unified Call Manager
    
    Handles:
    - Call queue management
    - Provider selection (Twilio/Exotel)
    - Concurrent call limiting
    - DND checking
    - Retry logic
    - Call result processing
    """
    
    def __init__(self, provider: Optional[str] = None):
        provider = provider or settings.default_telephony
        
        if provider == "twilio":
            self.handler = TwilioHandler()
        elif provider == "exotel":
            self.handler = ExotelHandler()
        else:
            raise ValueError(f"Unknown telephony provider: {provider}")
        
        self.provider = TelephonyProvider(provider)
        self.voice_agent = VoiceAgent()
        self.dnd_checker = DNDChecker()
        
        # Call queue
        self.call_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self.active_calls: Dict[str, CallContext] = {}
        self.completed_calls: List[CallResult] = []
        
        # Concurrency control
        self.max_concurrent_calls = settings.max_concurrent_calls
        self.semaphore = asyncio.Semaphore(self.max_concurrent_calls)
        
        # Stats
        self.calls_made = 0
        self.calls_connected = 0
        self.calls_failed = 0
        
        logger.info(f"📞 Call Manager initialized with {provider}")
    
    async def queue_call(self, request: CallRequest) -> str:
        """
        Add a call to the queue
        
        Returns:
            Call ID for tracking
        """
        call_id = str(uuid.uuid4())
        
        # DND check for Indian numbers
        if self.provider == TelephonyProvider.EXOTEL:
            dnd_status = await self.dnd_checker.check(request.phone_number)
            if dnd_status.get("is_dnd"):
                logger.warning(f"Phone {request.phone_number} is on DND list")
                return f"dnd_blocked_{call_id}"
        
        # Add to priority queue (lower number = higher priority)
        await self.call_queue.put((
            request.priority,
            datetime.now().timestamp(),
            call_id,
            request
        ))
        
        logger.info(f"Call queued: {call_id} to {request.phone_number}")
        return call_id
    
    async def start_call_processor(self):
        """
        Start processing calls from queue
        Call this in a background task
        """
        logger.info("🚀 Call processor started")
        
        while True:
            try:
                # Get next call from queue
                priority, timestamp, call_id, request = await self.call_queue.get()
                
                # Check if scheduled for later
                if request.scheduled_time and datetime.now() < request.scheduled_time:
                    # Re-queue for later
                    await self.call_queue.put((priority, timestamp, call_id, request))
                    await asyncio.sleep(60)  # Check again in 1 minute
                    continue
                
                # Process call with concurrency limit
                asyncio.create_task(self._process_call(call_id, request))
                
            except asyncio.CancelledError:
                logger.info("Call processor stopped")
                break
            except Exception as e:
                logger.error(f"Call processor error: {e}")
                await asyncio.sleep(5)
    
    async def _process_call(self, call_id: str, request: CallRequest):
        """Process a single call"""
        async with self.semaphore:
            try:
                logger.info(f"📞 Making call {call_id} to {request.phone_number}")
                self.calls_made += 1
                
                # Initialize voice agent for this call
                context = await self.voice_agent.start_call(
                    lead_id=request.lead_id,
                    phone_number=request.phone_number,
                    campaign_id=request.campaign_id,
                    niche=request.niche,
                    client_name=request.client_name,
                    client_service=request.client_service,
                    script_name=request.script_name,
                    lead_data=request.lead_data
                )
                
                self.active_calls[call_id] = context
                
                # Make the actual call
                if self.provider == TelephonyProvider.TWILIO:
                    call_sid = await self.handler.make_call(
                        to_number=request.phone_number,
                        call_id=call_id
                    )
                else:  # Exotel
                    call_sid = await self.handler.make_call(
                        to_number=request.phone_number,
                        call_id=call_id
                    )
                
                if call_sid:
                    context.status = CallStatus.RINGING
                    self.calls_connected += 1
                    logger.info(f"Call {call_id} connected: {call_sid}")
                else:
                    await self._handle_call_failure(call_id, request, "Failed to connect")
                
            except Exception as e:
                logger.error(f"Call {call_id} failed: {e}")
                await self._handle_call_failure(call_id, request, str(e))
    
    async def _handle_call_failure(
        self,
        call_id: str,
        request: CallRequest,
        error: str
    ):
        """Handle failed call with retry logic"""
        self.calls_failed += 1
        
        if request.retry_count < settings.call_retry_attempts:
            # Schedule retry
            request.retry_count += 1
            request.priority += 2  # Lower priority on retry
            request.scheduled_time = datetime.now() + asyncio.timedelta(
                minutes=settings.call_retry_delay_minutes * request.retry_count
            )
            
            await self.call_queue.put((
                request.priority,
                datetime.now().timestamp(),
                f"{call_id}_retry{request.retry_count}",
                request
            ))
            
            logger.info(f"Call {call_id} scheduled for retry #{request.retry_count}")
        else:
            logger.warning(f"Call {call_id} failed after {request.retry_count} retries")
            
            # Record as failed
            self.completed_calls.append(CallResult(
                call_id=call_id,
                lead_id=request.lead_id,
                phone_number=request.phone_number,
                status="failed",
                duration_seconds=0,
                outcome="failed",
                lead_score=0,
                qualification_data={},
                transcript=[],
                recording_url=None,
                appointment_details=None,
                callback_time=None,
                completed_at=datetime.now()
            ))
    
    async def handle_call_completed(
        self,
        call_id: str,
        duration: int,
        recording_url: Optional[str] = None
    ) -> CallResult:
        """
        Handle a completed call
        Called by webhook handler
        """
        context = self.active_calls.get(call_id)
        if not context:
            logger.warning(f"No context found for call {call_id}")
            return None
        
        # End call in voice agent
        summary = await self.voice_agent.end_call(call_id)
        
        # Determine outcome
        outcome = self._determine_outcome(summary)
        
        result = CallResult(
            call_id=call_id,
            lead_id=context.lead_id,
            phone_number=context.phone_number,
            status="completed",
            duration_seconds=duration,
            outcome=outcome,
            lead_score=summary.get("lead_score", 0),
            qualification_data=summary.get("qualification_answers", {}),
            transcript=summary.get("conversation_transcript", []),
            recording_url=recording_url,
            appointment_details=summary.get("appointment_details"),
            callback_time=summary.get("callback_time"),
            completed_at=datetime.now()
        )
        
        self.completed_calls.append(result)
        del self.active_calls[call_id]
        
        logger.info(f"✅ Call {call_id} completed. Outcome: {outcome}, Score: {result.lead_score}")
        
        return result
    
    def _determine_outcome(self, summary: Dict[str, Any]) -> str:
        """Determine call outcome from summary"""
        if summary.get("appointment_scheduled"):
            return "appointment"
        elif summary.get("callback_requested"):
            return "callback"
        elif summary.get("detected_intent") == "interested":
            return "interested"
        elif summary.get("detected_intent") == "not_interested":
            return "not_interested"
        elif summary.get("detected_intent") == "opt_out":
            return "opt_out"
        else:
            return "no_answer"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get call statistics"""
        return {
            "calls_made": self.calls_made,
            "calls_connected": self.calls_connected,
            "calls_failed": self.calls_failed,
            "active_calls": len(self.active_calls),
            "queued_calls": self.call_queue.qsize(),
            "completed_calls": len(self.completed_calls),
            "connection_rate": self.calls_connected / self.calls_made if self.calls_made > 0 else 0,
            "outcomes": self._get_outcome_stats()
        }
    
    def _get_outcome_stats(self) -> Dict[str, int]:
        """Get outcome breakdown"""
        outcomes = {}
        for call in self.completed_calls:
            outcomes[call.outcome] = outcomes.get(call.outcome, 0) + 1
        return outcomes
    
    async def get_hot_leads(self, min_score: int = 70) -> List[CallResult]:
        """Get high-scoring leads from completed calls"""
        return [
            call for call in self.completed_calls
            if call.lead_score >= min_score
        ]
    
    async def get_callbacks(self) -> List[CallResult]:
        """Get all callback requests"""
        return [
            call for call in self.completed_calls
            if call.outcome == "callback" and call.callback_time
        ]
    
    async def get_appointments(self) -> List[CallResult]:
        """Get all booked appointments"""
        return [
            call for call in self.completed_calls
            if call.outcome == "appointment" and call.appointment_details
        ]
