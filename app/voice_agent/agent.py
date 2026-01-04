"""
AI Voice Agent - Main Agent Orchestrator
Coordinates STT, LLM, TTS for voice conversations
"""
import asyncio
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import uuid
from contextlib import asynccontextmanager

from app.config import settings
from app.voice_agent.stt import SpeechToText
from app.voice_agent.tts import TextToSpeech
from app.voice_agent.llm_brain import LLMBrain
from app.voice_agent.intent_detector import IntentDetector
from app.voice_agent.conversation import ConversationManager, ConversationState
from app.utils.logger import setup_logger
from app.exceptions import TelephonyException, LLMException

logger = setup_logger(__name__)


class CallStatus(Enum):
    """Call status enumeration"""
    INITIATED = "initiated"
    RINGING = "ringing"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    NO_ANSWER = "no_answer"
    BUSY = "busy"
    VOICEMAIL = "voicemail"


@dataclass
class CallContext:
    """Context for a single call"""
    call_id: str
    lead_id: str
    phone_number: str
    campaign_id: str
    niche: str
    client_name: str
    client_service: str
    script_name: str
    status: CallStatus = CallStatus.INITIATED
    conversation_history: List[Dict[str, Any]] = field(default_factory=list)
    lead_data: Dict[str, Any] = field(default_factory=dict)
    qualification_answers: Dict[str, Any] = field(default_factory=dict)
    detected_intent: Optional[str] = None
    appointment_scheduled: bool = False
    callback_requested: bool = False
    objections_handled: List[str] = field(default_factory=list)
    call_duration_seconds: int = 0
    recording_url: Optional[str] = None
    error_count: int = 0
    max_errors: int = 3


class VoiceAgentError(Exception):
    """Custom exception for voice agent errors"""
    pass


