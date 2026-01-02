"""
Speech-to-Text Module
Supports Deepgram and Google Cloud Speech
"""
import asyncio
from typing import Optional
from abc import ABC, abstractmethod
import httpx

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class STTProvider(ABC):
    """Abstract base class for STT providers"""
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes, audio_format: str = "wav") -> str:
        pass


class DeepgramSTT(STTProvider):
    """Deepgram Speech-to-Text provider"""
    
    def __init__(self):
        self.api_key = settings.deepgram_api_key
        self.base_url = "https://api.deepgram.com/v1/listen"
        
    async def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str = "hi-en"  # Hindi-English
    ) -> str:
        """Transcribe audio using Deepgram"""
        if not self.api_key:
            raise ValueError("Deepgram API key not configured")
        
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type": f"audio/{audio_format}"
        }
        
        params = {
            "model": "nova-2",
            "language": language,
            "smart_format": "true",
            "punctuate": "true",
            "diarize": "false",
            "utterances": "true"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.base_url,
                headers=headers,
                params=params,
                content=audio_data,
                timeout=30.0
            )
            response.raise_for_status()
            
            result = response.json()
            transcript = result.get("results", {}).get("channels", [{}])[0].get(
                "alternatives", [{}]
            )[0].get("transcript", "")
            
            logger.debug(f"Deepgram transcription: {transcript}")
            return transcript


class GoogleSTT(STTProvider):
    """Google Cloud Speech-to-Text provider"""
    
    def __init__(self):
        self.project_id = settings.google_cloud_project_id
        
    async def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: str = "hi-IN"
    ) -> str:
        """Transcribe audio using Google Cloud Speech"""
        try:
            from google.cloud import speech
        except ImportError:
            raise ImportError("google-cloud-speech not installed")
        
        client = speech.SpeechClient()
        
        audio = speech.RecognitionAudio(content=audio_data)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=language,
            alternative_language_codes=["en-IN"],  # Also detect English
            enable_automatic_punctuation=True,
        )
        
        response = await asyncio.to_thread(
            client.recognize, config=config, audio=audio
        )
        
        transcript = ""
        for result in response.results:
            transcript += result.alternatives[0].transcript
        
        logger.debug(f"Google STT transcription: {transcript}")
        return transcript


class SpeechToText:
    """
    Unified Speech-to-Text interface
    Automatically selects provider based on configuration
    """
    
    def __init__(self, provider: Optional[str] = None):
        provider = provider or settings.default_stt
        
        if provider == "deepgram":
            self._provider = DeepgramSTT()
        elif provider == "google":
            self._provider = GoogleSTT()
        else:
            raise ValueError(f"Unknown STT provider: {provider}")
        
        self.provider_name = provider
        logger.info(f"🎤 STT initialized with: {provider}")
    
    async def transcribe(
        self,
        audio_data: bytes,
        audio_format: str = "wav",
        language: Optional[str] = None
    ) -> str:
        """
        Transcribe audio to text
        
        Args:
            audio_data: Raw audio bytes
            audio_format: Audio format (wav, mp3, etc.)
            language: Language code (hi-IN, en-US, etc.)
            
        Returns:
            Transcribed text
        """
        try:
            return await self._provider.transcribe(audio_data, audio_format)
        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
            raise
