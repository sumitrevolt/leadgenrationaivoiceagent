"""
Twilio Integration
Handles outbound calls via Twilio
"""
import asyncio
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
import base64
import json

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


@dataclass
class TwilioCallResult:
    """Result of a Twilio call operation"""
    call_sid: str
    status: str
    direction: str
    from_number: str
    to_number: str
    duration: Optional[int]
    recording_url: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]


class TwilioHandler:
    """
    Twilio telephony handler
    
    Handles:
    - Outbound calls
    - Call control (answer, hangup, transfer)
    - Audio streaming (for AI voice)
    - Recording
    - Webhooks
    """
    
    def __init__(self):
        self.account_sid = settings.twilio_account_sid
        self.auth_token = settings.twilio_auth_token
        self.phone_number = settings.twilio_phone_number
        self.webhook_url = settings.twilio_webhook_url
        
        if self.account_sid and self.auth_token:
            try:
                from twilio.rest import Client
                from twilio.twiml.voice_response import VoiceResponse, Gather
                self.client = Client(self.account_sid, self.auth_token)
                self.VoiceResponse = VoiceResponse
                self.Gather = Gather
                logger.info("📞 Twilio Handler initialized")
            except ImportError:
                logger.error("Twilio package not installed")
                self.client = None
        else:
            logger.warning("Twilio credentials not configured")
            self.client = None
    
    async def make_call(
        self,
        to_number: str,
        call_id: str,
        webhook_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Initiate an outbound call
        
        Args:
            to_number: Phone number to call (E.164 format: +91XXXXXXXXXX)
            call_id: Internal call ID for tracking
            webhook_url: URL for call status webhooks
            
        Returns:
            Twilio Call SID if successful
        """
        if not self.client:
            raise ValueError("Twilio client not initialized")
        
        # Ensure number is in E.164 format
        if not to_number.startswith('+'):
            to_number = f"+91{to_number.lstrip('0')}"
        
        webhook = webhook_url or f"{self.webhook_url}/voice/{call_id}"
        status_callback = f"{self.webhook_url}/status/{call_id}"
        
        try:
            call = await asyncio.to_thread(
                self.client.calls.create,
                to=to_number,
                from_=self.phone_number,
                url=webhook,
                status_callback=status_callback,
                status_callback_event=['initiated', 'ringing', 'answered', 'completed'],
                record=True,
                machine_detection='Enable',
                machine_detection_timeout=5
            )
            
            logger.info(f"Call initiated: {call.sid} to {to_number}")
            return call.sid
            
        except Exception as e:
            logger.error(f"Failed to make call: {e}")
            raise
    
    async def hangup_call(self, call_sid: str) -> bool:
        """Hang up an active call"""
        if not self.client:
            return False
        
        try:
            await asyncio.to_thread(
                self.client.calls(call_sid).update,
                status='completed'
            )
            logger.info(f"Call {call_sid} hung up")
            return True
        except Exception as e:
            logger.error(f"Failed to hangup call: {e}")
            return False
    
    async def get_call_status(self, call_sid: str) -> Optional[TwilioCallResult]:
        """Get current status of a call"""
        if not self.client:
            return None
        
        try:
            call = await asyncio.to_thread(
                self.client.calls(call_sid).fetch
            )
            
            return TwilioCallResult(
                call_sid=call.sid,
                status=call.status,
                direction=call.direction,
                from_number=call.from_,
                to_number=call.to,
                duration=int(call.duration) if call.duration else None,
                recording_url=None,  # Fetch separately if needed
                error_code=call.error_code,
                error_message=call.error_message
            )
        except Exception as e:
            logger.error(f"Failed to get call status: {e}")
            return None
    
    def generate_voice_response(
        self,
        text: str,
        voice: str = "Polly.Aditi",  # Indian English voice
        gather_input: bool = False,
        gather_timeout: int = 5,
        gather_action: Optional[str] = None
    ) -> str:
        """
        Generate TwiML voice response
        
        Args:
            text: Text to speak
            voice: Twilio voice to use
            gather_input: Whether to gather DTMF/speech input
            gather_timeout: Timeout for input gathering
            gather_action: URL to post gathered input
        """
        response = self.VoiceResponse()
        
        if gather_input:
            gather = self.Gather(
                input='speech dtmf',
                timeout=gather_timeout,
                action=gather_action,
                speech_timeout='auto'
            )
            gather.say(text, voice=voice)
            response.append(gather)
        else:
            response.say(text, voice=voice)
        
        return str(response)
    
    def generate_stream_response(
        self,
        stream_url: str,
        initial_text: Optional[str] = None
    ) -> str:
        """
        Generate TwiML for audio streaming (for custom AI voice)
        
        Args:
            stream_url: WebSocket URL for audio streaming
            initial_text: Optional initial greeting
        """
        response = self.VoiceResponse()
        
        if initial_text:
            response.say(initial_text, voice="Polly.Aditi")
        
        # Start bidirectional stream
        from twilio.twiml.voice_response import Connect, Stream
        
        connect = Connect()
        stream = Stream(url=stream_url)
        connect.append(stream)
        response.append(connect)
        
        return str(response)
    
    async def play_audio(
        self,
        call_sid: str,
        audio_url: str
    ) -> bool:
        """Play an audio file on an active call"""
        if not self.client:
            return False
        
        try:
            await asyncio.to_thread(
                self.client.calls(call_sid).update,
                twiml=f'<Response><Play>{audio_url}</Play></Response>'
            )
            return True
        except Exception as e:
            logger.error(f"Failed to play audio: {e}")
            return False
    
    async def get_recording_url(self, call_sid: str) -> Optional[str]:
        """Get recording URL for a completed call"""
        if not self.client:
            return None
        
        try:
            recordings = await asyncio.to_thread(
                self.client.recordings.list,
                call_sid=call_sid
            )
            
            if recordings:
                return recordings[0].uri.replace('.json', '.mp3')
            return None
            
        except Exception as e:
            logger.error(f"Failed to get recording: {e}")
            return None


class TwilioWebhookHandler:
    """
    Handles Twilio webhook callbacks
    """
    
    def __init__(self, voice_agent):
        self.voice_agent = voice_agent
        self.handler = TwilioHandler()
    
    async def handle_voice_webhook(
        self,
        call_sid: str,
        call_id: str,
        speech_result: Optional[str] = None
    ) -> str:
        """
        Handle incoming voice webhook from Twilio
        
        Args:
            call_sid: Twilio call SID
            call_id: Internal call ID
            speech_result: Transcribed speech from caller
            
        Returns:
            TwiML response
        """
        if speech_result:
            # Process user speech and generate response
            response_text = await self.voice_agent.process_speech(
                call_id=call_id,
                audio_data=None,  # Speech already transcribed by Twilio
                transcribed_text=speech_result
            )
        else:
            # Initial call - get opening message
            response_text = await self.voice_agent.get_opening_message(call_id)
        
        # Generate TwiML with response and gather next input
        return self.handler.generate_voice_response(
            text=response_text,
            gather_input=True,
            gather_action=f"{settings.twilio_webhook_url}/voice/{call_id}"
        )
    
    async def handle_status_webhook(
        self,
        call_sid: str,
        call_id: str,
        status: str,
        duration: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Handle call status update webhook
        
        Args:
            call_sid: Twilio call SID
            call_id: Internal call ID
            status: Call status (initiated, ringing, in-progress, completed, etc.)
            duration: Call duration in seconds
        """
        logger.info(f"Call {call_id} status: {status}")
        
        if status == 'completed':
            # End call and get summary
            summary = await self.voice_agent.end_call(call_id)
            
            # Get recording URL
            recording_url = await self.handler.get_recording_url(call_sid)
            if recording_url:
                summary['recording_url'] = recording_url
            
            return summary
        
        return {"call_id": call_id, "status": status}