class VoiceAgent:
    """
    Main AI Voice Agent Orchestrator
    
    Handles the complete flow:
    1. Receive audio from call
    2. Convert speech to text (STT)
    3. Process with LLM Brain
    4. Detect intent
    5. Generate response
    6. Convert text to speech (TTS)
    7. Send audio back to call
    """
    
    def __init__(self, tenant_id: Optional[str] = None):
        self.tenant_id = tenant_id or "default"
        self.stt: Optional[SpeechToText] = None
        self.tts: Optional[TextToSpeech] = None
        self.llm: Optional[LLMBrain] = None
        self.intent_detector: Optional[IntentDetector] = None
        self.active_calls: Dict[str, CallContext] = {}
        self._initialized = False
        self._lock = asyncio.Lock()
    
    async def initialize(self) -> None:
        """Initialize voice agent components lazily"""
        if self._initialized:
            return
        
        async with self._lock:
            if self._initialized:
                return
            
            try:
                self.stt = SpeechToText()
                self.tts = TextToSpeech()
                self.llm = LLMBrain(tenant_id=self.tenant_id)
                self.intent_detector = IntentDetector()
                self._initialized = True
                logger.info(f"✅ VoiceAgent initialized for tenant: {self.tenant_id}")
            except Exception as e:
                logger.error(f"Failed to initialize VoiceAgent: {e}")
                raise VoiceAgentError(f"Initialization failed: {e}") from e
    
    async def _ensure_initialized(self) -> None:
        """Ensure agent is initialized before operations"""
        if not self._initialized:
            await self.initialize()
        
    async def start_call(
        self,
        lead_id: str,
        phone_number: str,
        campaign_id: str,
        niche: str,
        client_name: str,
        client_service: str,
        script_name: str,
        lead_data: Optional[Dict[str, Any]] = None
    ) -> CallContext:
        """Initialize a new outbound call"""
        await self._ensure_initialized()
        
        call_id = str(uuid.uuid4())
        
        context = CallContext(
            call_id=call_id,
            lead_id=lead_id,
            phone_number=phone_number,
            campaign_id=campaign_id,
            niche=niche,
            client_name=client_name,
            client_service=client_service,
            script_name=script_name,
            lead_data=lead_data or {}
        )
        
        self.active_calls[call_id] = context
        logger.info(f"📞 Starting call {call_id} to {phone_number}")
        
        return context
    
    async def get_opening_message(self, call_id: str) -> str:
        """Get the opening message for a call"""
        await self._ensure_initialized()
        
        context = self.active_calls.get(call_id)
        if not context:
            raise VoiceAgentError(f"Call {call_id} not found")
        
        try:
            # Generate opening message using LLM
            opening = await self.llm.generate_opening(
                niche=context.niche,
                client_name=context.client_name,
                client_service=context.client_service,
                lead_name=context.lead_data.get("name", "Sir/Madam")
            )
            
            # Add compliance disclosure
            opening = f"Hello! This is an automated call from {context.client_name}. {opening}"
            
            context.conversation_history.append({
                "role": "assistant",
                "content": opening
            })
            
            return opening
            
        except Exception as e:
            logger.error(f"Failed to generate opening for call {call_id}: {e}")
            # Return fallback opening
            fallback = f"Hello! This is a call from {context.client_name}. How are you today?"
            context.conversation_history.append({
                "role": "assistant",
                "content": fallback
            })
            return fallback
    
    async def process_speech(
        self,
        call_id: str,
        audio_data: Optional[bytes] = None,
        audio_format: str = "wav",
        transcribed_text: Optional[str] = None
    ) -> str:
        """Process incoming speech and generate response"""
        await self._ensure_initialized()
        
        context = self.active_calls.get(call_id)
        if not context:
            raise VoiceAgentError(f"Call {call_id} not found")
        
        try:
            # 1. Convert speech to text (if not already transcribed)
            if transcribed_text:
                user_text = transcribed_text
            elif audio_data:
                user_text = await self.stt.transcribe(audio_data, audio_format)
            else:
                raise VoiceAgentError("Either audio_data or transcribed_text must be provided")
            
            logger.info(f"📝 User said: {user_text}")
            
            # 2. Add to conversation history
            context.conversation_history.append({
                "role": "user",
                "content": user_text
            })
            
            # 3. Detect intent
            intent = await self.intent_detector.detect(
                text=user_text,
                context=context
            )
            context.detected_intent = intent.intent_type
            logger.info(f"🎯 Detected intent: {intent.intent_type}")
            
            # 4. Handle special intents
            if intent.intent_type == "opt_out":
                return await self._handle_opt_out(context)
            elif intent.intent_type == "callback_request":
                return await self._handle_callback_request(context)
            elif intent.intent_type == "appointment_interest":
                return await self._handle_appointment(context)
            
            # 5. Generate response using LLM
            response = await self.llm.generate_response(
                conversation_history=context.conversation_history,
                niche=context.niche,
                client_name=context.client_name,
                client_service=context.client_service,
                detected_intent=intent,
                lead_data=context.lead_data
            )
            
            # 6. Add response to history
            context.conversation_history.append({
                "role": "assistant",
                "content": response
            })
            
            # Reset error count on success
            context.error_count = 0
            
            logger.info(f"🤖 Agent response: {response}")
            return response
            
        except Exception as e:
            context.error_count += 1
            logger.error(f"Error processing speech for call {call_id}: {e}")
            
            # Return error recovery response
            if context.error_count >= context.max_errors:
                context.status = CallStatus.FAILED
                return "I apologize, but we're experiencing technical difficulties. Let me arrange for someone to call you back shortly. Thank you for your patience."
            
            return "I'm sorry, I didn't catch that. Could you please repeat?"
    
    async def text_to_audio(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Convert text response to audio"""
        await self._ensure_initialized()
        
        try:
            return await self.tts.synthesize(text, voice_id)
        except Exception as e:
            logger.error(f"TTS failed: {e}")
            raise TelephonyException(f"Text-to-speech failed: {e}", provider=settings.default_tts)
    
    async def _handle_opt_out(self, context: CallContext) -> str:
        """Handle opt-out request"""
        context.status = CallStatus.COMPLETED
        context.detected_intent = "opt_out"
        return "I understand. We will remove your number from our calling list. Thank you for your time. Goodbye!"
    
    async def _handle_callback_request(self, context: CallContext) -> str:
        """Handle callback request"""
        context.callback_requested = True
        context.detected_intent = "callback_request"
        return "Certainly! I will arrange for a callback at your convenience. Could you please tell me your preferred time for the callback?"
    
    async def _handle_appointment(self, context: CallContext) -> str:
        """Handle appointment booking interest"""
        context.appointment_scheduled = True
        context.detected_intent = "appointment_interest"
        return "Great! I would be happy to schedule a meeting for you. What day and time works best for you?"
    
    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End a call and return summary"""
        context = self.active_calls.get(call_id)
        if not context:
            raise VoiceAgentError(f"Call {call_id} not found")
        
        if context.status not in [CallStatus.COMPLETED, CallStatus.FAILED]:
            context.status = CallStatus.COMPLETED
        
        # Record outcome for ML learning if LLM is available
        if self.llm and self._initialized:
            try:
                await self.llm.record_call_outcome(
                    outcome=context.detected_intent or "completed",
                    call_duration=float(context.call_duration_seconds),
                    conversation_history=context.conversation_history,
                    lead_data=context.lead_data,
                    niche=context.niche,
                    appointment_booked=context.appointment_scheduled,
                    callback_scheduled=context.callback_requested,
                )
            except Exception as e:
                logger.warning(f"Failed to record call outcome for ML: {e}")
        
        # Generate call summary
        summary = {
            "call_id": call_id,
            "lead_id": context.lead_id,
            "phone_number": context.phone_number,
            "campaign_id": context.campaign_id,
            "status": context.status.value,
            "duration_seconds": context.call_duration_seconds,
            "detected_intent": context.detected_intent,
            "appointment_scheduled": context.appointment_scheduled,
            "callback_requested": context.callback_requested,
            "qualification_answers": context.qualification_answers,
            "conversation_transcript": context.conversation_history,
            "recording_url": context.recording_url,
            "error_count": context.error_count,
        }
        
        # Remove from active calls
        del self.active_calls[call_id]
        
        logger.info(f"📞 Call {call_id} ended. Intent: {context.detected_intent}")
        return summary
    
    async def get_call_status(self, call_id: str) -> Optional[CallContext]:
        """Get current call status"""
        return self.active_calls.get(call_id)
    
    def get_active_calls_count(self) -> int:
        """Get number of active calls"""
        return len(self.active_calls)
    
    def get_active_call_ids(self) -> List[str]:
        """Get list of active call IDs"""
        return list(self.active_calls.keys())
    
    @asynccontextmanager
    async def call_session(
        self,
        lead_id: str,
        phone_number: str,
        campaign_id: str,
        niche: str,
        client_name: str,
        client_service: str,
        script_name: str,
        lead_data: Optional[Dict[str, Any]] = None
    ):
        """Context manager for handling a complete call session"""
        context = await self.start_call(
            lead_id=lead_id,
            phone_number=phone_number,
            campaign_id=campaign_id,
            niche=niche,
            client_name=client_name,
            client_service=client_service,
            script_name=script_name,
            lead_data=lead_data,
        )
        
        try:
            yield context
        except Exception as e:
            context.status = CallStatus.FAILED
            logger.error(f"Call session error: {e}")
            raise
        finally:
            if context.call_id in self.active_calls:
                await self.end_call(context.call_id)
