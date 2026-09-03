"""
Tata Smartflo Voice Streaming — conversational phone AI over WebSocket
======================================================================

Smartflo Voice Streaming sends/receives audio over WebSocket using the
Twilio Media Streams protocol (mulaw 8kHz).  This module implements the
conversation loop: listen → understand → reply → speak.

Protocol (from docs.smartflo.tatatelebusiness.com):
  recv from Smartflo:
    {"event":"connected"}                                  — handshake
    {"event":"start","start":{"streamSid":..,"callSid":..,"from":..,"to":..,
          "direction":..,"mediaFormat":{"encoding":"audio/x-mulaw",
          "sampleRate":8000,"bitRate":64,"bitDepth":8}}}
    {"event":"media","media":{"payload":"<b64 mulaw>","chunk":"1","timestamp":"5"}}
    {"event":"stop","stop":{"reason":"..."}}
    {"event":"dtmf","dtmf":{"digit":"1"}}
  send to Smartflo:
    {"event":"media","media":{"payload":"<b64 mulaw>","chunk":"1"}}
    {"event":"clear"}                    — flush playback (barge-in)
    {"event":"mark","mark":{"name":"..."}} — sync end-of-playback

Audio format: G.711 µ-law (mulaw), 8000 Hz, 8-bit, 64 kbps.
  - Inbound: decode mulaw → PCM16 8kHz → resample to 16kHz → STT
  - Outbound: TTS → PCM16 16kHz → resample to 8kHz → encode to mulaw → send

Conversion uses audioop (stdlib ≤3.12) or audioop-lts (3.13+).

Env vars:
  SMARTFLO_VOICE_STREAM_ENABLED=1    — arm the endpoint (INERT default)
  SMARTFLO_WS_SECRET=<random>        — optional HMAC auth on WS connect
  SMARTFLO_WS_REQUIRE_SECRET=0       — enforce secret check (INERT default)
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import importlib.util
import io
import json
import os
import struct
import time
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# ---------------------------------------------------------------------------
# Capability detection (same pattern as vobiz_stream.py)
# ---------------------------------------------------------------------------
def _have(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _groq_key() -> str:
    k = (os.environ.get("GROQ_API_KEY", "") or "").strip()
    if not k:
        try:
            from app.config import settings
            k = (getattr(settings, "groq_api_key", "") or "").strip()
        except Exception:
            pass
    return k


_VOSK_OK = _have("vosk")
_FWHISPER_OK = _have("faster_whisper")
_GENAI_OK = _have("google.genai")
_OPENAI_SDK_OK = _have("openai")
_LOCAL_STT_OK = _VOSK_OK or _FWHISPER_OK
STT_AVAILABLE = _LOCAL_STT_OK or _GENAI_OK or (_OPENAI_SDK_OK and bool(_groq_key()))
TTS_AVAILABLE = _have("edge_tts") and _have("pydub")

# audioop (stdlib ≤3.12, backport 3.13+)
try:
    import audioop  # type: ignore
    _AUDIOOP_OK = True
except Exception:
    try:
        import audioop_lts as audioop  # type: ignore
        _AUDIOOP_OK = True
    except Exception:
        audioop = None  # type: ignore
        _AUDIOOP_OK = False

# ---------------------------------------------------------------------------
# Audio constants
# ---------------------------------------------------------------------------
SMARTFLO_SAMPLE_RATE = 8000    # mulaw 8kHz
INTERNAL_SAMPLE_RATE = 16000   # our pipeline runs at 16kHz
FRAME_MS = 20                  # 20ms frames
MULAW_FRAME_BYTES = 160        # 8kHz * 20ms = 160 bytes mulaw
PCM16_FRAME_BYTES = 320        # 16kHz * 20ms = 320 bytes PCM16 (×2 for 16-bit)

# VAD thresholds (same as vobiz_stream defaults)
_DEF_VAD_RMS = 300
_VAD_RMS = int(os.environ.get("SMARTFLO_VAD_RMS", str(_DEF_VAD_RMS)))
_SILENCE_MS_DEF = 800.0
_SILENCE_MS = float(os.environ.get("SMARTFLO_SILENCE_MS", str(_SILENCE_MS_DEF)))
_MIN_SPEECH_MS = 300.0
_NOINPUT_MS = float(os.environ.get("SMARTFLO_NOINPUT_MS", "12000"))

# Send timeout (WS backpressure guard)
_SEND_TIMEOUT_S = 3.0


# ---------------------------------------------------------------------------
# Audio conversion helpers
# ---------------------------------------------------------------------------
def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Decode mulaw 8kHz → PCM16 8kHz."""
    if _AUDIOOP_OK and audioop is not None:
        return audioop.ulaw2lin(mulaw_bytes, 2)
    # Pure-Python fallback (linear decode, good enough for STT)
    result = bytearray()
    for byte in mulaw_bytes:
        # µ-law decode (ITU-T G.711)
        byte = ~byte & 0xFF
        sign = (byte & 0x80) >> 7
        exponent = (byte >> 4) & 0x07
        mantissa = byte & 0x0F
        sample = ((mantissa << 1) + 33) << (exponent + 2)
        sample -= 0x84
        if sign:
            sample = -sample
        result.extend(struct.pack("<h", max(-32768, min(32767, sample))))
    return bytes(result)


