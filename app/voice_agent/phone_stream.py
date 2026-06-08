"""
Phone Stream — Conversational AI over Vobiz/Twilio-compatible WebSocket media.
==============================================================================

Yeh module ek REAL two-way phone conversation chalata hai (bare asyncio, NO
pipecat). Vobiz <Stream> verb call ke audio ko ek WebSocket par bidirectionally
bhejta/leta hai (Twilio Media Streams compatible). Pipeline:

    Vobiz call --(G.711 µ-law 8kHz frames)--> WebSocket
        --> energy VAD (turn detection + barge-in)
        --> faster-whisper STT (tiny, cpu/int8 — 8k->16k float32)
        --> LLMBrain.generate_response (niche flows, Hinglish, short replies)
        --> EdgeTTS (hi-IN-SwaraNeural, natural) -> pydub mp3->PCM 8k -> µ-law
        --> WebSocket (paced ~20ms frames) --> caller

Naturalness ke liye: short Hinglish replies (system nudge), barge-in (caller
bot ko beech me rok sakta hai), aur energy-based turn detection (silence ke baad
hi STT chalta hai).

WIRE PROTOCOL (Vobiz, Twilio-compatible JSON text frames over WS)
-----------------------------------------------------------------
Vobiz -> us:
    {"event":"connected", ...}
    {"event":"start","start":{"streamSid":"...","callSid":"..."}}   # streamSid/stream_sid dono handle
    {"event":"media","media":{"payload":"<base64 µ-law 8kHz, 20ms=160B>"}}
    {"event":"dtmf","dtmf":{"digit":"1"}}
    {"event":"stop"}
us -> Vobiz:
    {"event":"media","streamSid":"<sid>","media":{"payload":"<base64 µ-law 8kHz>"}}  # 160B frames, paced
    {"event":"clear","streamSid":"<sid>"}                                            # barge-in flush

DEPENDENCIES (runtime — import-safe; missing deps degrade gracefully):
    faster-whisper  (STT)     — requirements.txt
    edge-tts        (TTS)     — requirements.txt
    pydub + ffmpeg  (decode)  — pydub in requirements.txt; ffmpeg = system binary
    numpy           (STT)     — requirements.txt
    audioop (stdlib <=3.12)   — Python 3.13 me hata diya gaya; tab `pip install audioop-lts`

Import-safe: heavy imports (faster_whisper/edge_tts/pydub/numpy) sab lazy hain,
to module import kabhi fail na ho — koi dep missing ho to woh path "" deta hai.
"""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import io
import json
import threading
from collections import deque
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# audioop: Python <=3.12 stdlib me hai. Python 3.13+ me hata diya gaya hai —
# tab `pip install audioop-lts` (drop-in `import audioop` wapas restore karta hai).
# Hum 3.12 par hain to stdlib import chalta hai; guard rakha hai taki module
# import-safe rahe agar kabhi 3.13 par bina backport ke chale.
try:
    import audioop  # type: ignore

    _AUDIOOP_OK = True
except Exception as _audioop_err:  # pragma: no cover - only on 3.13 w/o backport
    audioop = None  # type: ignore
    _AUDIOOP_OK = False
    logger.error(
        "phone_stream: audioop missing (%s) — Python 3.13+ par `pip install audioop-lts`",
        _audioop_err,
    )


