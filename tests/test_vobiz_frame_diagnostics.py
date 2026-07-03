"""Regression tests for the 2026-07-03 raw WS frame-capture diagnostic.

Context: the "inbound-deaf" bug (phone-agent-deaf-stt-zero memory) has one
symptom — `inbound_frames=0` in the call summary — but THREE possible causes,
and the pre-existing code silently dropped every one of them with zero signal:
  1. Vobiz never sends a "media"-type event at all (carrier/route-level).
  2. Vobiz sends "media" events but the payload is empty/unrecognized shape.
  3. The payload is present but isn't valid base64 (encoding mismatch).
These tests lock in the new counters (`_media_event_count`,
`_media_empty_payload_count`, `_media_decode_fail_count`,
`_event_type_counts`, `_nonjson_frame_count`) that make the three cases
distinguishable from a single call's log line, without changing any existing
audio-handling behavior.
"""

from __future__ import annotations

import base64
import json

from app.telephony import vobiz_stream as vs


class _FakeWS:
    async def accept(self) -> None:  # pragma: no cover - unused here
        pass

    async def send_text(self, text: str) -> None:  # pragma: no cover
        pass

    async def close(self) -> None:  # pragma: no cover
        pass

    async def receive(self) -> dict:  # pragma: no cover
        return {"type": "websocket.disconnect"}


def _session() -> vs.VobizStreamSession:
    return vs.VobizStreamSession(_FakeWS(), niche="general", client_name="Test Co")


async def test_media_event_with_nested_payload_counts_both(monkeypatch):
    """The common Vobiz shape: {"event":"media","media":{"payload":"<b64>"}}."""
    s = _session()
    silence = base64.b64encode(b"\x00\x00" * 320).decode()
    raw = json.dumps({"event": "media", "media": {"payload": silence}})
    await s._on_event(raw)
    assert s._media_event_count == 1
    assert s._media_frames == 1
    assert s._media_empty_payload_count == 0
    assert s._media_decode_fail_count == 0
    assert s._event_type_counts.get("media") == 1


async def test_media_event_with_flat_payload_still_counts(monkeypatch):
    """The flat-payload fallback shape: {"event":"media","payload":"<b64>"}."""
    s = _session()
    silence = base64.b64encode(b"\x00\x00" * 320).decode()
    raw = json.dumps({"event": "media", "payload": silence})
    await s._on_event(raw)
    assert s._media_event_count == 1
    assert s._media_frames == 1


async def test_media_event_with_empty_payload_is_a_distinct_anomaly():
    """This is the case that used to be a silent no-op: media_event_count
    must go up even though media_frames (inbound_frames) stays 0 — that gap
    is exactly what tells us Vobiz sent the event but not usable audio."""
    s = _session()
    raw = json.dumps({"event": "media", "media": {}})
    await s._on_event(raw)
    assert s._media_event_count == 1
    assert s._media_frames == 0
    assert s._media_empty_payload_count == 1


async def test_media_payload_bad_base64_counts_decode_failure():
    s = _session()
    await s._on_media("not-valid-base64!!!")
    assert s._media_decode_fail_count == 1
    assert s._media_frames == 0


async def test_nonjson_frame_is_counted_not_just_logged():
    s = _session()
    await s._on_event("this is not json")
    assert s._nonjson_frame_count == 1


async def test_event_type_counts_track_every_event_kind():
    s = _session()
    await s._on_event(json.dumps({"event": "start", "start": {}}))
    await s._on_event(json.dumps({"event": "media", "media": {}}))
    await s._on_event(json.dumps({"event": "stop"}))
    assert s._event_type_counts == {"start": 1, "media": 1, "stop": 1}


async def test_anomaly_logging_is_throttled_to_three(monkeypatch):
    """Long calls can have thousands of frames — don't spam the log if every
    single one is an anomaly; only the first 3 raw-shape dumps are useful."""
    s = _session()
    for _ in range(10):
        await s._on_event(json.dumps({"event": "media", "media": {}}))
    assert s._media_empty_payload_count == 10
    assert s._media_anomaly_logged == 3
