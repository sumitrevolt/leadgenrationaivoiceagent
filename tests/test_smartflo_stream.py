"""
Integration tests for Smartflo Voice Streaming WebSocket handler.

Tests the SmartfloStreamSession event lifecycle, media processing, DTMF
handling, greeting, and cleanup — all using mock WebSocket events (no real
Smartflo connection needed).

Protocol events tested:
  connected → start → media (speech/silence) → stop
  DTMF press-9 (opt-out)
  Mark events
  Non-JSON frames (error resilience)
"""

from __future__ import annotations

import asyncio
import base64
import json
import struct
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------
try:
    from app.telephony.smartflo_stream import (
        MULAW_FRAME_BYTES,
        SmartfloStreamSession,
        mulaw_to_pcm16,
        pcm16_to_mulaw,
    )

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="smartflo_stream not importable")


# ---------------------------------------------------------------------------
# Fake WebSocket (mirrors the FastAPI WebSocket interface)
# ---------------------------------------------------------------------------
class _FakeWS:
    """Mock WebSocket that records sent messages and simulates receive."""

    def __init__(self) -> None:
        self.accepted = False
        self.sent: list[dict[str, Any]] = []
        self.closed = False
        self._receive_queue: asyncio.Queue[str] = asyncio.Queue()
        self._receive_count = 0

    async def accept(self) -> None:
        self.accepted = True

    async def send_text(self, text: str) -> None:
        try:
            self.sent.append(json.loads(text))
        except Exception:
            self.sent.append({"_raw": text})

    async def receive_text(self) -> str:
        self._receive_count += 1
        return await self._receive_queue.get()

    async def close(self) -> None:
        self.closed = True

    def enqueue(self, event: dict[str, Any]) -> None:
        """Put an event into the receive queue."""
        self._receive_queue.put_nowait(json.dumps(event))

    def enqueue_raw(self, text: str) -> None:
        """Put raw text into the receive queue."""
        self._receive_queue.put_nowait(text)

    def enqueue_stop(self, reason: str = "caller hung up") -> None:
        """Convenience: enqueue a stop event."""
        self.enqueue({
            "event": "stop",
            "stop": {"reason": reason},
            "streamSid": "test-stream-001",
        })

    def enqueue_disconnect(self) -> None:
        """Simulate WebSocket disconnect (closes the receive loop)."""
        self._receive_queue.put_nowait(None)  # will cause an exception in handle()


def _make_silence_mulaw(n_bytes: int = 160) -> str:
    """Generate base64-encoded silence (mulaw 0xFF = PCM16 0)."""
    return base64.b64encode(b"\xff" * n_bytes).decode()


def _make_speech_mulaw(n_bytes: int = 160) -> str:
    """Generate base64-encoded speech-like audio (non-zero mulaw bytes)."""
    # Mulaw bytes 0x80-0xFE map to positive PCM16 values (non-silence)
    return base64.b64encode(bytes(range(0x80, 0x80 + n_bytes))).decode()


def _session(ws: _FakeWS | None = None, **kwargs: Any) -> SmartfloStreamSession:
    """Create a session with a fake WS and default params."""
    ws = ws or _FakeWS()
    return SmartfloStreamSession(
        websocket=ws,
        niche=kwargs.get("niche", "general"),
        client_id=kwargs.get("client_id"),
        client_name=kwargs.get("client_name", "Test Co"),
        lead_phone=kwargs.get("lead_phone"),
        opening_line=kwargs.get("opening_line", ""),
    )


