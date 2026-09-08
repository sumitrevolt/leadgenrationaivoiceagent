"""Regression tests for the Swara AI-telecaller call flow (SmartFlo WS streaming).

Context (2026-09-08, prod incident @ leadsgenai.in)
--------------------------------------------------
Symptom: calls disconnect immediately as they connect.
Prod log signature::

    "WebSocket /api/telephony/smartflo/stream" [accepted]
    [smartflo-stream] WS open niche=general client=None (STT=True TTS=True audioop=True)
    [smartflo-stream] WS error: (<CloseCode.NO_STATUS_RCVD: 1005>, '')

i.e. the socket is accepted, then dropped ~58ms later with NO ``connected`` and
NO ``start`` event ever arriving -> the provider tears the stream down during
the handshake. Separately, ``SIP_DID`` is empty and the FreeSWITCH ``vobiz``
gateway reports ``NOREG``.

These tests lock down the two things that must stay true after any fix:

1. The stream handler survives a FULL synthetic handshake
   (``connected`` -> ``start`` -> N ``media`` frames -> ``stop``) without
   closing the socket early, and ``media_frames`` / ``caller_rms_max`` both
   end up > 0.
2. The DID / caller-ID resolution used by the active outbound path never
   returns an empty number.

Hermetic by design
------------------
* no network, no real secrets, no DB, no FreeSWITCH
* STT/TTS/LLM are monkeypatched; transcripts are written to ``tmp_path``
* safe to run in CI  (``pytest tests/test_swara_smartflo_callflow.py``)

Compliance note: nothing here weakens a gate (DND / TRAI window / consent /
AI-disclosure). The greeting assertion below in fact *asserts* the AI-disclosure
opener is still emitted.
"""

from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import math
import struct
from typing import Any

import pytest

from app.telephony import smartflo_stream as ss
from app.telephony.smartflo_stream import SmartfloStreamSession, pcm16_to_mulaw

# --------------------------------------------------------------------------- #
# Deterministic audio helpers (real G.711 mu-law, no random data)
# --------------------------------------------------------------------------- #

_MULAW_SILENCE_BYTE = 0xFF  # mulaw encoding of PCM 0


def _pcm16(freq: float = 440.0, rate: int = 8000, n: int = 160, amp: int = 9000) -> bytes:
    """Build n samples of a PCM16 mono sine tone."""
    return b"".join(
        struct.pack("<h", int(amp * math.sin(2 * math.pi * freq * i / rate)))
        for i in range(n)
    )


def _loud_mulaw_frame() -> str:
    """Base64 mu-law of a 20ms 8kHz loud tone -> RMS far above the VAD floor."""
    return base64.b64encode(pcm16_to_mulaw(_pcm16(amp=9000))).decode()


def _silent_mulaw_frame() -> str:
    """Base64 mu-law of 20ms of digital silence -> RMS 0."""
    return base64.b64encode(bytes([_MULAW_SILENCE_BYTE]) * 160).decode()


def _media_event(payload: str, chunk: int) -> dict[str, Any]:
    return {
        "event": "media",
        "media": {"payload": payload, "chunk": str(chunk), "timestamp": str(chunk * 20)},
    }


def _connected_event() -> dict[str, Any]:
    return {"event": "connected"}


def _start_event(
    stream_sid: str = "SM_QA_0001",
    call_sid: str = "CA_QA_0001",
    src: str = "+919999999999",
    dst: str = "+918069879757",
) -> dict[str, Any]:
    return {
        "event": "start",
        "start": {
            "streamSid": stream_sid,
            "callSid": call_sid,
            "from": src,
            "to": dst,
            "direction": "inbound",
            "mediaFormat": {
                "encoding": "audio/x-mulaw",
                "sampleRate": 8000,
                "bitRate": 64,
                "bitDepth": 8,
            },
        },
    }


def _stop_event(reason: str = "caller_hangup") -> dict[str, Any]:
    return {"event": "stop", "stop": {"reason": reason}}


