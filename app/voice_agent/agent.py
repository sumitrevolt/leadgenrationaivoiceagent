"""
AI Voice Agent - Main Agent Orchestrator
Coordinates STT, LLM, TTS for voice conversations
"""
import asyncio
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import uuid

from app.config import settings
from app.voice_agent.stt import SpeechToText
from app.voice_agent.tts import TextToSpeech
from app.voice_agent.llm_brain import LLMBrain
from app.voice_agent.intent_detector import IntentDetector
from app.voice_agent.conversation import ConversationManager, ConversationState
from app.utils.logger import setup_logger

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
    conversation_history: list = field(default_factory=list)
    lead_data: Dict[str, Any] = field(default_factory=dict)
    qualification_answers: Dict[str, Any] = field(default_factory=dict)
    detected_intent: Optional[str] = None
    appointment_scheduled: bool = False
    callback_requested: bool = False
    objections_handled: list = field(default_factory=list)
    call_duration_seconds: int = 0
    recording_url: Optional[str] = None


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
    
    def __init__(self):
        self.stt = SpeechToText()
        self.tts = TextToSpeech()
        self.llm = LLMBrain()
        self.intent_detector = IntentDetector()
        self.active_calls: Dict[str, CallContext] = {}
        
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
        context = self.active_calls.get(call_id)
        if not context:
            raise ValueError(f"Call {call_id} not found")
        
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
    
    async def process_speech(
        self,
        call_id: str,
        audio_data: bytes,
        audio_format: str = "wav"
    ) -> str:
        """Process incoming speech and generate response"""
        context = self.active_calls.get(call_id)
        if not context:
            raise ValueError(f"Call {call_id} not found")
        
        # 1. Convert speech to text
        user_text = await self.stt.transcribe(audio_data, audio_format)
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
        
        logger.info(f"🤖 Agent response: {response}")
        return response
    
    async def text_to_audio(self, text: str, voice_id: Optional[str] = None) -> bytes:
        """Convert text response to audio"""
        return await self.tts.synthesize(text, voice_id)
    
    async def _handle_opt_out(self, context: CallContext) -> str:
        """Handle opt-out request"""
        context.status = CallStatus.COMPLETED
        return "I understand. We will remove your number from our calling list. Thank you for your time. Goodbye!"
    
    async def _handle_callback_request(self, context: CallContext) -> str:
        """Handle callback request"""
        context.callback_requested = True
        return "Certainly! I will arrange for a callback at your convenience. Could you please tell me your preferred time for the callback?"
    
    async def _handle_appointment(self, context: CallContext) -> str:
        """Handle appointment booking interest"""
        context.appointment_scheduled = True
        return "Great! I would be happy to schedule a meeting for you. What day and time works best for you?"
    
    async def end_call(self, call_id: str) -> Dict[str, Any]:
        """End a call and return summary"""
        context = self.active_calls.get(call_id)
        if not context:
            raise ValueError(f"Call {call_id} not found")
        
        context.status = CallStatus.COMPLETED
        
        # Generate call summary
        summary = {
            "call_id": call_id,
            "lead_id": context.lead_id,
            "phone_number": context.phone_number,
            "status": context.status.value,
            "duration_seconds": context.call_duration_seconds,
            "detected_intent": context.detected_intent,
            "appointment_scheduled": context.appointment_scheduled,
            "callback_requested": context.callback_requested,
            "qualification_answers": context.qualification_answers,
            "conversation_transcript": context.conversation_history,
            "recording_url": context.recording_url
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
