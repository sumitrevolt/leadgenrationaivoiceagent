"""
Twilio Media Streams Bridge (Dograh-inspired)
=============================================

Bridges a LIVE phone call's bidirectional audio to the voice pipeline over a
WebSocket, emulating Dograh's media-stream pattern.

Twilio Media Streams protocol (JSON text frames over the WS):
    {"event": "connected", ...}
    {"event": "start", "start": {"streamSid": "...", "callSid": "...", ...}}
    {"event": "media", "media": {"payload": "<base64 mu-law 8kHz>", ...}}
    {"event": "stop",  "stop": {...}}

Inbound `media.payload` is base64-encoded mu-law (G.711 u-law) audio at 8kHz.
We forward inbound audio to the VoicePipeline (lazy-imported — another agent
owns it) and stream TTS audio BACK as outbound `media` frames:
    {"event": "media", "streamSid": "...", "media": {"payload": "<base64>"}}

Design goals (match telephony_service.py style):
    - import-safe: never crash at import even if pipeline/SDKs missing.
    - defensive: NEVER crash on a malformed frame — log and continue.
    - lazy: VoicePipeline imported on first use; degrade to echo/log if absent.

Usage from a FastAPI WebSocket route (wired by main.py separately):

    from fastapi import WebSocket
    from app.telephony.media_stream import TwilioMediaStreamBridge

    @app.websocket("/api/telephony/media-stream")
    async def media_stream(ws: WebSocket):
        await ws.accept()
        bridge = TwilioMediaStreamBridge()
        await bridge.handle(ws)
"""
import asyncio
import base64
import json
from typing import Any, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class TwilioMediaStreamBridge:
    """
    Handles one Twilio Media Streams WebSocket connection.

    Construct one bridge per accepted WebSocket, then `await bridge.handle(ws)`.
    The bridge parses inbound frames, forwards caller audio to the voice
    pipeline, and writes the pipeline's TTS audio back as outbound media frames.
    """

    def __init__(self, pipeline: Optional[Any] = None):
        # Optional pre-built pipeline; otherwise lazily resolved on first audio.
        self._pipeline = pipeline
        self._pipeline_tried = pipeline is not None

        # Populated from the "start" frame.
        self.stream_sid: Optional[str] = None
        self.call_sid: Optional[str] = None

        # Counters for diagnostics.
        self._inbound_frames = 0
        self._outbound_frames = 0
        self._started = False
        self._stopped = False

    # ------------------------------------------------------------------ #
    # Pipeline resolution (lazy, import-safe)
    # ------------------------------------------------------------------ #
    def _get_pipeline(self) -> Optional[Any]:
        """
        Lazily import + construct app.voice_agent.pipeline.VoicePipeline.

        Another agent owns that module; it may not exist yet. We import it on
        first use and cache the result (including a None failure) so we don't
        retry the import on every audio frame.
        """
        if self._pipeline_tried:
            return self._pipeline

        self._pipeline_tried = True
        try:
            from app.voice_agent.pipeline import VoicePipeline  # type: ignore
            self._pipeline = VoicePipeline()
            logger.info("🎙️ MediaStreamBridge: VoicePipeline loaded.")
        except Exception as e:
            self._pipeline = None
            logger.warning(
                f"MediaStreamBridge: VoicePipeline unavailable ({e}); "
                f"running in ECHO/LOG mode (no real audio synthesis)."
            )
        return self._pipeline

    # ------------------------------------------------------------------ #
    # Outbound frame encoding
    # ------------------------------------------------------------------ #
    def _encode_media_frame(self, stream_sid: str, audio_bytes: bytes) -> str:
        """
        Encode raw outbound mu-law audio bytes into a Twilio media JSON frame.

        Returns the JSON string ready to send over the WebSocket. Twilio expects
        base64 mu-law 8kHz in `media.payload`.
        """
        payload = base64.b64encode(audio_bytes or b"").decode("ascii")
        return json.dumps(
            {
                "event": "media",
                "streamSid": stream_sid,
                "media": {"payload": payload},
            }
        )

    def _encode_mark_frame(self, stream_sid: str, name: str) -> str:
        """Encode a 'mark' frame — lets us know when playback finished."""
        return json.dumps(
            {"event": "mark", "streamSid": stream_sid, "mark": {"name": name}}
        )

    def _encode_clear_frame(self, stream_sid: str) -> str:
        """Encode a 'clear' frame — flush any buffered outbound audio (barge-in)."""
        return json.dumps({"event": "clear", "streamSid": stream_sid})

    # ------------------------------------------------------------------ #
    # Main loop
    # ------------------------------------------------------------------ #
    async def handle(self, websocket: Any) -> None:
        """
        Drive the Media Streams session until the socket closes or 'stop'.

        `websocket` is a FastAPI/Starlette WebSocket that has already been
        accept()'d by the caller. We never raise out of here — a malformed
        frame or transport error is logged and the loop ends cleanly.
        """
        logger.info("📡 Twilio Media Stream connected — awaiting frames.")
        try:
            while True:
                try:
                    raw = await websocket.receive_text()
                except Exception as e:
                    # Client closed / transport error / WebSocketDisconnect.
                    logger.info(f"Media stream closed: {e}")
                    break

                frame = self._safe_parse(raw)
                if frame is None:
                    continue  # malformed — already logged, keep going.

                event = frame.get("event")

                if event == "connected":
                    logger.debug("Media stream: 'connected' handshake received.")
                elif event == "start":
                    await self._on_start(websocket, frame)
                elif event == "media":
                    await self._on_media(websocket, frame)
                elif event == "mark":
                    logger.debug(f"Media stream mark: {frame.get('mark')}")
                elif event == "stop":
                    await self._on_stop(frame)
                    break
                else:
                    logger.debug(f"Media stream: ignoring unknown event '{event}'.")
        except Exception as e:
            # Absolute backstop — bridge must never crash the route.
            logger.error(f"Media stream bridge fatal (handled): {e}")
        finally:
            logger.info(
                f"📡 Media stream ended (call_sid={self.call_sid}, "
                f"in={self._inbound_frames}, out={self._outbound_frames})."
            )

    @staticmethod
    def _safe_parse(raw: str) -> Optional[dict]:
        """Parse a JSON frame defensively. Returns None on any problem."""
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return data
            logger.warning("Media stream frame was not a JSON object — skipping.")
            return None
        except Exception as e:
            logger.warning(f"Malformed media stream frame skipped: {e}")
            return None

    # ------------------------------------------------------------------ #
    # Event handlers
    # ------------------------------------------------------------------ #
    async def _on_start(self, websocket: Any, frame: dict) -> None:
        """Capture streamSid / callSid from the 'start' frame."""
        start = frame.get("start") or {}
        self.stream_sid = start.get("streamSid") or frame.get("streamSid")
        self.call_sid = start.get("callSid")
        self._started = True
        logger.info(
            f"▶️ Media stream START (streamSid={self.stream_sid}, "
            f"callSid={self.call_sid})."
        )

        # Optionally greet the caller via pipeline (best-effort).
        pipeline = self._get_pipeline()
        greet = getattr(pipeline, "get_opening_audio", None) if pipeline else None
        if greet is None:
            return
        try:
            audio = await self._maybe_await(greet())
            await self._send_audio(websocket, audio)
        except Exception as e:
            logger.debug(f"Opening audio skipped: {e}")

    async def _on_media(self, websocket: Any, frame: dict) -> None:
        """
        Decode inbound caller audio and forward it to the voice pipeline.

        If the pipeline returns response audio, stream it back as outbound
        media frames. If no pipeline is available, run in echo/log mode.
        """
        self._inbound_frames += 1
        media = frame.get("media") or {}
        payload_b64 = media.get("payload")
        if not payload_b64:
            return

        try:
            audio_in = base64.b64decode(payload_b64)
        except Exception as e:
            logger.debug(f"Bad base64 media payload skipped: {e}")
            return

        pipeline = self._get_pipeline()
        if pipeline is None:
            # ECHO / LOG mode — no pipeline. Periodically log inbound activity.
            if self._inbound_frames % 100 == 0:
                logger.debug(
                    f"[echo-mode] received {self._inbound_frames} inbound "
                    f"audio frames ({len(audio_in)} bytes last)."
                )
            return

        # Feed inbound audio to the pipeline. We support a few likely method
        # names so this works regardless of the pipeline's exact API.
        try:
            audio_out = await self._push_to_pipeline(pipeline, audio_in)
        except Exception as e:
            logger.debug(f"Pipeline processing error (handled): {e}")
            audio_out = None

        if audio_out:
            await self._send_audio(websocket, audio_out)

    async def _on_stop(self, frame: dict) -> None:
        """Handle the 'stop' frame — finalize the session."""
        self._stopped = True
        logger.info(f"⏹️ Media stream STOP (callSid={self.call_sid}).")
        pipeline = self._get_pipeline()
        closer = getattr(pipeline, "on_call_end", None) if pipeline else None
        if closer is None:
            return
        try:
            await self._maybe_await(closer(self.call_sid))
        except Exception as e:
            logger.debug(f"Pipeline on_call_end error (handled): {e}")

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    async def _push_to_pipeline(self, pipeline: Any, audio_in: bytes):
        """
        Forward inbound mu-law audio to the pipeline, trying common method
        names. Returns outbound audio bytes (mu-law) or None.
        """
        for name in ("process_audio_chunk", "process_audio", "push_audio", "feed"):
            fn = getattr(pipeline, name, None)
            if callable(fn):
                return await self._maybe_await(fn(audio_in))
        # No known ingest method — nothing to do.
        return None

    async def _send_audio(self, websocket: Any, audio_bytes: Optional[bytes]) -> None:
        """Send raw mu-law audio back as a Twilio outbound media frame."""
        if not audio_bytes or not self.stream_sid or websocket is None:
            return
        try:
            await websocket.send_text(
                self._encode_media_frame(self.stream_sid, audio_bytes)
            )
            self._outbound_frames += 1
        except Exception as e:
            logger.debug(f"Failed to send outbound media frame (handled): {e}")

    @staticmethod
    async def _maybe_await(value: Any) -> Any:
        """Await `value` if it's awaitable, else return it as-is."""
        if asyncio.iscoroutine(value) or isinstance(value, asyncio.Future):
            return await value
        return value