# --------------------------------------------------------------------------- #
# Fake WebSocket: queue-driven so the test controls timing deterministically
# --------------------------------------------------------------------------- #


class _FakeWS:
    """Minimal stand-in for FastAPI's ``WebSocket``.

    Records everything sent, counts everything received, and refuses traffic
    after ``close()`` -- that is what lets us assert the socket was NOT dropped
    mid-call.
    """

    def __init__(self) -> None:
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self.sent: list[str] = []
        self.closed = False
        self.accept_called = False
        self.received = 0
        self._eof = False

    # -- FastAPI WebSocket surface ------------------------------------------ #
    async def accept(self) -> None:
        self.accept_called = True

    async def send_text(self, data: str) -> None:
        if self.closed:
            raise RuntimeError("send_text() after close - socket was dropped early")
        self.sent.append(data)

    async def close(self, code: int = 1000) -> None:
        self.closed = True

    async def receive_text(self) -> str:
        if self.closed or self._eof:
            raise RuntimeError("no more frames")
        frame = await self._q.get()
        self.received += 1
        return frame

    # -- test-driver surface ------------------------------------------------ #
    async def feed(self, obj: dict[str, Any] | str) -> None:
        await self._q.put(obj if isinstance(obj, str) else json.dumps(obj))

    def finish(self) -> None:
        """Tell the handler there will be no more frames (clean EOF)."""
        self._eof = True

    @property
    def events(self) -> list[dict[str, Any]]:
        out = []
        for raw in self.sent:
            try:
                out.append(json.loads(raw))
            except Exception:  # pragma: no cover - defensive
                out.append({"_raw": raw})
        return out

    def names(self) -> list[str]:
        return [e.get("event", "?") for e in self.events]


# --------------------------------------------------------------------------- #
# Session factory with the heavy/remote parts stubbed out
# --------------------------------------------------------------------------- #


def _build_session(
    ws: _FakeWS,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    *,
    tts_samples: int = 160,
) -> SmartfloStreamSession:
    """Create a SmartfloStreamSession with STT/TTS/LLM stubbed and transcripts
    redirected to ``tmp_path``. No network, no real secrets, no prod writes."""
    monkeypatch.setattr(ss, "_call_transcripts_dir", lambda: str(tmp_path))
    monkeypatch.setattr(ss, "TTS_AVAILABLE", True)
    monkeypatch.setattr(ss, "STT_AVAILABLE", True)

    sess = SmartfloStreamSession(websocket=ws, niche="general")

    async def _fake_tts(text: str) -> bytes:
        # PCM16 16kHz (2 bytes/sample). Kept tiny so playback is 1-2 frames.
        return _pcm16(rate=16000, n=tts_samples, amp=8000)

    async def _fake_stt(pcm_16k: bytes) -> str:
        return "haan ji, main sun raha hoon"

    async def _fake_llm_reply(user_text: str) -> str:
        return "Bilkul sir, main aapki madad kar sakti hoon."

    sess._tts = _fake_tts            # type: ignore[method-assign]
    sess._stt = _fake_stt            # type: ignore[method-assign]
    sess._llm_reply = _fake_llm_reply  # type: ignore[method-assign]
    return sess


