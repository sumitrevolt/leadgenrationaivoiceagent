"""
Free STT (Speech-to-Text) Providers - No API keys required.

Supports:
1. Vosk - Fully OFFLINE, lightweight, 40+ languages
2. Whisper - OpenAI's model, runs locally (via faster-whisper)
3. SpeechRecognition - Uses Google's free web API
4. Mock STT - For testing
"""

import asyncio
import io
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import AsyncGenerator, Optional, Dict, Any, List
import wave

from app.utils.logger import get_logger

logger = get_logger(__name__)


class BaseSTTProvider(ABC):
    """Base class for STT providers."""
    
    @abstractmethod
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Transcribe audio to text."""
        pass
    
    @abstractmethod
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream transcription."""
        pass


class VoskProvider(BaseSTTProvider):
    """
    Vosk - Fully OFFLINE speech recognition.
    
    Features:
    - Completely offline (no internet required)
    - Small models (50MB) to large (1.5GB)
    - 40+ languages
    - Real-time streaming
    
    Install: pip install vosk
    
    Download models from: https://alphacephei.com/vosk/models
    Recommended: vosk-model-small-en-in-0.4 (Indian English, 36MB)
    """
    
    MODEL_URLS = {
        "en-in": "https://alphacephei.com/vosk/models/vosk-model-small-en-in-0.4.zip",
        "en-us": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "hi": "https://alphacephei.com/vosk/models/vosk-model-small-hi-0.22.zip",
    }
    
    def __init__(self, model_path: Optional[str] = None, sample_rate: int = 16000):
        self.model_path = model_path or os.getenv("VOSK_MODEL_PATH", "models/vosk")
        self.sample_rate = sample_rate
        self._model = None
        self._recognizer = None
    
    async def download_model(self, language: str = "en-in") -> str:
        """Download a Vosk model."""
        import zipfile
        import httpx
        
        url = self.MODEL_URLS.get(language)
        if not url:
            raise ValueError(f"Unknown language: {language}")
        
        model_dir = Path(self.model_path)
        model_dir.mkdir(parents=True, exist_ok=True)
        
        zip_path = model_dir / f"{language}.zip"
        
        logger.info(f"Downloading Vosk model for {language}...")
        async with httpx.AsyncClient() as client:
            response = await client.get(url, follow_redirects=True)
            with open(zip_path, 'wb') as f:
                f.write(response.content)
        
        # Extract
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(model_dir)
        
        zip_path.unlink()
        logger.info(f"✅ Vosk model downloaded to {model_dir}")
        
        # Find extracted folder
        for item in model_dir.iterdir():
            if item.is_dir() and "vosk" in item.name.lower():
                return str(item)
        
        return str(model_dir)
    
    def _get_model(self):
        """Get or create Vosk model."""
        if self._model is None:
            try:
                from vosk import Model, KaldiRecognizer
                
                model_path = Path(self.model_path)
                if not model_path.exists():
                    raise FileNotFoundError(f"Vosk model not found at {model_path}")
                
                # Find the actual model directory
                for item in model_path.iterdir():
                    if item.is_dir():
                        model_path = item
                        break
                
                self._model = Model(str(model_path))
                logger.info(f"✅ Vosk model loaded from {model_path}")
            except Exception as e:
                logger.error(f"Failed to load Vosk model: {e}")
                raise
        return self._model
    
    def _get_recognizer(self):
        """Get or create Vosk recognizer."""
        if self._recognizer is None:
            from vosk import KaldiRecognizer
            self._recognizer = KaldiRecognizer(self._get_model(), self.sample_rate)
        return self._recognizer
    
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Transcribe audio using Vosk."""
        try:
            import json
            from vosk import KaldiRecognizer
            
            model = self._get_model()
            recognizer = KaldiRecognizer(model, self.sample_rate)
            
            # Process audio
            loop = asyncio.get_event_loop()
            
            def _process():
                recognizer.AcceptWaveform(audio_data)
                result = json.loads(recognizer.FinalResult())
                return result.get("text", "")
            
            return await loop.run_in_executor(None, _process)
            
        except Exception as e:
            logger.error(f"Vosk transcription failed: {e}")
            return ""
    
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream transcription with Vosk (real-time!)."""
        try:
            import json
            from vosk import KaldiRecognizer
            
            model = self._get_model()
            recognizer = KaldiRecognizer(model, self.sample_rate)
            
            async for chunk in audio_stream:
                if recognizer.AcceptWaveform(chunk):
                    result = json.loads(recognizer.Result())
                    text = result.get("text", "")
                    if text:
                        yield text
                else:
                    # Partial result
                    partial = json.loads(recognizer.PartialResult())
                    partial_text = partial.get("partial", "")
                    if partial_text:
                        yield f"[partial] {partial_text}"
            
            # Final result
            final = json.loads(recognizer.FinalResult())
            if final.get("text"):
                yield final["text"]
                
        except Exception as e:
            logger.error(f"Vosk streaming failed: {e}")


