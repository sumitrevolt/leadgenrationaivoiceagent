"""
Provider Registry (BYOK) — Dograh/Vapi-inspired pluggable provider layer.

This module gives the streaming voice pipeline ONE uniform way to grab a ready
STT / TTS / LLM provider, no matter which underlying engine is configured. It
wraps the EXISTING project classes (free_stt.py, tts.py, llm_brain.py) behind 3
thin interfaces so the pipeline never has to know provider-specific details:

    STTProvider.transcribe(audio) -> str          (+ transcribe_stream)
    TTSProvider.synthesize(text)  -> bytes         (+ synthesize_stream)
    LLMProvider.complete(messages)-> str

BYOK = "Bring Your Own Keys": the active provider is chosen from env vars
(STT_PROVIDER / TTS_PROVIDER / LLM_PROVIDER) with FREE, safe defaults
(vosk/whisper, edge-tts, gemini). Anything that fails to construct degrades to
a Mock provider, so `get_registry()` NEVER hard-crashes — it always returns
working instances. This makes pure-text testing possible with zero external
services.

Extensibility:
    Use `register(kind, name, factory)` to plug in a brand-new engine without
    touching this file's selection logic.

Usage example (pure text mode, no audio / no API keys needed)::

    import asyncio
    from app.voice_agent.providers import get_registry

    async def main():
        reg = get_registry()                       # honors env, Mock fallback
        stt = reg.get_stt()
        tts = reg.get_tts()
        llm = reg.get_llm()

        text = await stt.transcribe(b"")           # Mock -> canned user line
        reply = await llm.complete([{"role": "user", "content": text}])
        audio = await tts.synthesize(reply)        # bytes (may be b"" on Mock)
        print("user:", text, "| bot:", reply, "| audio bytes:", len(audio))

    asyncio.run(main())
"""

import os
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from typing import (
    Any,
)

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# UNIFORM PROVIDER INTERFACES
# =============================================================================
# These 3 abstract interfaces are the ONLY contract the pipeline depends on.
# Concrete wrappers below adapt the existing project classes to these shapes.


class STTProvider(ABC):
    """Uniform Speech-to-Text interface used by the pipeline."""

    name: str = "stt"

    @abstractmethod
    async def transcribe(self, audio: bytes, **kwargs) -> str:
        """Transcribe a chunk/blob of audio bytes to text."""
        raise NotImplementedError

    async def transcribe_stream(
        self, audio_stream: AsyncGenerator[bytes, None], **kwargs
    ) -> AsyncGenerator[str, None]:
        """Stream partial/final transcripts. Default: buffer then transcribe once."""
        buffer = bytearray()
        async for chunk in audio_stream:
            buffer.extend(chunk)
        text = await self.transcribe(bytes(buffer), **kwargs)
        if text:
            yield text


class TTSProvider(ABC):
    """Uniform Text-to-Speech interface used by the pipeline."""

    name: str = "tts"

    @abstractmethod
    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes:
        """Synthesize text into audio bytes."""
        raise NotImplementedError

    async def synthesize_stream(
        self, text: str, voice_id: str | None = None
    ) -> AsyncGenerator[bytes, None]:
        """Stream audio chunks. Default: synthesize fully then yield once."""
        audio = await self.synthesize(text, voice_id)
        if audio:
            yield audio


class LLMProvider(ABC):
    """Uniform LLM interface used by the pipeline."""

    name: str = "llm"

    @abstractmethod
    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        """Complete a chat given OpenAI-style messages -> assistant text."""
        raise NotImplementedError


# =============================================================================
# MOCK PROVIDERS (zero-dependency fallback — always work)
# =============================================================================


class MockSTT(STTProvider):
    """Deterministic mock STT — cycles canned user lines, no deps."""

    name = "mock-stt"

    _LINES = [
        "Hello, I am interested in your services",
        "What are your pricing options?",
        "I would like to schedule a meeting",
        "Can you tell me more about lead generation?",
        "Yes, that sounds good",
        "Thank you for the information",
    ]

    def __init__(self) -> None:
        self._i = 0

    async def transcribe(self, audio: bytes, **kwargs) -> str:
        # If raw text was smuggled in as bytes, just decode it (text-mode helper).
        if audio:
            try:
                decoded = audio.decode("utf-8")
                if decoded.strip():
                    return decoded.strip()
            except Exception:
                pass
        line = self._LINES[self._i % len(self._LINES)]
        self._i += 1
        return line


class MockTTS(TTSProvider):
    """Mock TTS — returns deterministic fake audio bytes, no deps."""

    name = "mock-tts"

    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes:
        # Encode the text so callers/tests can assert on it; not real audio.
        return f"[MOCK_AUDIO:{text}]".encode()