def pcm16_8k_to_16k(pcm_8k: bytes) -> bytes:
    """Upsample PCM16 8kHz → PCM16 16kHz (simple linear interpolation).

    For each pair of input samples, outputs the original + interpolated midpoint.
    Produces exactly 2× the input sample count (2N samples from N).
    """
    if _AUDIOOP_OK and audioop is not None:
        out, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
        return out
    # Pure-Python: linear interpolation (8k→16k = 2×)
    samples = struct.unpack(f"<{len(pcm_8k) // 2}h", pcm_8k)
    out = []
    for i in range(len(samples)):
        out.append(samples[i])
        if i < len(samples) - 1:
            out.append((samples[i] + samples[i + 1]) // 2)
        else:
            out.append(samples[i])  # repeat last sample
    return struct.pack(f"<{len(out)}h", *out)


def pcm16_16k_to_8k(pcm_16k: bytes) -> bytes:
    """Downsample PCM16 16kHz → PCM16 8kHz (simple decimation)."""
    if _AUDIOOP_OK and audioop is not None:
        out, _ = audioop.ratecv(pcm_16k, 2, 1, 16000, 8000, None)
        return out
    # Pure-Python: decimate (16k→8k = every other sample)
    samples = struct.unpack(f"<{len(pcm_16k) // 2}h", pcm_16k)
    out = samples[::2]
    return struct.pack(f"<{len(out)}h", *out)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Encode PCM16 8kHz → mulaw 8kHz.

    Standard ITU-T G.711 µ-law: bias=0x84, clip=32635.
    Matches audioop.lin2ulaw() exactly (verified against reference).
    """
    if _AUDIOOP_OK and audioop is not None:
        return audioop.lin2ulaw(pcm16_bytes, 2)
    # Pure-Python fallback (ITU-T G.711 reference)
    result = bytearray()
    MULAW_BIAS = 0x84
    MULAW_CLIP = 32635
    for i in range(0, len(pcm16_bytes), 2):
        sample = struct.unpack_from("<h", pcm16_bytes, i)[0]
        sign = 0
        if sample < 0:
            sign = 0x80
            sample = -sample
        if sample > MULAW_CLIP:
            sample = MULAW_CLIP
        sample += MULAW_BIAS
        exponent = 7
        exp_mask = 0x4000
        while exponent > 0 and not (sample & exp_mask):
            exponent -= 1
            exp_mask >>= 1
        mantissa = (sample >> (exponent + 3)) & 0x0F
        byte = ~(sign | (exponent << 4) | mantissa) & 0xFF
        result.append(byte)
    return bytes(result)


# ---------------------------------------------------------------------------
# Transcript directory helper
# ---------------------------------------------------------------------------
def _call_transcripts_dir() -> str:
    try:
        from app.platform.runtime_recording_paths import call_transcripts_dir
        return str(call_transcripts_dir())
    except Exception:
        return "data/call_transcripts"


# ---------------------------------------------------------------------------
# Stream session
# ---------------------------------------------------------------------------
class SmartfloStreamSession:
    """Drives one Smartflo voice-streaming call.

    Audio flow:
      inbound mulaw 8kHz → PCM16 8kHz → upsample 16kHz → VAD + STT buffer
      → LLM reply → TTS → PCM16 16kHz → downsample 8kHz → mulaw 8kHz → send

    Never raises out of handle(). Graceful degradation: missing STT/TTS =
    call connects but stays silent (logged).
    """

    def __init__(
        self,
        websocket: Any,
        niche: str = "general",
        client_id: str | None = None,
        client_name: str = "LeadGen AI",
        lead_phone: str | None = None,
        crm_lead_id: str | None = None,
        opening_line: str = "",
    ) -> None:
        self.ws = websocket
        self.niche = (niche or "general").strip() or "general"
        self._caller_opening_line: str | None = (opening_line or "").strip() or None
        self.client_id = client_id
        self.client_name = client_name or "LeadGen AI"
        self._lead_phone: str | None = (lead_phone or "").strip() or None
        self._crm_lead_id: str | None = (crm_lead_id or "").strip() or None

        self.stream_sid: str | None = None
        self.call_sid: str | None = None
        self.from_number: str | None = None
        self.to_number: str | None = None
        self.hist: list[dict[str, str]] = []
        self._closed = False
        self._started_at = datetime.now(timezone.utc)
        self._greeted = False

        # VAD state
        self._speech_buf: list[bytes] = []  # PCM16 16kHz buffers
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False

        # Playback state
        self._speaking = False
        self._barge_frames = 0

        # Diagnostics
        self._media_frames = 0
        self._media_bytes = 0
        self._caller_rms_max = 0

        # Lazy helpers
        self._telecaller = None
        self._brain = None

    # ------------------------------------------------------------------ #
    # Main handler
    # ------------------------------------------------------------------ #
    async def handle(self) -> None:
        try:
            await self.ws.accept()
        except Exception as e:
            logger.warning(f"[smartflo-stream] accept failed: {e}")
            return
        logger.info(
            f"[smartflo-stream] WS open niche={self.niche} client={self.client_id} "
            f"(STT={STT_AVAILABLE} TTS={TTS_AVAILABLE} audioop={_AUDIOOP_OK})"
        )
        try:
            while True:
                raw = await asyncio.wait_for(self.ws.receive_text(), timeout=60.0)
                await self._on_event(raw)
        except asyncio.TimeoutError:
            logger.info("[smartflo-stream] WS idle timeout (60s) — closing")
        except Exception as e:
            if not self._closed:
                logger.warning(f"[smartflo-stream] WS error: {e}")
        finally:
            if not self._closed:
                await self._cleanup()

    # ------------------------------------------------------------------ #
    # Event handling
    # ------------------------------------------------------------------ #
    async def _on_event(self, raw: str) -> None:
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning(f"[smartflo-stream] non-JSON frame: {raw[:120]!r}")
            return

        event = data.get("event")

        if event == "connected":
            logger.info("[smartflo-stream] connected event")
            # Send our connected handshake back
            await self._send({"event": "connected"})

        elif event == "start":
            start = data.get("start") or {}
            self.stream_sid = data.get("streamSid") or start.get("streamSid")
            self.call_sid = start.get("callSid")
            self.from_number = start.get("from")
            self.to_number = start.get("to")
            # Pull niche/client from customParameters (if set in Smartflo portal)
            params = start.get("customParameters") or {}
            self.niche = (params.get("niche") or self.niche).strip() or "general"
            self.client_id = params.get("client_id") or self.client_id
            self._lead_phone = (
                params.get("lead_phone")
                or params.get("from")
                or self.from_number
                or self._lead_phone
            )
            logger.info(
                f"[smartflo-stream] start streamSid={self.stream_sid} "
                f"callSid={self.call_sid} from={self.from_number} "
                f"to={self.to_number} niche={self.niche}"
            )
            # Resolve client name
            if self.client_id:
                try:
                    from app.marketing import clients_store
                    _c = clients_store.get_client(self.client_id)
                    if _c:
                        self.client_name = (
                            _c.get("business_name") or ""
                        ).strip() or self.client_name
                        if (not self.niche or self.niche == "general") and _c.get("niche"):
                            self.niche = _c["niche"]
                except Exception:
                    pass
            # Send start ack back to Smartflo
            await self._send({
                "event": "start",
                "streamSid": self.stream_sid,
            })
            # Greet
            await self._maybe_greet()

        elif event == "media":
            media = data.get("media") or {}
            payload = media.get("payload")
            if payload:
                await self._on_media(payload)

        elif event == "stop":
            reason = (data.get("stop") or {}).get("reason", "unknown")
            logger.info(f"[smartflo-stream] stop reason={reason}")
            if not self._closed:
                await self._cleanup()

        elif event == "dtmf":
            digit = (data.get("dtmf") or {}).get("digit")
            logger.info(f"[smartflo-stream] dtmf={digit}")
            if str(digit) == "9":
                try:
                    from app.telephony.consent_ledger import ConsentAction, persist_opt_out
                    persist_opt_out(
                        phone=self._lead_phone or "",
                        action=ConsentAction.OPT_OUT,
                        source="smartflo_dtmf_press9",
                    )
                except Exception:
                    pass
                await self._send({"event": "clear", "streamSid": self.stream_sid})
                await self._cleanup()

        elif event == "mark":
            logger.debug(f"[smartflo-stream] mark: {data.get('mark', {}).get('name')}")

    # ------------------------------------------------------------------ #
    # Inbound audio: mulaw 8kHz → PCM16 8kHz → upsample → VAD → STT
    # ------------------------------------------------------------------ #
    async def _on_media(self, payload: str) -> None:
        try:
            mulaw = base64.b64decode(payload)
        except Exception:
            return
        if not mulaw:
            return
        self._media_frames += 1
        self._media_bytes += len(mulaw)

        # Convert: mulaw 8kHz → PCM16 8kHz → PCM16 16kHz
        pcm_8k = mulaw_to_pcm16(mulaw)
        pcm_16k = pcm16_8k_to_16k(pcm_8k)

        # RMS for VAD
        rms = self._pcm16_rms(pcm_16k)
        if rms > self._caller_rms_max:
            self._caller_rms_max = rms

        is_speech = rms >= _VAD_RMS

        if is_speech:
            self._had_speech = True
            self._speech_buf.append(pcm_16k)
            self._speech_ms += FRAME_MS
            self._silence_ms = 0.0

            # Barge-in detection
            if self._speaking:
                self._barge_frames += 1
                if self._barge_frames >= 3:  # ~60ms of speech = barge-in
                    await self._barge_in()
            else:
                self._barge_frames = 0
        else:
            self._barge_frames = max(0, self._barge_frames - 1)
            self._silence_ms += FRAME_MS

            # Utterance boundary: had speech + enough trailing silence
            if (
                self._had_speech
                and self._speech_ms >= _MIN_SPEECH_MS
                and self._silence_ms >= _SILENCE_MS
            ):
                await self._on_utterance()

    async def _on_utterance(self) -> None:
        """Process a completed user utterance: STT → LLM → TTS → send."""
        if not self._speech_buf:
            return
        pcm_16k = b"".join(self._speech_buf)
        self._speech_buf = []
        self._speech_ms = 0.0
        self._silence_ms = 0.0
        self._had_speech = False

        # STT
        text = await self._stt(pcm_16k)
        if not text or not text.strip():
            return
        logger.info(f"[smartflo-stream] user: {text.strip()}")
        self.hist.append({"role": "user", "content": text.strip()})

        # LLM reply
        reply = await self._llm_reply(text.strip())
        if not reply:
            return
        logger.info(f"[smartflo-stream] bot: {reply[:120]}")
        self.hist.append({"role": "assistant", "content": reply})

        # TTS → send
        await self._say(reply)

    # ------------------------------------------------------------------ #
    # STT pipeline (reuse vobiz_stream's chain)
    # ------------------------------------------------------------------ #
    async def _stt(self, pcm_16k: bytes) -> str:
        """Transcribe PCM16 16kHz audio → text. Returns empty string on failure."""
        if not STT_AVAILABLE:
            logger.warning("[smartflo-stream] STT unavailable")
            return ""
        try:
            # Try Groq Whisper first (free, fast)
            if _OPENAI_SDK_OK and _groq_key():
                return await self._groq_stt(pcm_16k)
        except Exception as e:
            logger.debug(f"[smartflo-stream] Groq STT failed: {e}")
        try:
            # Gemini audio-in (multimodal)
            if _GENAI_OK:
                return await self._gemini_stt(pcm_16k)
        except Exception as e:
            logger.debug(f"[smartflo-stream] Gemini STT failed: {e}")
        try:
            # Local whisper/fallback
            if _LOCAL_STT_OK:
                return await self._local_stt(pcm_16k)
        except Exception as e:
            logger.debug(f"[smartflo-stream] local STT failed: {e}")
        return ""

    async def _groq_stt(self, pcm_16k: bytes) -> str:
        """Groq Whisper-large-v3 STT (free tier)."""
        import httpx
        key = _groq_key()
        audio_b64 = base64.b64encode(pcm_16k).decode()
        # Groq expects file upload, but base64 works via the API
        files = {"file": ("audio.wav", io.BytesIO(pcm_16k), "audio/wav")}
        data = {
            "model": "whisper-large-v3",
            "language": "hi",
            "response_format": "text",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                files=files,
                data=data,
            )
        if resp.status_code == 200:
            return (resp.text or "").strip()
        raise RuntimeError(f"Groq STT {resp.status_code}: {resp.text[:200]}")

    async def _gemini_stt(self, pcm_16k: bytes) -> str:
        """Gemini multimodal audio-in STT."""
        from app.voice_agent.free_ai import gemini_audio_transcribe
        return await gemini_audio_transcribe(pcm_16k, sample_rate=16000)

    async def _local_stt(self, pcm_16k: bytes) -> str:
        """Local vosk/faster-whisper STT fallback."""
        from app.voice_agent.free_ai import local_stt
        return await local_stt(pcm_16k, sample_rate=16000)

    # ------------------------------------------------------------------ #
    # LLM reply (reuse telecaller_brain / free_ai)
    # ------------------------------------------------------------------ #
    async def _llm_reply(self, user_text: str) -> str:
        """Generate a conversational reply. Uses TelecallerBrain if available."""
        try:
            if self._telecaller is None and not getattr(self, "_telecaller_tried", False):
                self._telecaller_tried = True
                from app.voice_agent.telecaller_brain import TelecallerBrain
                self._telecaller = TelecallerBrain(
                    niche=self.niche,
                    client_id=self.client_id,
                    client_name=self.client_name,
                )
            if self._telecaller:
                return await self._telecaller.reply(user_text, self.hist)
        except Exception as e:
            logger.debug(f"[smartflo-stream] TelecallerBrain failed: {e}")

        # Fallback to free_ai chain
        try:
            from app.voice_agent.free_ai import chat
            messages = self.hist[-10:]  # bounded context
            return await chat(messages, niche=self.niche)
        except Exception as e:
            logger.warning(f"[smartflo-stream] LLM fallback failed: {e}")
            return ""

    # ------------------------------------------------------------------ #
    # TTS + send (PCM16 16kHz → downsample → mulaw → WS media event)
    # ------------------------------------------------------------------ #
    async def _say(self, text: str) -> None:
        """Synthesize text → TTS → send to caller via mulaw media events."""
        if not TTS_AVAILABLE:
            logger.warning("[smartflo-stream] TTS unavailable — text-only reply")
            return
        try:
            pcm_16k = await self._tts(text)
            if not pcm_16k:
                return
            # Downsample 16kHz → 8kHz, encode to mulaw
            pcm_8k = pcm16_16k_to_8k(pcm_16k)
            mulaw = pcm16_to_mulaw(pcm_8k)
            # Send in chunks (160 bytes = 20ms)
            await self._send_mulaw_audio(mulaw)
        except Exception as e:
            logger.warning(f"[smartflo-stream] TTS/send failed: {e}")

    async def _tts(self, text: str) -> bytes:
        """Text → PCM16 16kHz audio via EdgeTTS."""
        import edge_tts
        rate = os.environ.get("SMARTFLO_TTS_RATE", "+26%")
        pitch = os.environ.get("SMARTFLO_TTS_PITCH", "+2Hz")
        voice = os.environ.get("SMARTFLO_TTS_VOICE", "hi-IN-SwaraNeural")
        communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
        mp3_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buf.write(chunk["data"])
        mp3_data = mp3_buf.getvalue()
        if not mp3_data:
            return b""
        # Decode MP3 → PCM16 via pydub
        from pydub import AudioSegment
        seg = AudioSegment.from_mp3(io.BytesIO(mp3_data))
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        return seg.raw_data

    async def _send_mulaw_audio(self, mulaw: bytes) -> None:
        """Send mulaw audio to Smartflo in 160-byte chunks with chunk counter."""
        if not self.stream_sid:
            return
        self._speaking = True
        chunk_num = 1
        for offset in range(0, len(mulaw), MULAW_FRAME_BYTES):
            if not self._speaking:
                break  # barge-in cancelled playback
            frame = mulaw[offset : offset + MULAW_FRAME_BYTES]
            payload_b64 = base64.b64encode(frame).decode()
            try:
                await asyncio.wait_for(
                    self._send({
                        "event": "media",
                        "streamSid": self.stream_sid,
                        "media": {
                            "payload": payload_b64,
                            "chunk": str(chunk_num),
                        },
                    }),
                    timeout=_SEND_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                logger.warning("[smartflo-stream] send timeout — aborting playback")
                break
            chunk_num += 1
            await asyncio.sleep(FRAME_MS / 1000.0)  # pace at real-time
        self._speaking = False
        # Send mark to signal end of playback
        if self.stream_sid:
            try:
                await self._send({
                    "event": "mark",
                    "streamSid": self.stream_sid,
                    "mark": {"name": f"bot-{chunk_num}"},
                })
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Barge-in
    # ------------------------------------------------------------------ #
    async def _barge_in(self) -> None:
        """Interrupt bot playback, clear Smartflo buffer."""
        self._speaking = False
        self._barge_frames = 0
        if self.stream_sid:
            try:
                await asyncio.wait_for(
                    self._send({
                        "event": "clear",
                        "streamSid": self.stream_sid,
                    }),
                    timeout=_SEND_TIMEOUT_S,
                )
            except Exception:
                pass

    # ------------------------------------------------------------------ #
    # Greeting
    # ------------------------------------------------------------------ #
    async def _maybe_greet(self) -> None:
        if self._greeted:
            return
        self._greeted = True
        opener = self._caller_opening_line
        if not opener:
            opener = (
                f"Namaste! Main {self.client_name} ki virtual assistant bol rahi hoon. "
                "Aapki kya madad kar sakti hoon?"
            )
        self.hist.append({"role": "assistant", "content": opener})
        await self._say(opener)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _send(self, obj: dict[str, Any]) -> None:
        try:
            await self.ws.send_text(json.dumps(obj))
        except Exception as e:
            if not self._closed:
                logger.warning(f"[smartflo-stream] send failed: {e}")

    @staticmethod
    def _pcm16_rms(pcm16: bytes) -> int:
        """Compute RMS of PCM16 audio. Pure-Python (no audioop dependency)."""
        if len(pcm16) < 2:
            return 0
        n = len(pcm16) // 2
        s = 0
        for i in range(0, len(pcm16), 2):
            sample = struct.unpack_from("<h", pcm16, i)[0]
            s += sample * sample
        return int((s / n) ** 0.5) if n else 0

    async def _cleanup(self) -> None:
        """Idempotent cleanup: persist transcript + close WS."""
        if self._closed:
            return
        self._closed = True
        # Persist transcript (best-effort)
        try:
            await self._persist_transcript()
        except Exception as e:
            logger.debug(f"[smartflo-stream] transcript persist failed: {e}")
        # Meter call completion
        try:
            from app.telephony.post_call_hooks import meter_call_completion
            user_turns = sum(1 for m in self.hist if m.get("role") == "user")
            await meter_call_completion(
                client_id=self.client_id,
                call_duration_s=int(
                    (datetime.now(timezone.utc) - self._started_at).total_seconds()
                ),
                user_turns=user_turns,
                metadata={
                    "provider": "tata_smartflo",
                    "stream_sid": self.stream_sid,
                    "from": self.from_number,
                    "to": self.to_number,
                    "media_frames": self._media_frames,
                    "caller_rms_max": self._caller_rms_max,
                },
            )
        except Exception:
            pass
        # Close WS
        try:
            await self.ws.close()
        except Exception:
            pass

    async def _persist_transcript(self) -> None:
        """Save call transcript to disk."""
        if not self.hist:
            return
        import os
        transcript_dir = _call_transcripts_dir()
        os.makedirs(transcript_dir, exist_ok=True)
        ts = self._started_at.strftime("%Y%m%d_%H%M%S")
        sid = self.stream_sid or "unknown"
        filename = f"smartflo_{ts}_{sid[:12]}.json"
        filepath = os.path.join(transcript_dir, filename)
        record = {
            "provider": "tata_smartflo",
            "stream_sid": self.stream_sid,
            "call_sid": self.call_sid,
            "from": self.from_number,
            "to": self.to_number,
            "niche": self.niche,
            "client_id": self.client_id,
            "client_name": self.client_name,
            "started_at": self._started_at.isoformat(),
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "media_frames": self._media_frames,
            "caller_rms_max": self._caller_rms_max,
            "messages": self.hist,
        }
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False, indent=2)


__all__ = [
    "SmartfloStreamSession",
    "STT_AVAILABLE",
    "TTS_AVAILABLE",
    "mulaw_to_pcm16",
    "pcm16_to_mulaw",
    "pcm16_8k_to_16k",
    "pcm16_16k_to_8k",
]