class WhisperProvider(BaseSTTProvider):
    """
    Whisper - OpenAI's speech recognition, runs LOCALLY.
    
    Uses faster-whisper for optimized inference.
    
    Models:
    - tiny: 39M params, fastest
    - base: 74M params, good balance
    - small: 244M params, better accuracy
    - medium: 769M params, high accuracy
    - large: 1.5B params, best accuracy
    
    Install: pip install faster-whisper
    """
    
    def __init__(
        self,
        model_size: str = "base",
        device: str = "auto",
        compute_type: str = "auto"
    ):
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model = None
    
    def _get_model(self):
        """Get or create Whisper model."""
        if self._model is None:
            try:
                from faster_whisper import WhisperModel
                
                # Auto-detect device
                device = self.device
                compute_type = self.compute_type
                
                if device == "auto":
                    try:
                        import torch
                        device = "cuda" if torch.cuda.is_available() else "cpu"
                    except ImportError:
                        device = "cpu"
                
                if compute_type == "auto":
                    compute_type = "float16" if device == "cuda" else "int8"
                
                logger.info(f"Loading Whisper {self.model_size} on {device}...")
                self._model = WhisperModel(
                    self.model_size,
                    device=device,
                    compute_type=compute_type
                )
                logger.info(f"✅ Whisper model loaded")
                
            except Exception as e:
                logger.error(f"Failed to load Whisper: {e}")
                raise
        return self._model
    
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Transcribe audio using Whisper."""
        try:
            # Save to temp file (Whisper needs file path)
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            try:
                model = self._get_model()
                loop = asyncio.get_event_loop()
                
                def _transcribe():
                    segments, info = model.transcribe(
                        temp_path,
                        language=kwargs.get('language'),
                        beam_size=kwargs.get('beam_size', 5)
                    )
                    return " ".join(segment.text for segment in segments)
                
                result = await loop.run_in_executor(None, _transcribe)
                return result.strip()
                
            finally:
                os.unlink(temp_path)
                
        except Exception as e:
            logger.error(f"Whisper transcription failed: {e}")
            return ""
    
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream transcription (Whisper processes in chunks)."""
        # Collect audio chunks and process periodically
        buffer = bytearray()
        chunk_duration = kwargs.get('chunk_duration', 3.0)  # seconds
        sample_rate = kwargs.get('sample_rate', 16000)
        chunk_size = int(chunk_duration * sample_rate * 2)  # 16-bit audio
        
        async for chunk in audio_stream:
            buffer.extend(chunk)
            
            if len(buffer) >= chunk_size:
                # Create WAV from buffer
                wav_data = self._create_wav(bytes(buffer), sample_rate)
                text = await self.transcribe(wav_data, **kwargs)
                if text:
                    yield text
                buffer.clear()
        
        # Process remaining audio
        if buffer:
            wav_data = self._create_wav(bytes(buffer), sample_rate)
            text = await self.transcribe(wav_data, **kwargs)
            if text:
                yield text
    
    def _create_wav(self, audio_data: bytes, sample_rate: int) -> bytes:
        """Create WAV file from raw audio."""
        buffer = io.BytesIO()
        with wave.open(buffer, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(audio_data)
        buffer.seek(0)
        return buffer.read()


class SpeechRecognitionProvider(BaseSTTProvider):
    """
    SpeechRecognition - Uses free online APIs.
    
    Backends:
    - Google Web Speech API (free, default)
    - Sphinx (offline, less accurate)
    
    Install: pip install SpeechRecognition
    """
    
    def __init__(self, language: str = "en-IN"):
        self.language = language
    
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Transcribe using SpeechRecognition."""
        try:
            import speech_recognition as sr
            
            recognizer = sr.Recognizer()
            
            # Create AudioData from bytes
            # Assuming 16-bit, 16kHz mono audio
            sample_rate = kwargs.get('sample_rate', 16000)
            sample_width = kwargs.get('sample_width', 2)
            
            audio = sr.AudioData(audio_data, sample_rate, sample_width)
            
            loop = asyncio.get_event_loop()
            
            def _recognize():
                try:
                    # Try Google (free, requires internet)
                    return recognizer.recognize_google(
                        audio,
                        language=self.language
                    )
                except sr.UnknownValueError:
                    return ""
                except sr.RequestError:
                    # Fall back to Sphinx (offline)
                    try:
                        return recognizer.recognize_sphinx(audio)
                    except Exception:
                        return ""
            
            return await loop.run_in_executor(None, _recognize)
            
        except Exception as e:
            logger.error(f"SpeechRecognition failed: {e}")
            return ""
    
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream transcription (processes in chunks)."""
        buffer = bytearray()
        chunk_size = kwargs.get('chunk_size', 32000)  # ~1 second at 16kHz
        
        async for chunk in audio_stream:
            buffer.extend(chunk)
            
            if len(buffer) >= chunk_size:
                text = await self.transcribe(bytes(buffer), **kwargs)
                if text:
                    yield text
                buffer.clear()
        
        if buffer:
            text = await self.transcribe(bytes(buffer), **kwargs)
            if text:
                yield text


class MockSTTProvider(BaseSTTProvider):
    """
    Mock STT for testing - No external dependencies.
    
    Returns predefined responses for testing.
    """
    
    MOCK_RESPONSES = [
        "Hello, I am interested in your services",
        "What are your pricing options?",
        "I would like to schedule a meeting",
        "Can you tell me more about lead generation?",
        "Yes, that sounds good",
        "Thank you for the information",
    ]
    
    def __init__(self):
        import random
        self.random = random
        self._index = 0
    
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Return mock transcription."""
        await asyncio.sleep(0.1)  # Simulate processing
        response = self.MOCK_RESPONSES[self._index % len(self.MOCK_RESPONSES)]
        self._index += 1
        return response
    
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream mock transcription."""
        async for _ in audio_stream:
            pass  # Consume stream
        yield await self.transcribe(b"")


class FreeSTTManager:
    """
    Manages multiple free STT providers with automatic fallback.
    
    Priority order:
    1. Vosk (fully offline, real-time)
    2. Whisper (offline, high accuracy)
    3. SpeechRecognition (requires internet)
    4. Mock (always available)
    """
    
    def __init__(self):
        self.providers: Dict[str, BaseSTTProvider] = {}
        self.active_provider: Optional[str] = None
    
    async def initialize(self) -> str:
        """Initialize and find the best available provider."""
        
        # Try Vosk first (offline, real-time)
        try:
            from vosk import Model
            vosk_path = os.getenv("VOSK_MODEL_PATH", "models/vosk")
            if Path(vosk_path).exists():
                provider = VoskProvider(model_path=vosk_path)
                provider._get_model()  # Test loading
                self.providers["vosk"] = provider
                self.active_provider = "vosk"
                logger.info("✅ Using Vosk (offline, real-time STT)")
                return "vosk"
        except Exception as e:
            logger.debug(f"Vosk not available: {e}")
        
        # Try Whisper (offline, high accuracy)
        try:
            from faster_whisper import WhisperModel
            provider = WhisperProvider(model_size="base")
            self.providers["whisper"] = provider
            self.active_provider = "whisper"
            logger.info("✅ Using Whisper (offline, high accuracy)")
            return "whisper"
        except Exception as e:
            logger.debug(f"Whisper not available: {e}")
        
        # Try SpeechRecognition (requires internet)
        try:
            import speech_recognition
            provider = SpeechRecognitionProvider()
            self.providers["speech_recognition"] = provider
            self.active_provider = "speech_recognition"
            logger.info("✅ Using SpeechRecognition (Google free API)")
            return "speech_recognition"
        except Exception as e:
            logger.debug(f"SpeechRecognition not available: {e}")
        
        # Fall back to mock
        self.providers["mock"] = MockSTTProvider()
        self.active_provider = "mock"
        logger.warning("⚠️ Using Mock STT (for testing only)")
        return "mock"
    
    def get_provider(self) -> BaseSTTProvider:
        """Get the active provider."""
        if not self.active_provider:
            raise RuntimeError("STT Manager not initialized")
        return self.providers[self.active_provider]
    
    async def transcribe(self, audio_data: bytes, **kwargs) -> str:
        """Transcribe audio using active provider."""
        return await self.get_provider().transcribe(audio_data, **kwargs)
    
    async def transcribe_stream(self, audio_stream: AsyncGenerator[bytes, None], **kwargs) -> AsyncGenerator[str, None]:
        """Stream transcription."""
        async for text in self.get_provider().transcribe_stream(audio_stream, **kwargs):
            yield text


# Global instance
free_stt = FreeSTTManager()


async def get_free_stt() -> FreeSTTManager:
    """Get initialized free STT manager."""
    if not free_stt.active_provider:
        await free_stt.initialize()
    return free_stt