# --------------------------------------------------------------------------- #
# 1. Full synthetic handshake
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_synthetic_handshake_survives_connected_start_media_stop(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """connected -> start -> 25 loud + 45 silent media frames -> stop.

    The handler must:
      * accept the socket and keep it open for the whole call
      * end with media_frames > 0 AND caller_rms_max > 0
      * emit the AI-disclosure greeting
      * close cleanly (and only) on ``stop``
      * persist a post-call artifact with sane numbers
    """
    ws = _FakeWS()
    sess = _build_session(ws, monkeypatch, tmp_path)

    task = asyncio.create_task(sess.handle())

    await ws.feed(_connected_event())
    await ws.feed(_start_event())
    for i in range(25):
        await ws.feed(_media_event(_loud_mulaw_frame(), i + 1))
    # 45 x 20ms = 900ms of silence > the 800ms utterance boundary -> STT->LLM->TTS
    for i in range(45):
        await ws.feed(_media_event(_silent_mulaw_frame(), 26 + i))

    await asyncio.sleep(0)  # let the greeting / playback task make progress
    # >>> the socket must still be alive after the whole media burst <<<
    assert not sess._closed, "session closed itself before the caller hung up"
    assert not ws.closed, "WebSocket was closed before the 'stop' event"

    await ws.feed(_stop_event())
    await asyncio.wait_for(task, timeout=15)

    # --- socket lifecycle ------------------------------------------------- #
    assert ws.accept_called, "handler never accepted the WebSocket"
    assert ws.closed is True, "handler did not close the socket on stop"
    assert sess._closed is True, "session not marked closed after stop"
    assert ws.received == 1 + 1 + 25 + 45 + 1, (
        f"only {ws.received} frames consumed - socket dropped early"
    )

    # --- call quality counters (the regression we care about) -------------- #
    assert sess._media_frames > 0, "media_frames == 0 -> no caller audio reached the bot"
    assert sess._caller_rms_max > 0, "caller_rms_max == 0 -> caller audio was silence"
    assert sess._media_frames == 70
    # a loud 440Hz tone at amp 9000 must clear the default VAD floor (300)
    assert sess._caller_rms_max > 300, (
        f"caller_rms_max={sess._caller_rms_max} never crossed the VAD threshold"
    )

    # --- identifiers captured from the start event -------------------------- #
    assert sess.stream_sid == "SM_QA_0001"
    assert sess.call_sid == "CA_QA_0001"
    assert sess.from_number == "+919999999999"
    assert sess.to_number == "+918069879757"

    # --- compliance: AI-disclosure opener must still be spoken -------------- #
    assert sess.hist, "no transcript history recorded"
    opener = sess.hist[0]["content"]
    assert "AI assistant" in opener, (
        f"AI-disclosure missing from opener: {opener!r} (TRAI/§5 invariant)"
    )

    # --- post-call artifact -------------------------------------------------- #
    artifacts = sorted(tmp_path.glob("*.json"))
    assert artifacts, "post-call artifact was not written"
    rec = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert rec["provider"] == "tata_smartflo"
    assert rec["stream_sid"] == "SM_QA_0001"
    assert rec["media_frames"] > 0, "artifact media_frames is 0"
    assert rec["caller_rms_max"] > 0, "artifact caller_rms_max is 0"
    assert rec["messages"], "artifact has no transcript messages"
    started = dt.datetime.fromisoformat(rec["started_at"])
    ended = dt.datetime.fromisoformat(rec["ended_at"])
    assert (ended - started).total_seconds() >= 0, "artifact duration is negative"


@pytest.mark.asyncio
async def test_handshake_tolerates_snake_case_start_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """SmartFlo's exact casing is not fully confirmed. The handler must accept
    both camelCase and snake_case without dropping the stream."""
    ws = _FakeWS()
    sess = _build_session(ws, monkeypatch, tmp_path)
    task = asyncio.create_task(sess.handle())

    await ws.feed(_connected_event())
    await ws.feed(
        {
            "event": "start",
            "start": {
                "stream_sid": "SM_snake_01",
                "call_sid": "CA_snake_01",
                "from": "+918888888888",
                "to": "+918069879757",
                "media_format": {"encoding": "audio/x-mulaw", "sampleRate": 8000},
            },
        }
    )
    for i in range(10):
        await ws.feed(_media_event(_loud_mulaw_frame(), i + 1))
    await ws.feed(_stop_event())
    await asyncio.wait_for(task, timeout=15)

    assert sess.stream_sid == "SM_snake_01", "snake_case stream_sid was not parsed"
    assert sess._media_frames == 10
    assert sess._caller_rms_max > 0
    assert ws.received == 13, "frames were dropped on a snake_case start event"


@pytest.mark.asyncio
async def test_barge_in_clears_playback(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """While the bot is speaking, 3+ speech frames must fire barge-in:
    playback cancels and a ``clear`` event goes back to SmartFlo."""
    ws = _FakeWS()
    # ~1s of playback so there is a real window to interrupt
    sess = _build_session(ws, monkeypatch, tmp_path, tts_samples=8000)
    task = asyncio.create_task(sess.handle())

    await ws.feed(_connected_event())
    await ws.feed(_start_event())
    # quiet frames while the greeting plays out
    for i in range(10):
        await ws.feed(_media_event(_silent_mulaw_frame(), i + 1))

    for _ in range(60):  # give the playback task time to actually start
        await asyncio.sleep(0.01)
        if sess._speaking:
            break
    assert sess._speaking, "bot playback never started - barge-in cannot be tested"

    # caller starts talking over the bot
    for i in range(6):
        await ws.feed(_media_event(_loud_mulaw_frame(), 100 + i))
        await asyncio.sleep(0.01)

    assert sess._speaking is False, "barge-in did not stop playback"
    assert "clear" in ws.names(), "barge-in did not send a 'clear' event"

    await ws.feed(_stop_event())
    await asyncio.wait_for(task, timeout=15)
    assert sess._media_frames > 0


# --------------------------------------------------------------------------- #
# 2. DID / caller-ID resolution never returns empty
# --------------------------------------------------------------------------- #

_VOBIZ_DID = "+911171366938"
_TATA_DID = "918069879757"
_SIP_DID = "918069879757"


def _set(monkeypatch: pytest.MonkeyPatch, **kw: str) -> None:
    for k, v in kw.items():
        monkeypatch.setenv(k, v)


def _clear(monkeypatch: pytest.MonkeyPatch, *names: str) -> None:
    for n in names:
        monkeypatch.delenv(n, raising=False)


def test_pick_trunk_returns_non_empty_caller_id_for_vobiz(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.telephony.trunks import pick_trunk

    _clear(monkeypatch, "VOBIZ_AUTH_ID", "VOBIZ_AUTH_TOKEN", "VOBIZ_CALLER_ID",
           "JIO_SIP_HOST", "JIO_SIP_USER", "JIO_SIP_PASS", "JIO_SIP_DID",
           "JIO_TRUNK_ENABLED", "TATA_SMARTFLO_API_TOKEN", "TATA_SMARTFLO_API_KEY",
           "TATA_SMARTFLO_DID", "TATA_SMARTFLO_ENABLED")
    _set(monkeypatch,
         VOBIZ_AUTH_ID="MA_TEST", VOBIZ_AUTH_TOKEN="tok_test",
         VOBIZ_CALLER_ID=_VOBIZ_DID)

    provider, caller_id = pick_trunk(lead=None)
    assert provider == "vobiz"
    assert caller_id, "pick_trunk() returned an EMPTY caller-ID for the active trunk"
    assert caller_id == _VOBIZ_DID


def test_pick_trunk_never_returns_trunk_without_caller_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A trunk with creds but no DID must be skipped, not returned with ''."""
    from app.telephony.trunks import pick_trunk

    _clear(monkeypatch, "VOBIZ_AUTH_ID", "VOBIZ_AUTH_TOKEN", "VOBIZ_CALLER_ID",
           "JIO_SIP_HOST", "JIO_SIP_USER", "JIO_SIP_PASS", "JIO_SIP_DID",
           "JIO_TRUNK_ENABLED", "TATA_SMARTFLO_API_TOKEN", "TATA_SMARTFLO_API_KEY",
           "TATA_SMARTFLO_DID", "TATA_SMARTFLO_ENABLED")
    _set(monkeypatch, VOBIZ_AUTH_ID="MA_TEST", VOBIZ_AUTH_TOKEN="tok_test",
         VOBIZ_CALLER_ID="")  # creds present, DID missing -> the reported prod bug

    provider, caller_id = pick_trunk(lead=None)
    assert (provider, caller_id) == ("none", ""), (
        "a DID-less trunk was selected - outbound would place a call with no caller-ID"
    )


@pytest.mark.parametrize(
    "provider_env,expected_caller_id",
    [
        pytest.param(
            {
                "TATA_SMARTFLO_API_TOKEN": "tok_test",
                "TATA_SMARTFLO_API_KEY": "key_test",
                "TATA_SMARTFLO_DID": _TATA_DID,
                "TATA_SMARTFLO_ENABLED": "1",
            },
            _TATA_DID,
            id="tata_smartflo",
        ),
        pytest.param(
            {
                "JIO_SIP_HOST": "sip.example.in",
                "JIO_SIP_USER": "user",
                "JIO_SIP_PASS": "pass",
                "JIO_SIP_DID": _SIP_DID,
                "JIO_TRUNK_ENABLED": "1",
            },
            _SIP_DID,
            id="jio_mobile",
        ),
    ],
)
def test_pick_trunk_resolves_did_for_each_armed_trunk(
    monkeypatch: pytest.MonkeyPatch, provider_env: dict[str, str], expected_caller_id: str
) -> None:
    from app.telephony.trunks import pick_trunk

    _clear(monkeypatch, "VOBIZ_AUTH_ID", "VOBIZ_AUTH_TOKEN", "VOBIZ_CALLER_ID",
           "JIO_SIP_HOST", "JIO_SIP_USER", "JIO_SIP_PASS", "JIO_SIP_DID",
           "JIO_TRUNK_ENABLED", "TATA_SMARTFLO_API_TOKEN", "TATA_SMARTFLO_API_KEY",
           "TATA_SMARTFLO_DID", "TATA_SMARTFLO_ENABLED")
    _set(monkeypatch, **provider_env)

    provider, caller_id = pick_trunk(lead={"transactional": True})
    assert provider != "none", f"trunk not selected for {provider_env}"
    assert caller_id == expected_caller_id
    assert caller_id.strip(), "resolved caller-ID is empty"


def test_compliance_gate_caller_id_is_non_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ComplianceGate blocks promotional calls with 'no_caller_id' -- the
    resolver must therefore never hand back an empty string."""
    from app.telephony.compliance import ComplianceGate

    _set(monkeypatch, VOBIZ_CALLER_ID=_VOBIZ_DID)
    # Force the env path to be deterministic. `hasattr` guard matters: pydantic
    # Settings rejects monkeypatch's teardown for attributes it does not declare.
    try:
        from app.config import settings

        if hasattr(settings, "vobiz_caller_id"):
            monkeypatch.setattr(settings, "vobiz_caller_id", "", raising=False)
    except Exception:
        pass

    cid = ComplianceGate._caller_id()
    assert cid.strip(), "ComplianceGate._caller_id() returned empty -> promo calls blocked"
    assert cid.strip() == _VOBIZ_DID


def test_smartflo_client_did_resolves_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """TataSmartfloClient.did is what /test-call shows as the caller-ID."""
    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    _set(monkeypatch,
         TATA_SMARTFLO_API_TOKEN="tok_test",
         TATA_SMARTFLO_API_KEY="key_test",
         TATA_SMARTFLO_DID=_TATA_DID)
    try:
        from app.config import settings

        # `hasattr` guard: Settings does not declare `tata_smartflo_did`, so
        # monkeypatch would explode on teardown trying to delete it.
        if hasattr(settings, "tata_smartflo_did"):
            monkeypatch.setattr(settings, "tata_smartflo_did", "", raising=False)
    except Exception:
        pass

    client = TataSmartfloClient()
    assert client.did.strip(), "TataSmartfloClient.did is empty -> no caller-ID on C2C calls"
    assert client.did == _TATA_DID


def test_wss_host_has_no_scheme(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stream URL is built as f'wss://{host}/...' -- a host carrying a
    scheme would produce 'wss://wss://...'. SMARTFLO_WS_HOST must be bare."""
    from app.api.telephony_smartflo import _wss_host

    _set(monkeypatch, SMARTFLO_WS_HOST="leadsgenai.in")
    host = _wss_host()
    assert host, "SMARTFLO_WS_HOST resolved empty"
    assert "://" not in host, f"host must be bare, got {host!r}"


# --------------------------------------------------------------------------- #
# Regression guard: post-call metering must call the REAL meter_call_completion
# signature. Fixed 2026-09-08 - it previously raised TypeError (wrong kwargs)
# which `except Exception: pass` swallowed, so calls were never metered/billed.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_cleanup_meters_call_with_usable_duration(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    try:
        from app.telephony import post_call_hooks
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"post_call_hooks not importable: {exc}")

    seen: dict[str, Any] = {}

    async def _spy(**kwargs: Any) -> bool:
        seen.update(kwargs)
        return True

    monkeypatch.setattr(post_call_hooks, "meter_call_completion", _spy)

    ws = _FakeWS()
    sess = _build_session(ws, monkeypatch, tmp_path)
    task = asyncio.create_task(sess.handle())
    await ws.feed(_connected_event())
    await ws.feed(_start_event())
    await ws.feed(_media_event(_loud_mulaw_frame(), 1))
    await ws.feed(_stop_event())
    await asyncio.wait_for(task, timeout=15)

    assert seen, "meter_call_completion was never reached (silently swallowed)"
    assert "duration_seconds" in seen, (
        f"wrong kwarg name sent to meter_call_completion: {sorted(seen)}"
    )


# --------------------------------------------------------------------------- #
# Regression guard: Tata SmartFlo C2C caller_id must be FULL E.164.
# Fixed 2026-09-08 - `place_call()` used `_clean_number()` for the caller_id,
# which stripped the leading `91` (918069879757 -> 8069879757). SmartFlo rejects
# the 10-digit form with HTTP 422 {"caller_id": "Provide a vaild caller_id."},
# so NO outbound call was ever placed. `customer_number` must keep using the
# 10-digit `_clean_number()` form.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_place_call_sends_caller_id_in_full_e164(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """caller_id = 918069879757 (full E.164), customer_number = 10 digits."""
    httpx = pytest.importorskip("httpx")
    from app.telephony.tata_smartflo_handler import TataSmartfloClient

    _set(monkeypatch,
         TATA_SMARTFLO_API_TOKEN="tok_test",
         TATA_SMARTFLO_API_KEY="key_test",
         TATA_SMARTFLO_DID=_TATA_DID)

    captured: dict[str, Any] = {}

    class _FakeResponse:
        """Minimal stand-in for httpx.Response (no network)."""

        status_code = 200
        text = ('{"success": true, "message": "Originate successfully queued", '
                '"ref_id": "ref_test"}')

        def json(self) -> dict[str, Any]:
            return {
                "success": True,
                "message": "Originate successfully queued",
                "ref_id": "ref_test",
            }

    async def _fake_post(self: Any, url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["payload"] = dict(kwargs.get("json") or {})
        return _FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    client = TataSmartfloClient()
    result = await client.place_call(to="919876543210")

    payload = captured.get("payload")
    assert payload, "place_call() never posted a payload (client not configured?)"
    assert int(result.get("status_code") or 0) == 200, result

    # --- the actual regression: caller_id keeps its country code ------------
    assert payload["caller_id"] == _TATA_DID, (
        f"caller_id must be full E.164 {_TATA_DID!r}, got {payload['caller_id']!r} "
        "(10-digit form is rejected by SmartFlo with HTTP 422)"
    )
    assert payload["caller_id"] != "8069879757", (
        "caller_id lost its country code -> SmartFlo 422 'Provide a vaild caller_id.'"
    )

    # --- customer_number must still be the 10-digit form --------------------
    assert payload["customer_number"] == "9876543210", (
        f"customer_number must stay 10-digit, got {payload['customer_number']!r}"
    )
