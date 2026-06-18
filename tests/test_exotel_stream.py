"""DEPRECATED — Exotel Voicebot stream removed 2026-06-18 (provider is now Vobiz).

This whole module is skipped: ``ExotelVoicebotSession`` no longer exists. The live
conversational voice WS path is now the Vobiz stream (app.telephony.vobiz_stream).
"""

from __future__ import annotations

import pytest

pytest.skip(
    "Exotel removed 2026-06-18 — provider is now Vobiz (see app.telephony.vobiz_stream).",
    allow_module_level=True,
)


class FakeWS:
    query_params: dict = {}


def test_chunk_bytes_spec():
    # >=3.2KB aur 320 ka multiple — har supported rate par
    assert _chunk_bytes(8000) == 3200
    assert _chunk_bytes(16000) == 3200
    assert _chunk_bytes(24000) == 4800
    for sr in SUPPORTED_RATES:
        assert _chunk_bytes(sr) % 320 == 0 and _chunk_bytes(sr) >= 3200


def test_sample_rate_validation():
    assert ExotelVoicebotSession(FakeWS(), sample_rate=16000).sample_rate == 16000
    assert ExotelVoicebotSession(FakeWS(), sample_rate=11025).sample_rate == 8000  # default


def test_start_event_media_format_and_params():
    async def go():
        s = ExotelVoicebotSession(FakeWS())
        s._spawn = lambda c: (c.close(), None)[1]  # greeting task no-op
        await s._handle_start(
            {
                "event": "start",
                "stream_sid": "st1",
                "start": {
                    "stream_sid": "st1",
                    "call_sid": "c1",
                    "media_format": {"encoding": "raw", "sample_rate": "16000"},
                    "custom_parameters": {"niche": "solar"},
                },
            }
        )
        assert s.sample_rate == 16000
        assert s.stream_sid == "st1" and s.call_sid == "c1" and s.niche == "solar"

    asyncio.run(go())


def test_inbound_media_resample_and_alignment():
    s = ExotelVoicebotSession(FakeWS(), sample_rate=16000)
    pcm16k = b"\x00\x01" * 1600  # 100ms @ 16k PCM16
    asyncio.run(
        s._handle_media(
            {"event": "media", "media": {"payload": base64.b64encode(pcm16k).decode()}}
        )
    )
    assert len(s._inbound_rem) < 320  # 320B frame alignment maintained


def test_outbound_chunking_and_clear(monkeypatch):
    async def go():
        s = ExotelVoicebotSession(FakeWS(), sample_rate=16000)
        s.stream_sid = "st1"
        sent: list[dict] = []

        async def cap(obj):
            sent.append(obj)

        s._send_json = cap

        async def nosleep(_):
            return None

        monkeypatch.setattr(asyncio, "sleep", nosleep)
        await s._send_audio(b"\x01\x02" * 5000)  # 10000B (not 320-aligned)
        assert sent
        for m in sent:
            assert m["event"] == "media" and m["stream_sid"] == "st1"
            raw = base64.b64decode(m["media"]["payload"])
            assert len(raw) % 320 == 0
        total = sum(len(base64.b64decode(m["media"]["payload"])) for m in sent)
        assert total >= 10000 and total % 320 == 0  # zero-padded to boundary
        await s._send_clear()
        assert sent[-1] == {"event": "clear", "stream_sid": "st1"}

    asyncio.run(go())


def test_greeting_has_ai_disclosure(monkeypatch):
    # TRAI: LLM unavailable par bhi greeting me AI disclosure ho
    import app.voice_agent.phone_stream as ps

    monkeypatch.setattr(ps, "_get_brain", lambda: None)

    async def go():
        s = ExotelVoicebotSession(FakeWS())
        txt = await s._greeting_text()
        assert "ai" in txt.lower()

    asyncio.run(go())


def test_parent_vad_refactor_regression():
    # phone_stream._vad_on_frame extract ke baad Vobiz u-law path unchanged
    import audioop

    p = PhoneCallSession(FakeWS())
    assert callable(p._vad_on_frame)
    ulaw = audioop.lin2ulaw(b"\x00\x01" * 160, 2)
    asyncio.run(
        p._handle_media({"event": "media", "media": {"payload": base64.b64encode(ulaw).decode()}})
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