# ---------------------------------------------------------------------------
# 1. WebSocket lifecycle
# ---------------------------------------------------------------------------
class TestWebSocketLifecycle:
    """WS accept → event loop → cleanup on stop."""

    async def test_accept_called_on_handle(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_stop()
        await s.handle()
        assert ws.accepted is True

    async def test_cleanup_called_on_stop(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_stop()
        await s.handle()
        assert ws.closed is True
        assert s._closed is True

    async def test_cleanup_idempotent(self):
        """Double-stop doesn't crash."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_stop()
        ws.enqueue_stop()
        await s.handle()
        assert s._closed is True

    async def test_handle_returns_on_disconnect(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_disconnect()
        await s.handle()
        # Session should be cleaned up
        assert s._closed is True


# ---------------------------------------------------------------------------
# 2. Connected event
# ---------------------------------------------------------------------------
class TestConnectedEvent:
    async def test_connected_sends_handshake_back(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({"event": "connected"})
        ws.enqueue_stop()
        await s.handle()
        # Should have sent a connected event back
        connected_msgs = [m for m in ws.sent if m.get("event") == "connected"]
        assert len(connected_msgs) >= 1

    async def test_connected_does_not_set_stream_sid(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({"event": "connected"})
        ws.enqueue_stop()
        await s.handle()
        assert s.stream_sid is None  # only start sets stream_sid


# ---------------------------------------------------------------------------
# 3. Start event
# ---------------------------------------------------------------------------
class TestStartEvent:
    async def test_start_extracts_metadata(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-abc-123",
            "start": {
                "streamSid": "MZ-abc-123",
                "callSid": "CA-xyz-789",
                "from": "919876543210",
                "to": "918012345678",
                "direction": "outbound",
                "customParameters": {
                    "niche": "salon_spa",
                    "client_id": "jiya-makeover",
                },
            },
        })
        ws.enqueue_stop()
        await s.handle()
        assert s.stream_sid == "MZ-abc-123"
        assert s.call_sid == "CA-xyz-789"
        assert s.from_number == "919876543210"
        assert s.to_number == "918012345678"
        assert s.niche == "salon_spa"
        assert s.client_id == "jiya-makeover"

    async def test_start_sends_ack(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-test",
            "start": {"streamSid": "MZ-test", "callSid": "CA-test"},
        })
        ws.enqueue_stop()
        await s.handle()
        acks = [m for m in ws.sent if m.get("event") == "start"]
        assert len(acks) >= 1
        assert acks[0].get("streamSid") == "MZ-test"

    async def test_start_sets_lead_phone_from_number(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {
                "streamSid": "MZ-1",
                "callSid": "CA-1",
                "from": "919876543210",
                "to": "918012345678",
            },
        })
        ws.enqueue_stop()
        await s.handle()
        assert s._lead_phone == "919876543210"

    async def test_start_overrides_niche_from_params(self):
        ws = _FakeWS()
        s = _session(ws, niche="general")
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {
                "streamSid": "MZ-1",
                "callSid": "CA-1",
                "customParameters": {"niche": "solar"},
            },
        })
        ws.enqueue_stop()
        await s.handle()
        assert s.niche == "solar"


# ---------------------------------------------------------------------------
# 4. Media event processing
# ---------------------------------------------------------------------------
class TestMediaEvent:
    async def test_media_event_counts_frames(self):
        ws = _FakeWS()
        s = _session(ws)
        # Send start first
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        # Send 5 media events with silence
        for _ in range(5):
            ws.enqueue({
                "event": "media",
                "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
            })
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 5
        assert s._media_bytes == 160 * 5

    async def test_media_event_with_empty_payload_skipped(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue({"event": "media", "media": {}})  # no payload
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 0

    async def test_media_event_with_nested_payload(self):
        """Smartflo Twilio-style: payload nested under media key."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue({
            "event": "media",
            "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
        })
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 1

    async def test_media_tracks_rms(self):
        """Speech-like audio should register nonzero RMS."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue({
            "event": "media",
            "media": {"payload": _make_speech_mulaw(160), "chunk": "1"},
        })
        ws.enqueue_stop()
        await s.handle()
        assert s._caller_rms_max > 0

    async def test_non_json_frame_does_not_crash(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_raw("this is not valid json {{{")
        ws.enqueue_stop()
        await s.handle()
        assert s._closed is True


# ---------------------------------------------------------------------------
# 5. DTMF handling
# ---------------------------------------------------------------------------
class TestDTMF:
    async def test_dtmf_9_triggers_cleanup(self):
        ws = _FakeWS()
        s = _session(ws, lead_phone="919876543210")
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue({"event": "dtmf", "dtmf": {"digit": "9"}})
        await s.handle()
        assert s._closed is True
        # Should have sent clear event
        clear_msgs = [m for m in ws.sent if m.get("event") == "clear"]
        assert len(clear_msgs) >= 1

    async def test_dtmf_other_digit_ignored(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue({"event": "dtmf", "dtmf": {"digit": "5"}})
        ws.enqueue_stop()
        await s.handle()
        assert s._closed is True
        # Should NOT have sent clear for digit 5
        clear_msgs = [m for m in ws.sent if m.get("event") == "clear"]
        assert len(clear_msgs) == 0


# ---------------------------------------------------------------------------
# 6. Mark event
# ---------------------------------------------------------------------------
class TestMarkEvent:
    async def test_mark_does_not_crash(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "mark",
            "streamSid": "MZ-1",
            "mark": {"name": "bot-100"},
        })
        ws.enqueue_stop()
        await s.handle()
        assert s._closed is True


# ---------------------------------------------------------------------------
# 7. Stop event
# ---------------------------------------------------------------------------
class TestStopEvent:
    async def test_stop_sets_closed(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue_stop("caller hung up")
        await s.handle()
        assert s._closed is True

    async def test_stop_with_different_reasons(self):
        for reason in ("caller hung up", "timeout", "provider disconnect"):
            ws = _FakeWS()
            s = _session(ws)
            ws.enqueue_stop(reason)
            await s.handle()
            assert s._closed is True


# ---------------------------------------------------------------------------
# 8. Greeting
# ---------------------------------------------------------------------------
class TestGreeting:
    async def test_greeting_sent_on_start(self):
        """Start event should trigger greeting (if TTS available)."""
        ws = _FakeWS()
        s = _session(ws, opening_line="Namaste! Main Swara bol rahi hoon.")
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue_stop()
        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock) as mock_say:
                await s.handle()
                assert mock_say.called
                # Greeting text should be in hist
                greetings = [m for m in s.hist if m["role"] == "assistant"]
                assert len(greetings) >= 1

    async def test_greeting_not_sent_twice(self):
        """_maybe_greet is idempotent."""
        ws = _FakeWS()
        s = _session(ws, opening_line="Namaste!")
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue_stop()
        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock) as mock_say:
                await s.handle()
                # _say called exactly once for greeting
                assert mock_say.call_count == 1

    async def test_default_greeting_includes_client_name(self):
        ws = _FakeWS()
        s = _session(ws, client_name="Sharma Salon")
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
        })
        ws.enqueue_stop()
        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock):
                await s.handle()
        greetings = [m for m in s.hist if m["role"] == "assistant"]
        assert len(greetings) >= 1
        assert "Sharma Salon" in greetings[0]["content"]


# ---------------------------------------------------------------------------
# 9. Full event sequence
# ---------------------------------------------------------------------------
class TestFullSequence:
    """End-to-end event sequence: connected → start → media × N → stop."""

    async def test_full_lifecycle(self):
        ws = _FakeWS()
        s = _session(ws, opening_line="Hello!")
        # Enqueue the full sequence
        ws.enqueue({"event": "connected"})
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-full-001",
            "start": {
                "streamSid": "MZ-full-001",
                "callSid": "CA-full-001",
                "from": "919876543210",
                "to": "918012345678",
                "direction": "inbound",
            },
        })
        # 10 silence frames
        for _ in range(10):
            ws.enqueue({
                "event": "media",
                "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
            })
        # 3 speech frames
        for _ in range(3):
            ws.enqueue({
                "event": "media",
                "media": {"payload": _make_speech_mulaw(160), "chunk": "1"},
            })
        # 5 more silence frames (turn boundary)
        for _ in range(5):
            ws.enqueue({
                "event": "media",
                "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
            })
        # A mark event
        ws.enqueue({"event": "mark", "streamSid": "MZ-full-001", "mark": {"name": "end"}})
        # Stop
        ws.enqueue_stop("caller hung up")

        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock):
                await s.handle()

        # Verify session state
        assert s.stream_sid == "MZ-full-001"
        assert s.call_sid == "CA-full-001"
        assert s.from_number == "919876543210"
        assert s.to_number == "918012345678"
        assert s._media_frames == 18  # 10 + 3 + 5
        assert s._closed is True
        assert ws.closed is True
        # Greeting was sent
        greetings = [m for m in s.hist if m["role"] == "assistant"]
        assert len(greetings) >= 1

    async def test_media_before_start_still_processed(self):
        """Media events before start should still be counted."""
        ws = _FakeWS()
        s = _session(ws)
        # Media BEFORE start
        ws.enqueue({
            "event": "media",
            "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
        })
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 1  # counted but no stream_sid


# ---------------------------------------------------------------------------
# 10. Transcript persistence
# ---------------------------------------------------------------------------
class TestTranscriptPersistence:
    async def test_transcript_saved_on_cleanup(self, tmp_path):
        ws = _FakeWS()
        s = _session(ws)
        s.hist = [
            {"role": "assistant", "content": "Namaste!"},
            {"role": "user", "content": "Haan boliye"},
        ]
        s.stream_sid = "MZ-transcript-001"
        s.call_sid = "CA-transcript-001"
        s.from_number = "919876543210"
        s.to_number = "918012345678"

        with patch("app.telephony.smartflo_stream._call_transcripts_dir", return_value=str(tmp_path)):
            await s._persist_transcript()

        files = list(tmp_path.glob("smartflo_*.json"))
        assert len(files) == 1
        with open(files[0]) as f:
            data = json.load(f)
        assert data["stream_sid"] == "MZ-transcript-001"
        assert data["from"] == "919876543210"
        assert len(data["messages"]) == 2

    async def test_empty_hist_no_transcript(self, tmp_path):
        ws = _FakeWS()
        s = _session(ws)
        s.hist = []
        with patch("app.telephony.smartflo_stream._call_transcripts_dir", return_value=str(tmp_path)):
            await s._persist_transcript()
        files = list(tmp_path.glob("smartflo_*.json"))
        assert len(files) == 0


# ---------------------------------------------------------------------------
# 11. Custom parameters override
# ---------------------------------------------------------------------------
class TestCustomParameters:
    async def test_lead_phone_from_start_params(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {
                "streamSid": "MZ-1",
                "callSid": "CA-1",
                "from": "919999999999",
                "customParameters": {"lead_phone": "918888888888"},
            },
        })
        ws.enqueue_stop()
        await s.handle()
        # lead_phone from customParameters should win over 'from'
        assert s._lead_phone == "918888888888"

    async def test_client_id_from_params(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({
            "event": "start",
            "streamSid": "MZ-1",
            "start": {
                "streamSid": "MZ-1",
                "callSid": "CA-1",
                "customParameters": {"client_id": "jiya-makeover"},
            },
        })
        ws.enqueue_stop()
        await s.handle()
        assert s.client_id == "jiya-makeover"


# ---------------------------------------------------------------------------
# 12. Constants
# ---------------------------------------------------------------------------
class TestConstants:
    def test_mulaw_frame_bytes(self):
        assert MULAW_FRAME_BYTES == 160  # 8kHz * 20ms