# --------------------------------------------------------------------------- #
# Capability flags — light (find_spec heavy module ko import NAHI karta). Status
# endpoints / drop-in callers inse jaan sakte hain ki STT/TTS live ho payega ya
# nahi (missing dep => woh path graceful "" deta hai, socket fir bhi chalta hai).
# --------------------------------------------------------------------------- #
def _have(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


STT_AVAILABLE = _have("faster_whisper") or _have("vosk")
TTS_AVAILABLE = _have("edge_tts") and _have("pydub")

# --------------------------------------------------------------------------- #
# Audio constants — Vobiz/Twilio media streams: G.711 µ-law, 8 kHz, mono, 20ms
# --------------------------------------------------------------------------- #
SR_8K = 8000
SR_16K = 16000
FRAME_BYTES_ULAW = 160  # 20 ms of 8 kHz µ-law (1 byte/sample)
FRAME_SLEEP = 0.02  # pace outbound audio ~realtime (20 ms/frame)

# --------------------------------------------------------------------------- #
# Energy VAD / turn-detection tuning (har inbound media frame ~= 20 ms)
# --------------------------------------------------------------------------- #
VAD_RMS_THRESHOLD = 300  # PCM16 rms isse upar = speech
VAD_START_FRAMES = 3  # >=3 consecutive speech frames -> speech shuru (~60ms)
VAD_SILENCE_FRAMES = 35  # >=0.7 s silence -> utterance khatam
VAD_MIN_SPEECH_FRAMES = 20  # >=0.4 s speech collected ho to hi utterance accept
VAD_MAX_UTTERANCE_BYTES = 12 * SR_8K * 2  # 12 s hard cap (PCM16 @ 8kHz)

# --------------------------------------------------------------------------- #
# STT / LLM / TTS config
# --------------------------------------------------------------------------- #
WHISPER_MODEL_SIZE = "tiny"
STT_LANGUAGE = "hi"  # Hinglish hint; None karne se auto-detect
TTS_VOICE = "hi-IN-SwaraNeural"  # natural Indian Hindi female
REPLY_NUDGE = "(Reply in natural conversational Hinglish, max 2 short sentences)"
MAX_HISTORY = 20  # conversation history cap (recent turns)

_FALLBACK_GREETING = (
    "Namaste! Main LeadGen AI ki taraf se baat kar rahi hoon. "
    "Aapse bas do minute baat kar sakti hoon?"
)


# --------------------------------------------------------------------------- #
# Module-level singletons (lazy) — STT model + LLM brain ek hi baar banein
# --------------------------------------------------------------------------- #
_WHISPER_MODEL: Any = None
_WHISPER_TRIED = False
_WHISPER_LOCK = threading.Lock()


def _get_whisper() -> Any:
    """faster-whisper WhisperModel('tiny', cpu, int8) — lazy global singleton.
    Missing/failed load par None (STT silently '' deta hai)."""
    global _WHISPER_MODEL, _WHISPER_TRIED
    if _WHISPER_TRIED:
        return _WHISPER_MODEL
    with _WHISPER_LOCK:
        if _WHISPER_TRIED:
            return _WHISPER_MODEL
        _WHISPER_TRIED = True
        try:
            from faster_whisper import WhisperModel  # heavy — lazy import

            _WHISPER_MODEL = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
            logger.info("phone_stream: faster-whisper '%s' loaded (cpu/int8)", WHISPER_MODEL_SIZE)
        except Exception as e:
            logger.error("phone_stream: faster-whisper unavailable (%s) — STT disabled", e)
            _WHISPER_MODEL = None
    return _WHISPER_MODEL


_LLM_BRAIN: Any = None
_LLM_LOCK = threading.Lock()


def _get_brain() -> Any:
    """LLMBrain module-level singleton (lazy). None on failure."""
    global _LLM_BRAIN
    if _LLM_BRAIN is not None:
        return _LLM_BRAIN
    with _LLM_LOCK:
        if _LLM_BRAIN is None:
            try:
                from app.voice_agent.llm_brain import LLMBrain  # heavy (ML imports)

                _LLM_BRAIN = LLMBrain()
            except Exception as e:
                logger.error("phone_stream: LLMBrain unavailable (%s)", e)
                _LLM_BRAIN = None
    return _LLM_BRAIN


# --------------------------------------------------------------------------- #
# Per-call session
# --------------------------------------------------------------------------- #
class PhoneCallSession:
    """Ek live phone call ka conversational session (Vobiz media-stream WS).

    Lifecycle: ``await PhoneCallSession(ws, niche=...).run()`` — run() WS se
    JSON events loop karta hai; 'start' par greeting bolta hai, 'media' par
    caller audio buffer + VAD karta hai, utterance khatam hone par STT->LLM->TTS
    chalata hai, aur 'stop'/disconnect par cleanup.
    """

    def __init__(
        self,
        websocket: WebSocket,
        niche: str = "general",
        client_name: str = "LeadGen AI",
        client_id: str | None = None,
    ) -> None:
        self.ws = websocket
        self.niche = niche or "general"
        self.client_name = client_name or "LeadGen AI"
        self.client_id = client_id  # optional — drop-in compat with /stream WS endpoint

        # Stream identity (Vobiz 'start' se aata hai)
        self.stream_sid: str | None = None
        self.call_sid: str | None = None

        # Conversation state
        self.history: list[dict[str, str]] = []
        self._greeted = False

        # Control flags
        self._running = True
        self._interrupt = False  # barge-in: sender task isse check karke abort karta hai
        self._bot_speaking = False

        # Locks
        self._send_lock = asyncio.Lock()  # outbound WS sends serialize
        self._speak_lock = asyncio.Lock()  # ek time par ek hi audio stream bole
        self._turn_lock = asyncio.Lock()  # STT->LLM->TTS turns serialize

        # Background tasks (greeting + per-turn processing)
        self._tasks: set[asyncio.Task] = set()

        # VAD state
        self._in_speech = False
        self._consec_speech = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._utterance = bytearray()  # PCM16 @ 8kHz collected
        self._preroll: deque[bytes] = deque(maxlen=VAD_START_FRAMES)  # leading speech na cut ho

    # --------------------------------------------------------------------- #
    # Entry points
    # --------------------------------------------------------------------- #
    async def handle(self) -> None:
        """Accept the WebSocket, then run the conversation loop. Use this when
        the caller passes an UN-accepted socket (the /stream WS endpoint does).
        If you already called ``websocket.accept()``, call :meth:`run` instead."""
        try:
            await self.ws.accept()
        except Exception as e:
            logger.warning("phone_stream: ws accept failed (%s)", e)
            return
        await self.run()

    # --------------------------------------------------------------------- #
    # Main receive loop
    # --------------------------------------------------------------------- #
    async def run(self) -> None:
        logger.info("phone_stream: session opened (niche=%s)", self.niche)
        try:
            while self._running:
                try:
                    raw = await self._recv()
                except (WebSocketDisconnect, RuntimeError):
                    break
                if raw is None:  # disconnect
                    break
                try:
                    data = json.loads(raw)
                except Exception:
                    continue  # stray/non-JSON frame — skip
                if isinstance(data, dict):
                    await self._dispatch(data)
        except Exception as e:
            logger.warning("phone_stream: run error (handled): %s", e)
        finally:
            await self._cleanup()

    async def _recv(self) -> str | None:
        """Raw WS receive — text ya bytes dono handle; disconnect par None."""
        msg = await self.ws.receive()
        if msg.get("type") == "websocket.disconnect":
            return None
        raw = msg.get("text")
        if raw is None:
            b = msg.get("bytes")
            raw = b.decode("utf-8", "ignore") if b else None
        return raw

    async def _dispatch(self, data: dict[str, Any]) -> None:
        event = data.get("event")
        if event == "media":
            await self._handle_media(data)
        elif event == "start":
            await self._handle_start(data)
        elif event == "dtmf":
            self._handle_dtmf(data)
        elif event == "stop":
            logger.info("phone_stream: stop event (callSid=%s)", self.call_sid)
            self._running = False
        elif event == "connected":
            logger.debug("phone_stream: connected event")
        # mark / clear / unknown — ignore

    # --------------------------------------------------------------------- #
    # Event handlers
    # --------------------------------------------------------------------- #
    async def _handle_start(self, data: dict[str, Any]) -> None:
        """'start' — streamSid/callSid save karo (streamSid & stream_sid dono),
        optional customParameters se niche/client_name override, phir greeting."""
        start = data.get("start") or {}
        self.stream_sid = (
            start.get("streamSid")
            or start.get("stream_sid")
            or data.get("streamSid")
            or data.get("stream_sid")
        )
        self.call_sid = (
            start.get("callSid")
            or start.get("call_sid")
            or data.get("callSid")
            or data.get("call_sid")
        )
        params = start.get("customParameters") or start.get("custom_parameters") or {}
        if isinstance(params, dict):
            if params.get("niche"):
                self.niche = str(params["niche"])
            if params.get("client_name"):
                self.client_name = str(params["client_name"])

        logger.info(
            "phone_stream: start streamSid=%s callSid=%s niche=%s",
            self.stream_sid,
            self.call_sid,
            self.niche,
        )
        if not self._greeted:
            self._greeted = True
            self._spawn(self._greeting())

    def _handle_dtmf(self, data: dict[str, Any]) -> None:
        digit = (data.get("dtmf") or {}).get("digit")
        logger.debug("phone_stream: dtmf %s", digit)
        # '#' / '*' ko hangup-intent maan sakte hain (abhi sirf log).

    async def _handle_media(self, data: dict[str, Any]) -> None:
        """Inbound caller audio frame — decode, energy VAD, buffer; utterance
        khatam hone par turn spawn. Bot bolte waqt speech aaye to barge-in."""
        payload = (data.get("media") or {}).get("payload")
        if not payload:
            return
        pcm8k = self._decode_inbound(payload)  # PCM16 @ 8kHz
        if not pcm8k or not _AUDIOOP_OK:
            return
        try:
            rms = audioop.rms(pcm8k, 2)
        except Exception:
            return
        is_speech = rms >= VAD_RMS_THRESHOLD

        # Pre-roll buffer (jab tak speech officially shuru nahi hui)
        if not self._in_speech:
            self._preroll.append(pcm8k)

        if is_speech:
            self._consec_speech += 1
            self._silence_frames = 0
            if not self._in_speech and self._consec_speech >= VAD_START_FRAMES:
                # Speech officially shuru — pre-roll prepend (leading clip na ho)
                self._in_speech = True
                for f in self._preroll:
                    self._utterance.extend(f)
                self._preroll.clear()
                self._speech_frames = self._consec_speech
                # BARGE-IN: bot bol raha hai to use turant roko
                if self._bot_speaking:
                    self._interrupt = True
                    logger.debug("phone_stream: barge-in detected")
            elif self._in_speech:
                self._utterance.extend(pcm8k)
                self._speech_frames += 1
        else:
            self._consec_speech = 0
            if self._in_speech:
                self._utterance.extend(pcm8k)  # trailing silence bhi rakho
                self._silence_frames += 1

        # Utterance end? (silence-based ya hard cap)
        if self._in_speech and self._silence_frames >= VAD_SILENCE_FRAMES:
            if self._speech_frames >= VAD_MIN_SPEECH_FRAMES:
                pcm = bytes(self._utterance)
                self._reset_vad()
                self._spawn(self._process_turn(pcm))
            else:
                # bahut chhota blip (noise) — discard, process mat karo
                self._reset_vad()
        elif self._in_speech and len(self._utterance) >= VAD_MAX_UTTERANCE_BYTES:
            pcm = bytes(self._utterance)
            self._reset_vad()
            self._spawn(self._process_turn(pcm))

    # --------------------------------------------------------------------- #
    # Turn pipeline: STT -> LLM -> TTS
    # --------------------------------------------------------------------- #
    async def _process_turn(self, pcm8k: bytes) -> None:
        """Ek caller utterance ka full turn. _turn_lock se turns serialize hote
        hain; barge-in active speech ko rok deta hai isliye lock jaldi free hota."""
        async with self._turn_lock:
            if not self._running:
                return
            loop = asyncio.get_event_loop()
            text = await loop.run_in_executor(None, self._transcribe_blocking, pcm8k)
            text = (text or "").strip()
            if not text:
                logger.debug("phone_stream: empty STT — turn skipped")
                return
            logger.info("phone_stream caller: %s", text)

            reply = await self._llm_reply(text)
            if not reply or not self._running:
                return
            logger.info("phone_stream bot: %s", reply)
            await self._speak(reply)

    def _transcribe_blocking(self, pcm8k: bytes) -> str:
        """Blocking STT (executor me chalta hai). 8k PCM16 -> 16k float32 ->
        faster-whisper. Kisi bhi failure par '' (never raises)."""
        try:
            model = _get_whisper()
            if model is None or not pcm8k or not _AUDIOOP_OK:
                return ""
            import numpy as np  # lazy

            pcm16k, _ = audioop.ratecv(pcm8k, 2, 1, SR_8K, SR_16K, None)
            samples = np.frombuffer(pcm16k, dtype=np.int16).astype(np.float32) / 32768.0
            segments, _info = model.transcribe(samples, language=STT_LANGUAGE, beam_size=1)
            return " ".join(seg.text for seg in segments).strip()
        except Exception as e:
            logger.warning("phone_stream: STT failed (%s)", e)
            return ""

    async def _llm_reply(self, user_text: str) -> str:
        """LLMBrain se reply. History clean rakhte hain; brevity nudge sirf LLM
        ko bheje jaane wale last user message par append hota hai."""
        self.history.append({"role": "user", "content": user_text})
        self._trim_history()

        brain = _get_brain()
        if brain is None:
            reply = "Maaf kijiye, abhi thodi technical dikkat hai. Baad me try karein."
            self.history.append({"role": "assistant", "content": reply})
            return reply

        # Last user message ko nudge ke saath bhejo (history me original hi rahe)
        call_history = list(self.history)
        call_history[-1] = {"role": "user", "content": f"{user_text} {REPLY_NUDGE}"}
        try:
            text = await brain.generate_response(
                conversation_history=call_history,
                niche=self.niche,
                client_name=self.client_name,
                client_service=self.niche,
            )
            text = (text or "").strip() or "Haan, boliye?"
        except Exception as e:
            logger.warning("phone_stream: LLM failed (%s)", e)
            text = "Sorry, awaaz thodi clear nahi aayi — dobara boliye?"
        self.history.append({"role": "assistant", "content": text})
        return text

    def _trim_history(self) -> None:
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]

    # --------------------------------------------------------------------- #
    # Greeting (bot pehle bolta hai — proves it's alive)
    # --------------------------------------------------------------------- #
    async def _greeting(self) -> None:
        try:
            await asyncio.sleep(0.3)  # stream ko settle hone do
            text = await self._greeting_text()
            self.history.append({"role": "assistant", "content": text})
            await self._speak(text)
        except Exception as e:
            logger.warning("phone_stream: greeting failed (%s)", e)

    async def _greeting_text(self) -> str:
        brain = _get_brain()
        if brain is not None:
            try:
                text = await brain.generate_response(
                    conversation_history=[
                        {
                            "role": "user",
                            "content": (
                                f"Start a friendly outbound phone call for a {self.niche} "
                                f"business. Greet warmly in Hinglish and ask ONE short opening "
                                f"question. {REPLY_NUDGE}"
                            ),
                        }
                    ],
                    niche=self.niche,
                    client_name=self.client_name,
                    client_service=self.niche,
                )
                if text and text.strip():
                    return text.strip()
            except Exception as e:
                logger.debug("phone_stream: greeting LLM failed (%s)", e)
        return _FALLBACK_GREETING

    # --------------------------------------------------------------------- #
    # TTS + outbound audio
    # --------------------------------------------------------------------- #
    async def _speak(self, text: str) -> None:
        """text -> EdgeTTS -> µ-law 8k -> WS (paced). _speak_lock se ek time par
        ek hi stream bole; barge-in interrupt jaldi free karta hai."""
        text = (text or "").strip()
        if not text or not self._running:
            return
        ulaw = await self._synthesize(text)
        if not ulaw:
            return
        async with self._speak_lock:
            await self._send_audio(ulaw)

    async def _synthesize(self, text: str) -> bytes:
        """EdgeTTS mp3 stream collect karo, phir executor me µ-law 8k decode.
        Koi bhi failure (edge_tts/pydub/ffmpeg missing) par b'' (never raises)."""
        try:
            import edge_tts  # lazy

            communicate = edge_tts.Communicate(text, voice=TTS_VOICE)
            mp3 = bytearray()
            async for chunk in communicate.stream():
                if chunk.get("type") == "audio" and chunk.get("data"):
                    mp3.extend(chunk["data"])
            if not mp3:
                return b""
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._mp3_to_ulaw, bytes(mp3))
        except Exception as e:
            logger.warning("phone_stream: TTS failed (%s)", e)
            return b""

    @staticmethod
    def _mp3_to_ulaw(mp3_bytes: bytes) -> bytes:
        """Blocking: mp3 -> PCM16 mono 8kHz (pydub/ffmpeg) -> G.711 µ-law."""
        try:
            from pydub import AudioSegment  # lazy (needs ffmpeg binary)

            seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            seg = seg.set_frame_rate(SR_8K).set_channels(1).set_sample_width(2)
            pcm = seg.raw_data
            if not _AUDIOOP_OK:
                return b""
            return audioop.lin2ulaw(pcm, 2)
        except Exception as e:
            logger.warning("phone_stream: mp3->ulaw decode failed (%s)", e)
            return b""

    async def _send_audio(self, ulaw: bytes) -> None:
        """µ-law bytes ko ~160B frames me, ~20ms paced, WS par bhejo. Har frame
        se pehle barge-in/stop check — interrupt par turant abort + clear."""
        if not self.stream_sid or not ulaw:
            return
        self._interrupt = False
        self._bot_speaking = True
        try:
            for i in range(0, len(ulaw), FRAME_BYTES_ULAW):
                if self._interrupt or not self._running:
                    logger.debug("phone_stream: outbound audio aborted (barge-in/stop)")
                    await self._send_clear()
                    break
                frame = ulaw[i : i + FRAME_BYTES_ULAW]
                await self._send_json(
                    {
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {"payload": base64.b64encode(frame).decode("ascii")},
                    }
                )
                await asyncio.sleep(FRAME_SLEEP)
        finally:
            self._bot_speaking = False

    async def _send_clear(self) -> None:
        """Barge-in par Vobiz/Twilio ke buffered audio ko flush (best-effort)."""
        if not self.stream_sid:
            return
        try:
            await self._send_json({"event": "clear", "streamSid": self.stream_sid})
        except Exception:
            pass

    async def _send_json(self, obj: dict[str, Any]) -> None:
        if not self._running:
            return
        async with self._send_lock:
            try:
                await self.ws.send_json(obj)
            except Exception as e:
                logger.debug("phone_stream: WS send failed (%s) — ending", e)
                self._running = False

    # --------------------------------------------------------------------- #
    # Helpers
    # --------------------------------------------------------------------- #
    def _decode_inbound(self, payload_b64: str) -> bytes:
        """base64 µ-law -> PCM16 @ 8kHz. Failure par b''."""
        try:
            ulaw = base64.b64decode(payload_b64)
        except Exception:
            return b""
        if not ulaw or not _AUDIOOP_OK:
            return b""
        try:
            return audioop.ulaw2lin(ulaw, 2)
        except Exception:
            return b""

    def _reset_vad(self) -> None:
        self._in_speech = False
        self._consec_speech = 0
        self._speech_frames = 0
        self._silence_frames = 0
        self._utterance = bytearray()
        self._preroll.clear()

    def _spawn(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _cleanup(self) -> None:
        self._running = False
        self._interrupt = True
        for t in list(self._tasks):
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("phone_stream: session ended (callSid=%s)", self.call_sid)


__all__ = ["PhoneCallSession", "STT_AVAILABLE", "TTS_AVAILABLE"]
