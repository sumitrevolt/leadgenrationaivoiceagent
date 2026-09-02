"""
VoicePipeline — Dograh/Vapi-inspired real-time streaming voice loop.

Implements the low-latency agent loop:

    audio-in -> VAD/endpointing -> STT -> LLM -> TTS -> audio-out

…with the two features that make these agents feel human:

  * BARGE-IN: if the user starts speaking while the bot is talking, the current
    TTS task is cancelled immediately (via an asyncio.Event `interrupt`), so the
    bot "shuts up" and listens. Call `interrupt_current()` to trigger it.
  * ENDPOINTING / VAD: `_detect_end_of_turn` decides when the user has finished
    speaking — using audio energy + a silence timeout (and, in text mode, simple
    punctuation / non-empty heuristics) so a turn can be processed.

It pulls its STT / TTS / LLM from `providers.get_registry()` (BYOK, Mock-safe),
and OPTIONALLY drives a `flow_engine` if one exists in the project — imported
lazily so its absence is fine; we fall back to free-form LLM turns.

Everything is defensive: provider calls are wrapped in try/except and degrade to
Mock-ish behavior rather than crashing. Per-turn latency is tracked in
`TurnMetrics` (stt_ms / llm_ms / tts_ms).

The pipeline runs in PURE TEXT MODE with zero external services — feed strings,
get strings back — so it is testable without any audio stack.

Usage example (pure text mode)::

    import asyncio
    from app.voice_agent.pipeline import VoicePipeline

    async def main():
        pipe = VoicePipeline(system_prompt="You sell solar. Be brief.")

        # Single turn: text in -> reply text out
        reply, metrics = await pipe.run_turn("Hi, what do you offer?")
        print("BOT:", reply)
        print("latency:", metrics.as_dict())

        # Streaming loop over a list of user utterances (audio_source can be any
        # async iterable of str or bytes):
        async def user_lines():
            for line in ["Tell me pricing", "Okay, book a demo"]:
                yield line

        async for bot_reply in pipe.stream(user_lines()):
            print("BOT:", bot_reply)

    asyncio.run(main())
"""

import asyncio
import time
from collections.abc import AsyncGenerator, AsyncIterable
from dataclasses import dataclass, field
from typing import (
    Any,
    Union,
)

from app.utils.logger import setup_logger
from app.voice_agent.providers import (
    LLMProvider,
    STTProvider,
    TTSProvider,
    get_registry,
)

logger = setup_logger(__name__)

# A pipeline input can be raw audio bytes OR a text string (text mode).
AudioOrText = Union[bytes, str]


def _default_silence_s() -> float:
    """End-of-turn silence (seconds) — shares TURN_SILENCE_MS with the phone
    paths. Historical default 0.8 s if turn_detector is unimportable. Defensive:
    never raises (a missing module just yields the literal default)."""
    try:
        from app.voice_agent.turn_detector import turn_silence_ms

        return turn_silence_ms(800.0) / 1000.0
    except Exception:
        return 0.8


def _default_energy() -> int:
    """Avg-abs-amplitude 'silence' threshold for this pipeline's pure-Python VAD.
    This metric ≈ 0.6×RMS, so we scale the shared TURN_VAD_RMS to keep parity and
    fall back to the historical 500. Defensive (never raises)."""
    try:
        from app.voice_agent.turn_detector import turn_vad_rms

        # avg-abs ≈ RMS for speech; keep the historical 500 floor so we never get
        # *more* eager than before unless the operator lowers TURN_VAD_RMS a lot.
        return max(1, int(turn_vad_rms(500)))
    except Exception:
        return 500


# =============================================================================
# METRICS & STATE
# =============================================================================


@dataclass
class TurnMetrics:
    """Latency breakdown for a single conversation turn (milliseconds)."""

    stt_ms: float = 0.0
    llm_ms: float = 0.0
    tts_ms: float = 0.0
    total_ms: float = 0.0
    barged_in: bool = False

    def as_dict(self) -> dict[str, float]:
        return {
            "stt_ms": round(self.stt_ms, 1),
            "llm_ms": round(self.llm_ms, 1),
            "tts_ms": round(self.tts_ms, 1),
            "total_ms": round(self.total_ms, 1),
            "barged_in": self.barged_in,
        }


@dataclass
class PipelineState:
    """Holds conversation history + (optional) flow-engine state for a session."""

    history: list[dict[str, str]] = field(default_factory=list)
    flow_state: dict[str, Any] = field(default_factory=dict)
    turn_count: int = 0
    last_metrics: TurnMetrics | None = None

    def add_user(self, text: str) -> None:
        self.history.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        self.history.append({"role": "assistant", "content": text})


# =============================================================================
# PIPELINE
# =============================================================================


