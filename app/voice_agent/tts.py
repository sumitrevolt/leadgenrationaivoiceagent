"""
Text-to-Speech Module
Supports ElevenLabs, Azure Neural Voice, and EdgeTTS (Free)
"""
import asyncio
from typing import Optional
from abc import ABC, abstractmethod
import httpx
import edge_tts
import io

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TTSProvider(ABC):
    """Abstract base class for TTS providers"""
    
    @abstractmethod
    async def synthesize(self, text: str, voice_id: Optional[str] = None) -> bytes:
        pass


class ElevenLabsTTS(TTSProvider):
    """ElevenLabs Text-to-Speech provider - Natural human-like voice"""
    
    def __init__(self):
        self.api_key = settings.elevenlabs_api_key
        self.default_voice_id = settings.elevenlabs_voice_id
        self.base_url = "https://api.elevenlabs.io/v1"
        
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        model_id: str = "eleven_multilingual_v2"
    ) -> bytes:
        """
        Synthesize text to speech using ElevenLabs
        
        Args:
            text: Text to convert to speech
            voice_id: ElevenLabs voice ID (uses default if not provided)
            model_id: Model to use (eleven_multilingual_v2 for Hindi support)
            
        Returns:
            Audio bytes (mp3 format)
        """
        if not self.api_key:
            raise ValueError("ElevenLabs API key not configured")
        
        voice = voice_id or self.default_voice_id
        if not voice:
            raise ValueError("No voice ID provided")
        
        headers = {
            "Accept": "audio/mpeg",
            "Content-Type": "application/json",
            "xi-api-key": self.api_key
        }
        
        payload = {
            "text": text,
            "model_id": model_id,
            "voice_settings": {
                "stability": 0.5,
                "similarity_boost": 0.8,
                "style": 0.0,
                "use_speaker_boost": True
            }
        }
        
        url = f"{self.base_url}/text-to-speech/{voice}"
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                json=payload,
                timeout=30.0
            )
            response.raise_for_status()
            
            logger.debug(f"ElevenLabs TTS generated {len(response.content)} bytes")
            return response.content


class AzureTTS(TTSProvider):
    """Azure Neural Voice Text-to-Speech provider"""
    
    def __init__(self):
        self.api_key = settings.azure_speech_key
        self.region = settings.azure_speech_region
        
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        language: str = "hi-IN"
    ) -> bytes:
        """
        Synthesize text to speech using Azure Neural Voice
        
        Args:
            text: Text to convert to speech
            voice_id: Azure voice name (e.g., hi-IN-SwaraNeural)
            language: Language code
            
        Returns:
            Audio bytes (wav format)
        """
        if not self.api_key:
            raise ValueError("Azure Speech key not configured")
        
        # Default Indian Hindi female voice
        voice_name = voice_id or "hi-IN-SwaraNeural"
        
        # Create SSML
        ssml = f"""
        <speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' 
               xmlns:mstts='https://www.w3.org/2001/mstts' xml:lang='{language}'>
            <voice name='{voice_name}'>
                <mstts:express-as style='friendly'>
                    {text}
                </mstts:express-as>
            </voice>
        </speak>
        """
        
        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-16khz-128kbitrate-mono-mp3"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                url,
                headers=headers,
                content=ssml,
                timeout=30.0
            )
            response.raise_for_status()
            
            logger.debug(f"Azure TTS generated {len(response.content)} bytes")
            return response.content


class EdgeTTS(TTSProvider):
    """
    Edge TTS provider (Free)
    Uses Microsoft Edge's online TTS service
    """
    
    def __init__(self):
        self.default_voice = "en-IN-NeerjaNeural"
        
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None
    ) -> bytes:
        """
        Synthesize text to speech using Edge TTS
        """
        voice = voice_id or self.default_voice
        
        communicate = edge_tts.Communicate(text, voice)
        
        # Capture audio to memory
        audio_stream = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_stream.write(chunk["data"])
                
        logger.debug(f"Edge TTS generated {audio_stream.getbuffer().nbytes} bytes")
        return audio_stream.getvalue()


class TextToSpeech:
    """
    Unified Text-to-Speech interface
    Automatically selects provider based on configuration
    """
    
    # Available voice presets for different languages
    VOICE_PRESETS = {
        "hindi_female": {
            "elevenlabs": "pNInz6obpgDQGcFmaJgB",
            "azure": "hi-IN-SwaraNeural",
            "edge": "hi-IN-SwaraNeural"
        },
        "hindi_male": {
            "elevenlabs": "VR6AewLTigWG4xSOukaG",
            "azure": "hi-IN-MadhurNeural",
            "edge": "hi-IN-MadhurNeural"
        },
        "english_indian_female": {
            "elevenlabs": "21m00Tcm4TlvDq8ikWAM",
            "azure": "en-IN-NeerjaNeural",
            "edge": "en-IN-NeerjaNeural"
        },
        "english_indian_male": {
            "elevenlabs": "TxGEqnHWrfWFTfGW9XjX",
            "azure": "en-IN-PrabhatNeural",
            "edge": "en-IN-PrabhatNeural"
        }
    }
    
    def __init__(self, provider: Optional[str] = None):
        provider = provider or settings.default_tts
        
        if provider == "elevenlabs":
            self._provider = ElevenLabsTTS()
        elif provider == "azure":
            self._provider = AzureTTS()
        elif provider == "edge":
            self._provider = EdgeTTS()
        else:
            raise ValueError(f"Unknown TTS provider: {provider}")
        
        self.provider_name = provider
        logger.info(f"🔊 TTS initialized with: {provider}")
    
    async def synthesize(
        self,
        text: str,
        voice_id: Optional[str] = None,
        voice_preset: Optional[str] = None
    ) -> bytes:
        """
        Convert text to speech audio
        
        Args:
            text: Text to convert
            voice_id: Specific voice ID (provider-dependent)
            voice_preset: Named preset (hindi_female, english_indian_male, etc.)
            
        Returns:
            Audio bytes
        """
        # Resolve voice preset to voice_id
        if voice_preset and voice_preset in self.VOICE_PRESETS:
            voice_id = self.VOICE_PRESETS[voice_preset].get(self.provider_name)
        
        try:
            return await self._provider.synthesize(text, voice_id)
        except Exception as e:
            logger.error(f"TTS synthesis failed: {e}")
            raise
    
    async def synthesize_stream(
        self,
        text: str,
        voice_id: Optional[str] = None
    ):
        """
        Stream audio for real-time playback
        (Implementation depends on provider capabilities)
        """
        # For now, return full audio
        # TODO: Implement streaming for lower latency
        return await self.synthesize(text, voice_id)