class MockLLM(LLMProvider):
    """Mock LLM — echoes a canned, on-brand sales reply, no deps."""

    name = "mock-llm"

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        last_user = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last_user = m.get("content", "")
                break
        if not last_user:
            return "Hello! Thanks for taking my call. How are you today?"
        return (
            f"I understand you said '{last_user}'. That's great — "
            "would you be open to a quick 5-minute chat so I can show you how we help?"
        )


# =============================================================================
# CONCRETE WRAPPERS AROUND EXISTING PROJECT CLASSES
# =============================================================================


class FreeSTTWrapper(STTProvider):
    """
    Wraps the existing FreeSTTManager (free_stt.py) which auto-selects the best
    free offline engine (Vosk -> Whisper -> SpeechRecognition -> Mock).
    """

    name = "free-stt"

    def __init__(self) -> None:
        # Imported lazily so this module stays import-safe even if free_stt has
        # optional heavy deps in the future.
        from app.voice_agent.free_stt import FreeSTTManager

        self._manager = FreeSTTManager()
        self._ready = False

    async def _ensure(self) -> None:
        if not self._ready:
            await self._manager.initialize()
            self._ready = True

    async def transcribe(self, audio: bytes, **kwargs) -> str:
        await self._ensure()
        return await self._manager.transcribe(audio, **kwargs)

    async def transcribe_stream(
        self, audio_stream: AsyncGenerator[bytes, None], **kwargs
    ) -> AsyncGenerator[str, None]:
        await self._ensure()
        async for text in self._manager.transcribe_stream(audio_stream, **kwargs):
            yield text


class EdgeTTSWrapper(TTSProvider):
    """
    Wraps the existing TextToSpeech (tts.py). Defaults to the free EdgeTTS
    provider but honors whatever `provider` name is passed (edge/elevenlabs/azure).
    """

    name = "edge-tts"

    def __init__(self, provider: str = "edge") -> None:
        from app.voice_agent.tts import TextToSpeech

        self._tts = TextToSpeech(provider=provider)
        self.name = f"{provider}-tts"

    async def synthesize(self, text: str, voice_id: str | None = None) -> bytes:
        return await self._tts.synthesize(text, voice_id=voice_id)

    async def synthesize_stream(
        self, text: str, voice_id: str | None = None
    ) -> AsyncGenerator[bytes, None]:
        async for chunk in self._tts.synthesize_stream(text, voice_id=voice_id):
            yield chunk


class LLMBrainWrapper(LLMProvider):
    """
    Wraps the existing LLMBrain (llm_brain.py) and exposes a simple
    `complete(messages)` over its internal chat generation.
    """

    name = "llm-brain"

    def __init__(self, model: str | None = None, tenant_id: str | None = None) -> None:
        from app.voice_agent.llm_brain import LLMBrain

        self._brain = LLMBrain(model=model, tenant_id=tenant_id)
        self.name = f"llm-{self._brain.model}"

    async def complete(self, messages: list[dict[str, str]], **kwargs) -> str:
        system_prompt = kwargs.get("system_prompt", "")
        # Pull out any explicit system message if present.
        chat: list[dict[str, str]] = []
        for m in messages:
            if m.get("role") == "system":
                system_prompt = (system_prompt + "\n" + m.get("content", "")).strip()
            else:
                chat.append(m)
        if not system_prompt:
            system_prompt = (
                "You are a friendly, concise AI sales agent. Respond naturally "
                "in 1-2 sentences. Hinglish is fine."
            )
        # Reuse the brain's internal chat generator.
        return await self._brain._generate_chat(system_prompt, chat)


# =============================================================================
# REGISTRY
# =============================================================================

ProviderFactory = Callable[[], Any]


