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
        if self._receive_queue.empty():
            if self.closed:
                # Real WS semantics: receive after server-side close raises —
                # lets handle()'s read loop exit instead of blocking forever
                # (2026-09-04 CI shard-4 hang: tests enqueued only `stop`, so
                # handle() blocked on queue.get() until the 60s idle timeout).
                raise RuntimeError("WebSocket disconnected after close")
            # Mirror prod idle-timeout with a bounded wait so a misbehaving
            # test fails fast instead of hanging the whole shard.
            try:
                return await asyncio.wait_for(self._receive_queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                raise RuntimeError("FakeWS receive idle timeout (5s)") from None
        return self._receive_queue.get_nowait()

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
        self.enqueue(
            {
                "event": "stop",
                "stop": {"reason": reason},
                "streamSid": "test-stream-001",
            }
        )

    def enqueue_disconnect(self) -> None:
        """Simulate WebSocket disconnect (closes the receive loop)."""
        self._receive_queue.put_nowait(None)  # will cause an exception in handle()


def _make_silence_mulaw(n_bytes: int = 160) -> str:
    """Generate base64-encoded silence (mulaw 0xFF = PCM16 0)."""
    return base64.b64encode(b"\xff" * n_bytes).decode()


def _make_speech_mulaw(n_bytes: int = 160) -> str:
    """Generate base64-encoded speech-like audio (non-zero mulaw bytes)."""
    # Mulaw bytes 0x80-0xFE map to positive PCM16 values (non-silence);
    # wrap mod 256 so n_bytes > 128 stays valid (2026-09-04 fix: range
    # 0x80..0x120 raised ValueError for the default 160-byte payload).
    return base64.b64encode(bytes((0x80 + i) % 256 for i in range(n_bytes))).decode()


# ---------------------------------------------------------------------------
# Structural write isolation (autouse, 2026-09-10)
#
# `_persist_opt_out` really calls `consent_ledger.record_opt_out` and `_cleanup`
# really calls `post_call_hooks.finalize_stream_session` (the P0 fail-open fix).
# Both are correct; what was wrong is that this file let them hit the REAL
# `data/consent_ledger.jsonl` / `data/interactions.jsonl`. One stray opt-out row
# for +919876543210 permanently poisoned the unrelated
# test_telephony_upgrades.py::test_compliance_fails_closed_on_unverified_dnd
# (it saw `opted_out` instead of `dnd_lookup_failed`).
#
# So isolation is structural: EVERY test here gets in-memory writers. Tests that
# assert on these calls already patch them with `unittest.mock.patch`; an inner
# patch simply wins inside its `with` block, so nothing fights.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolate_stream_runtime_writers(request, monkeypatch, tmp_path):
    """No test in this module may write to real runtime data files."""
    from tests._stream_runtime_isolation import install_fixture

    return install_fixture(request, monkeypatch, tmp_path)


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
    async def test_connected_does_not_echo_back(self):
        """Spec conformance: `connected` is provider -> endpoint ONLY.

        integration.txt v11 §2.1 makes `connected` the first frame the WebSocket
        server RECEIVES. §3 ("Events Received from the Vendor") lists only
        media/mark/clear as endpoint -> provider events, and §5 spells it out:
        "Client to Vendor: Send connected -> start -> media -> stop. Vendor to
        Client: Receive media -> mark -> clear."

        This test previously asserted the opposite (an echo), which was an
        out-of-spec frame. It now locks the spec behaviour.
        """
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({"event": "connected"})
        ws.enqueue_stop()
        await s.handle()
        echoed = [m for m in ws.sent if m.get("event") == "connected"]
        assert echoed == [], f"connected must not be echoed back, got {echoed}"

    async def test_connected_is_handled_without_error(self):
        """We still HANDLE `connected` (log + continue) — just never echo it."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({"event": "connected"})
        ws.enqueue_stop()
        await s.handle()
        assert s.stream_sid is None  # only start sets stream_sid

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
        ws.enqueue(
            {
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
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-test",
                "start": {"streamSid": "MZ-test", "callSid": "CA-test"},
            }
        )
        ws.enqueue_stop()
        await s.handle()
        acks = [m for m in ws.sent if m.get("event") == "start"]
        assert len(acks) >= 1
        assert acks[0].get("streamSid") == "MZ-test"

    async def test_start_sets_lead_phone_from_number(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {
                    "streamSid": "MZ-1",
                    "callSid": "CA-1",
                    "from": "919876543210",
                    "to": "918012345678",
                },
            }
        )
        ws.enqueue_stop()
        await s.handle()
        assert s._lead_phone == "919876543210"

    async def test_start_overrides_niche_from_params(self):
        ws = _FakeWS()
        s = _session(ws, niche="general")
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {
                    "streamSid": "MZ-1",
                    "callSid": "CA-1",
                    "customParameters": {"niche": "solar"},
                },
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        # Send 5 media events with silence
        for _ in range(5):
            ws.enqueue(
                {
                    "event": "media",
                    "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
                }
            )
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 5
        assert s._media_bytes == 160 * 5

    async def test_media_event_with_empty_payload_skipped(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue({"event": "media", "media": {}})  # no payload
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 0

    async def test_media_event_with_nested_payload(self):
        """Smartflo Twilio-style: payload nested under media key."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue(
            {
                "event": "media",
                "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
            }
        )
        ws.enqueue_stop()
        await s.handle()
        assert s._media_frames == 1

    async def test_media_tracks_rms(self):
        """Speech-like audio should register nonzero RMS."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue(
            {
                "event": "media",
                "media": {"payload": _make_speech_mulaw(160), "chunk": "1"},
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue({"event": "dtmf", "dtmf": {"digit": "9"}})
        await s.handle()
        assert s._closed is True
        # Should have sent clear event
        clear_msgs = [m for m in ws.sent if m.get("event") == "clear"]
        assert len(clear_msgs) >= 1

    async def test_dtmf_other_digit_ignored(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
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
        ws.enqueue(
            {
                "event": "mark",
                "streamSid": "MZ-1",
                "mark": {"name": "bot-100"},
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue_stop()
        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock) as mock_say:
                await s.handle()
                # _say called exactly once for greeting
                assert mock_say.call_count == 1


# ---------------------------------------------------------------------------
# 9. Compliance / billing regressions (P0-1, P0-2, P0-3)
#
# These three are here because the pre-existing DTMF test only asserted
# cleanup — it never asserted the ledger write, which is precisely why the
# dead ``persist_opt_out`` import survived. Assert on the EFFECT, not on the
# code running.
# ---------------------------------------------------------------------------
def _start_frame() -> dict[str, Any]:
    return {
        "event": "start",
        "streamSid": "MZ-1",
        "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
    }


class TestPress9OptOutLedger:
    """P0-1: press-9 MUST write to the consent ledger (TCCCPR)."""

    async def test_press9_writes_opt_out_to_consent_ledger(self):
        """record_opt_out is really invoked, with the real kwarg contract.

        Fails against the old code: it imported ``ConsentAction`` /
        ``persist_opt_out``, neither of which exists in consent_ledger.py, so
        the ImportError was swallowed and nothing was ever recorded.
        """
        ws = _FakeWS()
        s = _session(ws, lead_phone="919876543210")

        captured: dict[str, Any] = {}

        def _fake_record_opt_out(phone, **kwargs):
            captured["phone"] = phone
            captured.update(kwargs)
            return {"ok": True}

        ws.enqueue(_start_frame())
        ws.enqueue({"event": "dtmf", "dtmf": {"digit": "9"}})

        with patch(
            "app.telephony.consent_ledger.record_opt_out",
            new=_fake_record_opt_out,
        ), patch(
            "app.telephony.post_call_hooks.finalize_stream_session",
            new_callable=AsyncMock,
        ):
            await s.handle()

        assert captured, (
            "record_opt_out was NEVER called — press-9 opt-out is dead code again"
        )
        assert captured["phone"] == "919876543210"
        assert captured["reason"] == "smartflo_dtmf_press9"
        assert captured["channel"] == "voice"
        assert captured["call_id"] == "MZ-1"
        # ...and the call still tears down (opt-out must not wedge the socket).
        assert s._closed is True

    async def test_press9_warns_when_no_lead_phone(self):
        """No phone → no silent no-op: it must warn and skip, not crash."""
        ws = _FakeWS()
        s = _session(ws, lead_phone=None)
        s._lead_phone = None
        ws.enqueue(_start_frame())
        ws.enqueue({"event": "dtmf", "dtmf": {"digit": "9"}})
        with patch(
            "app.telephony.consent_ledger.record_opt_out",
            new=MagicMock(side_effect=AssertionError("must not be called")),
        ), patch(
            "app.telephony.post_call_hooks.finalize_stream_session",
            new_callable=AsyncMock,
        ):
            await s.handle()
        assert s._closed is True


class TestGreetingAIDisclosure:
    """P0-2: the opener must go through the shared disclosure helpers."""

    async def test_greeting_carries_ai_disclosure_marker(self):
        """Asserts on the marker list in niche_scripts, not a copied sentence."""
        from app.voice_agent.niche_scripts import (
            _AI_DISCLOSURE_TOKENS,
            ensure_ai_disclosure,
            ensure_permission_ask,
        )

        calls: list[str] = []

        def _spy_disclosure(text, *a, **kw):
            calls.append("ensure_ai_disclosure")
            return ensure_ai_disclosure(text, *a, **kw)

        def _spy_permission(text, *a, **kw):
            calls.append("ensure_permission_ask")
            return ensure_permission_ask(text, *a, **kw)

        ws = _FakeWS()
        # Deliberately NO AI token in the raw opener, so the helper must inject.
        s = _session(ws, opening_line="Namaste! Main Swara bol rahi hoon.")
        ws.enqueue(_start_frame())
        ws.enqueue_stop()

        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True), patch(
            "app.voice_agent.niche_scripts.ensure_ai_disclosure", new=_spy_disclosure
        ), patch(
            "app.voice_agent.niche_scripts.ensure_permission_ask", new=_spy_permission
        ), patch.object(
            s, "_say", new_callable=AsyncMock
        ), patch(
            "app.telephony.post_call_hooks.finalize_stream_session",
            new_callable=AsyncMock,
        ):
            await s.handle()

        # 1. It actually routes through the shared helpers (not an inline copy).
        assert "ensure_ai_disclosure" in calls
        assert "ensure_permission_ask" in calls
        # 2. The spoken/history opener carries a recognised disclosure marker.
        greetings = [m["content"] for m in s.hist if m.get("role") == "assistant"]
        assert greetings, "no assistant opener in history"
        opener = greetings[0]
        low = opener.lower()
        assert any(tok in low for tok in _AI_DISCLOSURE_TOKENS), (
            f"opener has NO AI disclosure marker from _AI_DISCLOSURE_TOKENS: {opener!r}"
        )


class TestEndOfCallQualification:
    """P0-3: end of call must reach the qualify/billing entry point."""

    async def test_cleanup_invokes_finalize_stream_session(self):
        ws = _FakeWS()
        s = _session(ws, lead_phone="919876543210")
        ws.enqueue(_start_frame())
        ws.enqueue_stop()

        with patch(
            "app.telephony.post_call_hooks.finalize_stream_session",
            new_callable=AsyncMock,
        ) as mock_finalize:
            await s.handle()

        assert mock_finalize.call_count == 1
        kwargs = mock_finalize.call_args.kwargs
        # DOUBLE-METERING GUARD: the stream must bill under the PROVIDER call id
        # (start.callSid), never under stream_sid, so the webhook's
        # `call_meter:{call_id}` dedupe key lines up with ours.
        assert kwargs["call_id"] == "CA-1"
        assert kwargs["phone"] == "919876543210"
        assert kwargs["client_id"] == (s.client_id or "")
        assert kwargs["niche"] == s.niche
        assert kwargs["started_at"] == s._started_at
        assert kwargs["extra_transcript"]["provider"] == "tata_smartflo"
        # 2026-09-10: without this the analytics call_logs row is written with
        # provider="phone", so Smartflo calls can never be broken out on the
        # dashboard (vobiz_stream.py:3374 passes provider="vobiz").
        assert kwargs["provider"] == "tata_smartflo"

    async def test_default_greeting_includes_client_name(self):
        ws = _FakeWS()
        s = _session(ws, client_name="Sharma Salon")
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-full-001",
                "start": {
                    "streamSid": "MZ-full-001",
                    "callSid": "CA-full-001",
                    "from": "919876543210",
                    "to": "918012345678",
                    "direction": "inbound",
                },
            }
        )
        # 10 silence frames
        for _ in range(10):
            ws.enqueue(
                {
                    "event": "media",
                    "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
                }
            )
        # 3 speech frames
        for _ in range(3):
            ws.enqueue(
                {
                    "event": "media",
                    "media": {"payload": _make_speech_mulaw(160), "chunk": "1"},
                }
            )
        # 5 more silence frames (turn boundary)
        for _ in range(5):
            ws.enqueue(
                {
                    "event": "media",
                    "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
                }
            )
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
        ws.enqueue(
            {
                "event": "media",
                "media": {"payload": _make_silence_mulaw(160), "chunk": "1"},
            }
        )
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

        with patch(
            "app.telephony.smartflo_stream._call_transcripts_dir", return_value=str(tmp_path)
        ):
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
        with patch(
            "app.telephony.smartflo_stream._call_transcripts_dir", return_value=str(tmp_path)
        ):
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
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {
                    "streamSid": "MZ-1",
                    "callSid": "CA-1",
                    "from": "919999999999",
                    "customParameters": {"lead_phone": "918888888888"},
                },
            }
        )
        ws.enqueue_stop()
        await s.handle()
        # lead_phone from customParameters should win over 'from'
        assert s._lead_phone == "918888888888"

    async def test_client_id_from_params(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {
                    "streamSid": "MZ-1",
                    "callSid": "CA-1",
                    "customParameters": {"client_id": "jiya-makeover"},
                },
            }
        )
        ws.enqueue_stop()
        await s.handle()
        assert s.client_id == "jiya-makeover"


# ---------------------------------------------------------------------------
# 12. Constants
# ---------------------------------------------------------------------------
class TestConstants:
    def test_mulaw_frame_bytes(self):
        assert MULAW_FRAME_BYTES == 160  # 8kHz * 20ms


# ---------------------------------------------------------------------------
# 13. Demo-readiness regressions (2026-09-07, pre Tata demo-account live test)
# ---------------------------------------------------------------------------
class TestDemoReadinessRegressions:
    async def test_groq_stt_uploads_wav_container_not_raw_pcm(self):
        """Regression: raw PCM was posted as 'audio.wav' → Groq 400 every time."""
        import app.telephony.smartflo_stream as ss

        s = _session()
        captured: dict[str, Any] = {}

        class _Resp:
            status_code = 200
            text = "namaste"

        class _Client:
            def __init__(self, *a, **k):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, headers=None, files=None, data=None):
                captured["files"] = files
                captured["data"] = data
                return _Resp()

        fake_httpx = MagicMock()
        fake_httpx.AsyncClient = _Client
        pcm = b"\x00\x01" * 1600  # 100ms PCM16 16kHz
        with patch.dict("sys.modules", {"httpx": fake_httpx}):
            with patch.object(ss, "_groq_key", return_value="gsk_test"):
                text = await s._groq_stt(pcm)
        assert text == "namaste"
        name, fileobj, mime = captured["files"]["file"]
        body = fileobj.getvalue()
        assert name.endswith(".wav") and mime == "audio/wav"
        assert body[:4] == b"RIFF" and body[8:12] == b"WAVE"
        assert body.endswith(pcm)  # payload preserved after the 44-byte header
        assert captured["data"]["model"] == "whisper-large-v3"

    def test_pcm16_to_wav_header_declares_16k_mono(self):
        import io as _io
        import wave

        from app.telephony.smartflo_stream import pcm16_to_wav

        pcm = b"\x10\x00" * 320
        with wave.open(_io.BytesIO(pcm16_to_wav(pcm)), "rb") as wf:
            assert wf.getframerate() == 16000
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.readframes(wf.getnframes()) == pcm

    async def test_say_does_not_block_receive_loop_and_barge_in_cancels(self):
        """Regression: playback ran inline → no inbound frames read while
        speaking → barge-in dead. Now _say() returns immediately, playback runs
        as a task, and caller speech cancels it + emits `clear`."""
        import app.telephony.smartflo_stream as ss

        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-1"
        # 2 s of "speech" = 100 frames of 160 mulaw bytes → would take ~2 s inline
        long_audio = b"\x00\x00" * 16000

        async def _fake_tts(_text: str) -> bytes:
            return long_audio

        with patch.object(ss, "TTS_AVAILABLE", True):
            with patch.object(s, "_tts", side_effect=_fake_tts):
                t0 = asyncio.get_event_loop().time()
                await s._say("lambi baat")
                assert asyncio.get_event_loop().time() - t0 < 0.5  # non-blocking
                assert s._play_task is not None and not s._play_task.done()
                # Let a few frames go out
                await asyncio.sleep(0.15)
                assert s._speaking is True
                sent_before = len([m for m in ws.sent if m.get("event") == "media"])
                assert sent_before >= 3
                # Caller speaks over the bot → barge-in
                for _ in range(3):
                    await s._on_media(_make_speech_mulaw())
                await asyncio.sleep(0.05)
                assert s._speaking is False
                assert s._play_task is None
                assert any(m.get("event") == "clear" for m in ws.sent)
                sent_after = len([m for m in ws.sent if m.get("event") == "media"])
                # Playback truncated well short of the full 100 frames
                assert sent_after < 60

    async def test_cleanup_cancels_in_flight_playback(self):
        import app.telephony.smartflo_stream as ss

        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-1"

        async def _slow_tts(_text: str) -> bytes:
            await asyncio.sleep(5)
            return b"\x00\x00" * 160

        with patch.object(ss, "TTS_AVAILABLE", True):
            with patch.object(s, "_tts", side_effect=_slow_tts):
                await s._say("hello")
                task = s._play_task
                assert task is not None
                await s._cleanup()
                await asyncio.sleep(0)
                assert task.cancelled() or task.done()
                assert s._play_task is None
                assert ws.closed

    async def test_start_accepts_snake_case_keys(self):
        """Smartflo's exact casing is unconfirmed until the live call — accept both."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "stream_sid": "SN-1",
                "start": {
                    "stream_sid": "SN-1",
                    "call_sid": "CS-1",
                    "from": "919999999999",
                    "to": "918000000000",
                    "custom_parameters": {"niche": "salon", "client_id": "c-1"},
                },
            }
        )
        ws.enqueue_stop()
        await s.handle()
        assert s.stream_sid == "SN-1"
        assert s.call_sid == "CS-1"
        assert s.niche == "salon"
        assert s.client_id == "c-1"

    async def test_default_greeting_discloses_ai(self):
        """§5 TRAI invariant: AI-disclosure at call start."""
        ws = _FakeWS()
        s = _session(ws, client_name="Sharma Salon")
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-1",
                "start": {"streamSid": "MZ-1", "callSid": "CA-1"},
            }
        )
        ws.enqueue_stop()
        with patch("app.telephony.smartflo_stream.TTS_AVAILABLE", True):
            with patch.object(s, "_say", new_callable=AsyncMock):
                await s.handle()
        opener = [m for m in s.hist if m["role"] == "assistant"][0]["content"]
        assert "AI assistant" in opener