class VoicePipeline:
    """
    Streaming voice agent loop with barge-in + endpointing.

    Args:
        system_prompt: optional system instruction for the LLM.
        registry: provider registry (defaults to the module singleton).
        silence_timeout_s: how long of silence (no new audio) ends a turn.
        energy_threshold: RMS-ish energy below which audio is "silence".
        use_flow_engine: try to drive app.voice_agent.flow_engine if available.
    """

    def __init__(
        self,
        system_prompt: str = "",
        registry: Any | None = None,
        silence_timeout_s: float | None = None,
        energy_threshold: int | None = None,
        use_flow_engine: bool = True,
        voice_id: str | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self._registry = registry or get_registry()
        # End-of-turn knobs: explicit args win; otherwise the shared env-tunable
        # defaults (TURN_SILENCE_MS / TURN_VAD_RMS) so this path tunes with the
        # phone paths. Falls back to the historical 0.8 s / 500 if unset/unimportable.
        self.silence_timeout_s = (
            silence_timeout_s if silence_timeout_s is not None else _default_silence_s()
        )
        self.energy_threshold = (
            energy_threshold if energy_threshold is not None else _default_energy()
        )
        self.voice_id = voice_id

        self.state = PipelineState()

        # Barge-in coordination: set => "interrupt the bot now".
        self.interrupt = asyncio.Event()
        self._tts_task: asyncio.Task | None = None

        # Endpointing bookkeeping (audio mode).
        self._silence_started: float | None = None

        # Lazy provider handles (built on first use, Mock-safe).
        self._stt: STTProvider | None = None
        self._tts: TTSProvider | None = None
        self._llm: LLMProvider | None = None

        # Optional flow engine (lazy / optional).
        self._flow = None
        self._flow_loaded = False
        self._use_flow_engine = use_flow_engine

    # -- lazy provider accessors ------------------------------------------

    @property
    def stt(self) -> STTProvider:
        if self._stt is None:
            self._stt = self._registry.get_stt()
        return self._stt

    @property
    def tts(self) -> TTSProvider:
        if self._tts is None:
            self._tts = self._registry.get_tts()
        return self._tts

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = self._registry.get_llm()
        return self._llm

    def _get_flow_engine(self):
        """
        Lazily import an optional flow engine. If app.voice_agent.flow_engine is
        absent or unusable, we silently fall back to free-form LLM turns.
        """
        if self._flow_loaded:
            return self._flow
        self._flow_loaded = True
        if not self._use_flow_engine:
            return None
        try:
            from app.voice_agent import flow_engine  # type: ignore

            # Try the most likely simple entry points; tolerate any shape.
            # NOTE: the project's `FlowRunner.step(flow, state, user_input)`
            # requires a pre-built ConversationFlow graph which this generic
            # pipeline does not own — so we deliberately do NOT auto-drive it
            # here and fall back to free-form LLM turns. A drop-in engine that
            # exposes one of the simple methods below WILL be driven.
            engine = None
            for attr in ("FlowEngine", "Flow", "get_flow_engine", "create_engine"):
                obj = getattr(flow_engine, attr, None)
                if obj is None:
                    continue
                engine = obj() if callable(obj) else obj
                break
            if engine is not None:
                logger.info("✅ Flow engine loaded for pipeline.")
            else:
                logger.debug(
                    "flow_engine present but no simple driver entry point; "
                    "using free-form LLM turns."
                )
            self._flow = engine
        except Exception as e:
            logger.debug(f"Flow engine not available, using free-form LLM: {e}")
            self._flow = None
        return self._flow

    # -- VAD / endpointing -------------------------------------------------

    @staticmethod
    def _audio_energy(chunk: bytes) -> float:
        """
        Cheap energy estimate over 16-bit PCM. Pure-stdlib (no numpy):
        average absolute sample amplitude. Returns 0 for empty/odd buffers.
        """
        if not chunk or len(chunk) < 2:
            return 0.0
        total = 0
        n = 0
        # Iterate as little-endian signed 16-bit samples.
        for i in range(0, len(chunk) - 1, 2):
            sample = int.from_bytes(chunk[i : i + 2], "little", signed=True)
            total += abs(sample)
            n += 1
        return (total / n) if n else 0.0

    def _detect_end_of_turn(self, item: AudioOrText) -> bool:
        """
        Decide whether the user's turn has ended.

        TEXT MODE: any non-empty string is treated as a complete turn (the test
        harness feeds whole utterances). An empty string never ends a turn.

        AUDIO MODE: track consecutive silence. When audio energy stays below
        `energy_threshold` for longer than `silence_timeout_s`, the turn ends.
        Loud (speech) audio resets the silence timer.
        """
        # Text mode: a complete utterance string => end of turn.
        if isinstance(item, str):
            return bool(item.strip())

        # Audio mode: energy-based silence + timeout endpointing.
        energy = self._audio_energy(item)
        now = time.monotonic()
        if energy >= self.energy_threshold:
            # Speech detected -> reset silence window.
            self._silence_started = None
            return False
        # Silence frame.
        if self._silence_started is None:
            self._silence_started = now
            return False
        if (now - self._silence_started) >= self.silence_timeout_s:
            self._silence_started = None
            # Combine silence-timer with Smart Turn v3 (USE_SMART_TURN=1): don't end
            # the turn if the model says the caller only paused mid-sentence to think.
            try:
                from app.voice_agent.turn_detector import confirm_end_of_turn

                return confirm_end_of_turn(True, item if isinstance(item, bytes) else b"")
            except Exception:
                return True
        return False

    # -- barge-in ----------------------------------------------------------

    def interrupt_current(self) -> None:
        """
        Signal a barge-in: stop any in-flight TTS so the bot stops talking and
        starts listening. Safe to call anytime (no-op if nothing is speaking).
        """
        self.interrupt.set()
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
            logger.debug("🔇 Barge-in: current TTS task cancelled.")

    def is_speaking(self) -> bool:
        """True if the bot currently has an active (un-cancelled) TTS task."""
        return self._tts_task is not None and not self._tts_task.done()

    # -- core stages -------------------------------------------------------

    async def _do_stt(self, item: AudioOrText) -> tuple[str, float]:
        """Run STT (or pass text through). Returns (text, elapsed_ms)."""
        start = time.monotonic()
        if isinstance(item, str):
            text = item.strip()
        else:
            try:
                text = await self.stt.transcribe(item)
            except Exception as e:
                logger.warning(f"STT failed, treating as empty: {e}")
                text = ""
        return text, (time.monotonic() - start) * 1000.0

    async def _do_llm(self, user_text: str) -> tuple[str, float]:
        """
        Generate the assistant reply. Prefers the optional flow engine; falls
        back to a free-form LLM completion. Returns (reply, elapsed_ms).
        """
        start = time.monotonic()
        reply = ""

        flow = self._get_flow_engine()
        if flow is not None:
            try:
                # Be tolerant about the flow engine's method name/signature.
                for meth in ("next", "step", "advance", "run", "respond"):
                    fn = getattr(flow, meth, None)
                    if fn is None:
                        continue
                    res = fn(user_text, self.state)
                    reply = await res if asyncio.iscoroutine(res) else res
                    break
            except Exception as e:
                logger.warning(f"Flow engine step failed, using LLM: {e}")
                reply = ""

        if not reply:
            messages: list[dict[str, str]] = []
            if self.system_prompt:
                messages.append({"role": "system", "content": self.system_prompt})
            messages.extend(self.state.history)
            try:
                reply = await self.llm.complete(messages, system_prompt=self.system_prompt)
            except Exception as e:
                logger.warning(f"LLM failed, using safe fallback reply: {e}")
                reply = "Sorry, I didn't catch that. Could you repeat?"

        return (reply or "").strip(), (time.monotonic() - start) * 1000.0

    async def _do_tts(self, text: str) -> tuple[bytes, float]:
        """
        Synthesize speech for `text` as a CANCELLABLE task so barge-in can stop
        it mid-way. Returns (audio_bytes, elapsed_ms); audio is b"" if cancelled.
        """
        start = time.monotonic()
        if not text:
            return b"", 0.0

        async def _synth() -> bytes:
            return await self.tts.synthesize(text, voice_id=self.voice_id)

        self._tts_task = asyncio.ensure_future(_synth())
        try:
            audio = await self._tts_task
        except asyncio.CancelledError:
            logger.debug("TTS cancelled by barge-in.")
            audio = b""
        except Exception as e:
            logger.warning(f"TTS failed, returning empty audio: {e}")
            audio = b""
        finally:
            self._tts_task = None
        return audio, (time.monotonic() - start) * 1000.0

    # -- public API: one turn ---------------------------------------------

    async def run_turn(self, audio_chunk_or_text: AudioOrText) -> tuple[str, TurnMetrics]:
        """
        Run ONE full turn: STT -> LLM -> TTS, updating conversation state.

        Works in both text mode (pass a str) and audio mode (pass bytes). Audio
        is synthesized but only the reply text is returned here (audio bytes are
        produced for side effects / overridable hooks). Returns (reply_text,
        TurnMetrics).
        """
        # New turn => clear any stale interrupt flag from a previous barge-in.
        self.interrupt.clear()
        turn_start = time.monotonic()
        metrics = TurnMetrics()

        # 1) STT (or text passthrough)
        user_text, metrics.stt_ms = await self._do_stt(audio_chunk_or_text)
        if not user_text:
            metrics.total_ms = (time.monotonic() - turn_start) * 1000.0
            self.state.last_metrics = metrics
            return "", metrics

        self.state.add_user(user_text)

        # 1.5) Live human-transfer intent (gated CALL_TRANSFER, default OFF).
        # Pure-keyword check (hot-path safe, no LLM); transfer khud fire-and-forget
        # background task me hota hai — turn block NAHI karta.
        try:
            from app.telephony import call_transfer as _ct

            if (
                _ct.enabled()
                and not self.state.flow_state.get("transfer_requested")
                and _ct.detect_transfer_intent(user_text)
            ):
                self.state.flow_state["transfer_requested"] = True
                _ctx = {
                    "history": list(self.state.history[-12:]),
                    **{
                        k: v
                        for k, v in self.state.flow_state.items()
                        if isinstance(v, (str, int, float))
                    },
                }
                _owner = str(self.state.flow_state.get("owner_phone") or "")
                asyncio.get_running_loop().create_task(_ct.request_transfer(_ctx, _owner))
                reply = "Ji bilkul — ek minute rukiye, main aapko owner se connect kar raha hoon."
                self.state.add_assistant(reply)
                if not self.interrupt.is_set():
                    _audio, metrics.tts_ms = await self._do_tts(reply)
                metrics.total_ms = (time.monotonic() - turn_start) * 1000.0
                self.state.turn_count += 1
                self.state.last_metrics = metrics
                return reply, metrics
        except Exception as _e:
            logger.warning(f"transfer-intent check failed (ignored): {_e}")

        # 2) LLM (flow engine or free-form)
        reply, metrics.llm_ms = await self._do_llm(user_text)
        self.state.add_assistant(reply)

        # 3) TTS (cancellable for barge-in)
        if self.interrupt.is_set():
            metrics.barged_in = True
        else:
            _audio, metrics.tts_ms = await self._do_tts(reply)
            if self.interrupt.is_set():
                metrics.barged_in = True

        metrics.total_ms = (time.monotonic() - turn_start) * 1000.0
        self.state.turn_count += 1
        self.state.last_metrics = metrics
        logger.debug(f"Turn {self.state.turn_count} metrics: {metrics.as_dict()}")
        # P1 observability: persist this turn's latency to the shared per-turn
        # store so web-call (the live tuning surface) feeds the same P50/P95
        # rollups as the phone paths. TURN_METRICS-gated; never raises.
        try:
            from app.voice_agent import turn_metrics as _tm

            _tm.record_turn(
                {
                    "path": "web_pipeline",
                    "turn": self.state.turn_count,
                    "outcome": "ok" if reply else "no_reply",
                    **metrics.as_dict(),
                }
            )
        except Exception:
            pass
        return reply, metrics

    # -- public API: streaming loop ---------------------------------------

    async def stream(self, audio_source: AsyncIterable[AudioOrText]) -> AsyncGenerator[str, None]:
        """
        Consume an async stream of audio chunks (or text utterances) and yield a
        bot reply string per completed user turn.

        Endpointing: chunks are buffered until `_detect_end_of_turn` fires, at
        which point the accumulated turn is processed. In text mode each yielded
        string is a complete turn.

        Barge-in: if `interrupt` is set (e.g. caller detected fresh user speech),
        the in-flight TTS is cancelled and the loop moves on to the next turn.
        """
        text_buffer: list[str] = []
        audio_buffer = bytearray()

        async for item in audio_source:
            # If the user starts talking while the bot speaks -> barge-in.
            if self.is_speaking():
                self.interrupt_current()

            ended = self._detect_end_of_turn(item)

            if isinstance(item, str):
                if item.strip():
                    text_buffer.append(item.strip())
                if ended and text_buffer:
                    turn_text = " ".join(text_buffer)
                    text_buffer = []
                    reply, _ = await self.run_turn(turn_text)
                    if reply:
                        yield reply
            else:
                audio_buffer.extend(item)
                if ended and audio_buffer:
                    chunk = bytes(audio_buffer)
                    audio_buffer = bytearray()
                    reply, _ = await self.run_turn(chunk)
                    if reply:
                        yield reply

        # Flush any trailing buffered input as a final turn.
        if text_buffer:
            reply, _ = await self.run_turn(" ".join(text_buffer))
            if reply:
                yield reply
        elif audio_buffer:
            reply, _ = await self.run_turn(bytes(audio_buffer))
            if reply:
                yield reply

    # -- convenience -------------------------------------------------------

    def reset(self) -> None:
        """Reset conversation state + interrupt flags for a fresh session."""
        self.state = PipelineState()
        self.interrupt.clear()
        self._silence_started = None
        if self._tts_task is not None and not self._tts_task.done():
            self._tts_task.cancel()
        self._tts_task = None