class ProviderRegistry:
    """
    BYOK provider registry.

    Selection order for each kind:
        1. Explicit env var (STT_PROVIDER / TTS_PROVIDER / LLM_PROVIDER)
        2. Safe free default
        3. Mock fallback (guaranteed to construct)

    Built instances are cached so repeated get_*() calls are cheap. Register new
    engines via `register(kind, name, factory)`.
    """

    KINDS = ("stt", "tts", "llm")

    # Safe free defaults per kind.
    DEFAULTS = {
        "stt": "free",  # Vosk/Whisper/SpeechRecognition auto via FreeSTTManager
        "tts": "edge",  # EdgeTTS (free)
        "llm": "gemini",  # Gemini (free tier friendly)
    }

    def __init__(self) -> None:
        # kind -> { name -> factory }
        self._factories: dict[str, dict[str, ProviderFactory]] = {
            "stt": {},
            "tts": {},
            "llm": {},
        }
        # kind -> cached active instance
        self._cache: dict[str, Any] = {}
        self._register_builtins()

    # -- registration ------------------------------------------------------

    def register(self, kind: str, name: str, factory: ProviderFactory) -> None:
        """
        Register a provider factory under (kind, name).

        Args:
            kind: one of "stt", "tts", "llm".
            name: lookup key matched against the *_PROVIDER env var.
            factory: zero-arg callable returning a provider instance.
        """
        kind = kind.lower()
        if kind not in self._factories:
            raise ValueError(f"Unknown provider kind: {kind!r}. Use one of {self.KINDS}")
        self._factories[kind][name.lower()] = factory
        # Invalidate cache for this kind in case the active provider changed.
        self._cache.pop(kind, None)
        logger.debug(f"Registered {kind} provider: {name}")

    def _register_builtins(self) -> None:
        """Register the built-in wrappers + mock fallbacks."""
        # STT
        self.register("stt", "free", FreeSTTWrapper)
        self.register("stt", "vosk", FreeSTTWrapper)
        self.register("stt", "whisper", FreeSTTWrapper)
        self.register("stt", "mock", MockSTT)

        # TTS
        self.register("tts", "edge", lambda: EdgeTTSWrapper(provider="edge"))
        self.register("tts", "edge-tts", lambda: EdgeTTSWrapper(provider="edge"))
        self.register("tts", "elevenlabs", lambda: EdgeTTSWrapper(provider="elevenlabs"))
        self.register("tts", "azure", lambda: EdgeTTSWrapper(provider="azure"))
        self.register("tts", "mock", MockTTS)

        # LLM
        self.register("llm", "gemini", lambda: LLMBrainWrapper(model="gemini-1.5-flash"))
        self.register("llm", "gpt", lambda: LLMBrainWrapper(model="gpt-4o"))
        self.register("llm", "openai", lambda: LLMBrainWrapper(model="gpt-4o"))
        self.register("llm", "claude", lambda: LLMBrainWrapper(model="claude-3-opus"))
        self.register("llm", "anthropic", lambda: LLMBrainWrapper(model="claude-3-opus"))
        self.register("llm", "vertex", lambda: LLMBrainWrapper(model="vertex-gemini-1.5-flash"))
        self.register("llm", "local", lambda: LLMBrainWrapper(model="local-llama"))
        self.register("llm", "mock", MockLLM)

    # -- selection ---------------------------------------------------------

    _ENV_VARS = {
        "stt": "STT_PROVIDER",
        "tts": "TTS_PROVIDER",
        "llm": "LLM_PROVIDER",
    }

    _MOCKS = {
        "stt": MockSTT,
        "tts": MockTTS,
        "llm": MockLLM,
    }

    def _select_name(self, kind: str) -> str:
        """Resolve the configured provider name for a kind (env -> default)."""
        env_name = os.getenv(self._ENV_VARS[kind])
        if env_name and env_name.strip():
            return env_name.strip().lower()
        return self.DEFAULTS[kind]

    def _build(self, kind: str) -> Any:
        """Build (and cache) the active provider for a kind, with Mock fallback."""
        if kind in self._cache:
            return self._cache[kind]

        name = self._select_name(kind)
        factory = self._factories[kind].get(name)

        instance: Any = None
        if factory is None:
            logger.warning(
                f"{kind.upper()} provider '{name}' not registered; falling back to Mock."
            )
        else:
            try:
                instance = factory()
                logger.info(f"✅ {kind.upper()} provider active: {name}")
            except Exception as e:
                logger.warning(
                    f"{kind.upper()} provider '{name}' failed to init ({e}); falling back to Mock."
                )
                instance = None

        if instance is None:
            instance = self._MOCKS[kind]()
            logger.warning(f"⚠️ Using Mock {kind.upper()} provider.")

        self._cache[kind] = instance
        return instance

    def get_stt(self) -> STTProvider:
        """Return the active STT provider instance (cached)."""
        return self._build("stt")

    def get_tts(self) -> TTSProvider:
        """Return the active TTS provider instance (cached)."""
        return self._build("tts")

    def get_llm(self) -> LLMProvider:
        """Return the active LLM provider instance (cached)."""
        return self._build("llm")

    def reset(self) -> None:
        """Clear cached instances (e.g. after changing env)."""
        self._cache.clear()

    def describe(self) -> dict[str, str]:
        """Return the resolved provider name per kind (for diagnostics)."""
        return {kind: self._select_name(kind) for kind in self.KINDS}


# =============================================================================
# MODULE SINGLETON
# =============================================================================

_registry: ProviderRegistry | None = None


def get_registry() -> ProviderRegistry:
    """Get the process-wide ProviderRegistry singleton (lazy)."""
    global _registry
    if _registry is None:
        _registry = ProviderRegistry()
    return _registry
