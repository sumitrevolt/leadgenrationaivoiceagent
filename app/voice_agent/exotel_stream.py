"""
Exotel Voicebot Stream — AgentStream bidirectional WS bridge.
=============================================================

Exotel ke Voicebot applet (App Bazar flow: Greeting -> Voicebot) se aane wale
bidirectional stream ko existing voice pipeline (PhoneCallSession: energy VAD ->
faster-whisper STT -> LLMBrain -> EdgeTTS) se jodta hai. Vobiz/Twilio path se
PROTOCOL differences:

    Vobiz/Twilio                      Exotel Voicebot (AgentStream)
    ------------                      -----------------------------
    G.711 u-law 8k, 20ms frames       raw/slin PCM16 LE mono (8k default;
                                      ?sample-rate=16000|24000 query param)
    camelCase keys (streamSid)        snake_case keys (stream_sid) — parent
                                      dono pehle se handle karta hai
    160B u-law frames out             PCM16 chunks: MULTIPLE of 320 bytes,
                                      min ~3.2KB, max 100KB per frame
    clear:{streamSid}                 clear:{stream_sid}

Spec: docs.exotel.com/exotel-agentstream/voicebot-applet (events: connected/
start/media/dtmf/stop/mark/clear; media.payload = base64 PCM16 LE mono).

Endpoint (main.py): ``/ws/exotel-voicebot`` — applet me URL:
    wss://leadsgenai.in/ws/exotel-voicebot?sample-rate=16000
optional custom params (max 3, Exotel limit): niche / client_name / client_id.

Import-safe + never-raise (project pattern): heavy deps lazy via parent; koi bhi
failure graceful degrade karta hai, socket crash nahi hota.
"""

from __future__ import annotations

import asyncio
import base64
from typing import Any

from fastapi import WebSocket

from app.utils.logger import setup_logger
from app.voice_agent.phone_stream import (
    _AUDIOOP_OK,
    SR_8K,
    PhoneCallSession,
    audioop,
)

logger = setup_logger(__name__)

SUPPORTED_RATES = (8000, 16000, 24000)
_VAD_FRAME_BYTES = 320  # 20ms PCM16 @ 8kHz — parent VAD isi granularity par tuned

# TRAI: AI disclosure mandatory — greeting me hamesha ho.
_AI_DISCLOSURE = "Main ek AI assistant bol rahi hoon. "


def _chunk_bytes(sample_rate: int) -> int:
    """Outbound chunk size: >=3.2KB aur 320 ka multiple (Exotel spec).
    8k->3200B(200ms) · 16k->3200B(100ms) · 24k->4800B(100ms)."""
    per_100ms = sample_rate // 10 * 2  # 16-bit mono
    return max(3200, per_100ms)