# ---------------------------------------------------------------------------
# Provider protocol contract — PDF §2.2 / §3.1 / §3.2 (2026-09-11)
#
# Three criteria were only partially met before this change:
#   * `start` carried accountSid/direction in the contract but we dropped them
#   * outbound media shipped a <160-byte runt frame per utterance, which the
#     vendor documents as causing audible gaps
#   * mark names were reused (`bot-{chunk_num}`) and inbound acks were only
#     logged, so nothing tied an ack to one utterance and `clear` left the
#     registry dangling
# ---------------------------------------------------------------------------
class TestProviderProtocolContract:
    async def test_start_captures_account_sid_and_direction(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-contract-1",
                "start": {
                    "streamSid": "MZ-contract-1",
                    "accountSid": "AC-contract-1",
                    "callSid": "CA-contract-1",
                    "direction": "inbound",
                    "from": "919876543210",
                    "to": "918069879757",
                    "mediaFormat": {
                        "encoding": "audio/x-mulaw",
                        "sampleRate": 8000,
                        "bitRate": 64,
                        "bitDepth": 8,
                    },
                    "customParameters": {},
                },
            }
        )
        ws.enqueue_stop()
        with patch.object(s, "_say", new_callable=AsyncMock):
            await s.handle()
        assert s.stream_sid == "MZ-contract-1"
        assert s.call_sid == "CA-contract-1"
        assert s.account_sid == "AC-contract-1"
        assert s.direction == "inbound"

    async def test_start_captures_snake_case_account_and_direction(self):
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue(
            {
                "event": "start",
                "streamSid": "MZ-contract-2",
                "start": {
                    "account_sid": "AC-contract-2",
                    "call_sid": "CA-contract-2",
                    "direction": "outbound",
                },
            }
        )
        ws.enqueue_stop()
        with patch.object(s, "_say", new_callable=AsyncMock):
            await s.handle()
        assert s.account_sid == "AC-contract-2"
        assert s.call_sid == "CA-contract-2"
        assert s.direction == "outbound"

    async def test_outbound_media_payloads_are_multiples_of_160(self):
        """PDF §3.1: a payload that is not a multiple of 160 bytes gaps audio."""
        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-framing-1"
        # 200 bytes = one full 160-byte frame + a 40-byte runt that must be padded.
        await s._send_mulaw_audio(b"\x7f" * 200, s._playback_generation)
        frames = [m for m in ws.sent if m.get("event") == "media"]
        assert len(frames) == 2, frames
        for m in frames:
            raw = base64.b64decode(m["media"]["payload"])
            assert len(raw) >= MULAW_FRAME_BYTES
            assert len(raw) % MULAW_FRAME_BYTES == 0

    async def test_no_stream_sid_drops_audio_and_warns_once(self):
        """Silent-failure guard.

        Without a `streamSid` we cannot address a media frame to the provider, so
        the utterance is synthesised and dropped. That used to happen with no
        warning at all, which on a live call looks like "the AI heard me but never
        spoke". The drop must now set a one-shot flag (which drives the warning).
        """
        ws = _FakeWS()
        s = _session(ws)
        assert s.stream_sid is None
        assert s._warned_no_stream_sid is False
        await s._send_mulaw_audio(b"\x7f" * 160, s._playback_generation)
        assert [m for m in ws.sent if m.get("event") == "media"] == []
        assert s._warned_no_stream_sid is True

    async def test_barge_in_generation_mismatch_is_not_flagged(self):
        """A cancelled generation is NORMAL — it must not trip the warning flag."""
        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-barge"
        await s._send_mulaw_audio(b"\x7f" * 160, s._playback_generation + 1)
        assert s._warned_no_stream_sid is False

    async def test_mark_names_are_unique_per_utterance(self):
        """PDF §3.2: the ack echoes mark.name, so the label identifies one utterance."""
        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-mark-1"
        await s._send_mulaw_audio(b"\x7f" * 160, s._playback_generation)
        await s._send_mulaw_audio(b"\x7f" * 160, s._playback_generation)
        names = [m["mark"]["name"] for m in ws.sent if m.get("event") == "mark"]
        assert len(names) == 2
        assert len(set(names)) == 2, f"mark names must be unique, got {names}"

    async def test_mark_ack_resolves_the_pending_mark(self):
        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-mark-2"
        await s._send_mulaw_audio(b"\x7f" * 160, s._playback_generation)
        name = next(m["mark"]["name"] for m in ws.sent if m.get("event") == "mark")
        assert name in s._pending_marks
        ws.enqueue({"event": "mark", "streamSid": "MZ-mark-2", "mark": {"name": name}})
        ws.enqueue_stop()
        await s.handle()
        assert name not in s._pending_marks

    async def test_clear_resolves_pending_marks_and_stops_playback(self):
        """Barge-in must drop unplayed audio AND its outstanding marks."""
        ws = _FakeWS()
        s = _session(ws)
        s.stream_sid = "MZ-clear-1"
        await s._send_mulaw_audio(b"\x7f" * 320, s._playback_generation)
        assert s._pending_marks, "a mark should be awaiting an ack"
        await s._barge_in()
        assert s._pending_marks == {}
        assert s._speaking is False
        assert any(m.get("event") == "clear" for m in ws.sent)

    async def test_unknown_mark_ack_never_raises(self):
        """After a clear the provider acks marks we have already resolved."""
        ws = _FakeWS()
        s = _session(ws)
        ws.enqueue({"event": "mark", "streamSid": "MZ-ghost", "mark": {"name": "ghost"}})
        ws.enqueue_stop()
        await s.handle()
        assert s._pending_marks == {}