class ExotelVoicebotSession(PhoneCallSession):
    """Ek live Exotel Voicebot call ka session — PhoneCallSession ka PCM16
    adapter. VAD/STT/LLM/TTS/barge-in sab parent se reuse; sirf wire format
    (decode/encode/chunking/clear) Exotel-specific hai."""

    def __init__(
        self,
        websocket: WebSocket,
        sample_rate: int = SR_8K,
        niche: str = "general",
        client_name: str = "LeadGen AI",
        client_id: str | None = None,
    ) -> None:
        super().__init__(websocket, niche=niche, client_name=client_name, client_id=client_id)
        self.sample_rate = sample_rate if sample_rate in SUPPORTED_RATES else SR_8K
        self._rate_state: Any = None  # audioop.ratecv streaming state (inbound)
        self._inbound_rem = b""  # 320B alignment ke liye leftover
        self._out_chunk_seq = 0
        self._out_ms = 0.0

    # ------------------------------------------------------------------ #
    # Inbound: start / media
    # ------------------------------------------------------------------ #
    async def _handle_start(self, data: dict[str, Any]) -> None:
        """start.media_format se actual sample_rate pick karo (query param se
        zyada authoritative), phir parent (sids + custom_parameters + greeting)."""
        start = data.get("start") or {}
        mf = start.get("media_format") or start.get("mediaFormat") or {}
        try:
            sr = int(str(mf.get("sample_rate") or mf.get("sampleRate") or 0))
            if sr in SUPPORTED_RATES:
                self.sample_rate = sr
        except Exception:
            pass
        logger.info("exotel_stream: media_format=%s -> sample_rate=%d", mf, self.sample_rate)
        await super()._handle_start(data)

    async def _handle_media(self, data: dict[str, Any]) -> None:
        """Exotel media: base64 PCM16 LE mono @ self.sample_rate (chunks ~100ms,
        size variable). Decode -> 8k resample (streaming state) -> 320B frames
        -> parent VAD (turn detection + barge-in sab wahi)."""
        payload = (data.get("media") or {}).get("payload")
        if not payload or not _AUDIOOP_OK:
            return
        try:
            pcm = base64.b64decode(payload)
        except Exception:
            return
        if not pcm:
            return
        if self.sample_rate != SR_8K:
            try:
                pcm, self._rate_state = audioop.ratecv(
                    pcm, 2, 1, self.sample_rate, SR_8K, self._rate_state
                )
            except Exception:
                return
        buf = self._inbound_rem + pcm
        usable = len(buf) - (len(buf) % _VAD_FRAME_BYTES)
        self._inbound_rem = buf[usable:]
        for i in range(0, usable, _VAD_FRAME_BYTES):
            self._vad_on_frame(buf[i : i + _VAD_FRAME_BYTES])

    # ------------------------------------------------------------------ #
    # Outbound: TTS -> PCM16 @ negotiated rate -> chunked media frames
    # ------------------------------------------------------------------ #
    async def _synthesize(self, text: str) -> bytes:
        """EdgeTTS mp3 (parent _edge_mp3 — prosody env-tuned) -> PCM16 mono @
        self.sample_rate (u-law NAHI — Exotel slin). Failure par b''."""
        try:
            mp3 = await self._edge_mp3(text)
            if not mp3:
                return b""
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._mp3_to_pcm, mp3, self.sample_rate)
        except Exception as e:
            logger.warning("exotel_stream: TTS failed (%s)", e)
            return b""

    def _mp3_to_wire(self, mp3_bytes: bytes) -> bytes:
        """Filler clips bhi PCM16 @ negotiated rate me (parent µ-law default
        Exotel pipe me noise ban jaata)."""
        return self._mp3_to_pcm(mp3_bytes, self.sample_rate)

    def _tts_voice(self) -> str:
        from app.voice_agent.phone_stream import TTS_VOICE

        return TTS_VOICE

    @staticmethod
    def _mp3_to_pcm(mp3_bytes: bytes, sample_rate: int) -> bytes:
        """Blocking: mp3 -> PCM16 LE mono @ sample_rate (pydub/ffmpeg)."""
        try:
            import io

            from pydub import AudioSegment  # lazy (needs ffmpeg binary)

            seg = AudioSegment.from_file(io.BytesIO(mp3_bytes), format="mp3")
            seg = seg.set_frame_rate(sample_rate).set_channels(1).set_sample_width(2)
            return seg.raw_data or b""
        except Exception as e:
            logger.warning("exotel_stream: mp3->pcm decode failed (%s)", e)
            return b""

    async def _send_audio(self, pcm: bytes) -> None:
        """PCM16 ko Exotel-spec chunks (320B multiple, >=3.2KB) me paced bhejo.
        Har chunk se pehle barge-in/stop check — interrupt par abort + clear."""
        if not self.stream_sid or not pcm:
            return
        chunk_size = _chunk_bytes(self.sample_rate)
        # last partial chunk ko 320B boundary par zero-pad (spec: multiple of 320)
        if len(pcm) % _VAD_FRAME_BYTES:
            pcm += b"\x00" * (_VAD_FRAME_BYTES - len(pcm) % _VAD_FRAME_BYTES)
        self._interrupt = False
        self._bot_speaking = True
        try:
            for i in range(0, len(pcm), chunk_size):
                if self._interrupt or not self._running:
                    logger.debug("exotel_stream: outbound aborted (barge-in/stop)")
                    await self._send_clear()
                    break
                frame = pcm[i : i + chunk_size]
                self._out_chunk_seq += 1
                await self._send_json(
                    {
                        "event": "media",
                        "stream_sid": self.stream_sid,
                        "media": {
                            "chunk": self._out_chunk_seq,
                            "timestamp": str(int(self._out_ms)),
                            "payload": base64.b64encode(frame).decode("ascii"),
                        },
                    }
                )
                dur = len(frame) / (2.0 * self.sample_rate)  # seconds
                self._out_ms += dur * 1000.0
                await asyncio.sleep(dur)
        finally:
            self._bot_speaking = False

    async def _send_clear(self) -> None:
        """Barge-in par Exotel ka buffered (not-yet-played) audio flush."""
        if not self.stream_sid:
            return
        try:
            await self._send_json({"event": "clear", "stream_sid": self.stream_sid})
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # TRAI compliance — greeting me AI disclosure guarantee
    # ------------------------------------------------------------------ #
    async def _greeting_text(self) -> str:
        text = await super()._greeting_text()
        low = (text or "").lower()
        if "ai" not in low and "artificial" not in low:
            text = _AI_DISCLOSURE + (text or "")
        return text


__all__ = ["ExotelVoicebotSession", "SUPPORTED_RATES"]
