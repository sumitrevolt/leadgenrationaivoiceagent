"""Cross-path telephony lifecycle — Vobiz stream metering + qualified-lead idempotency."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.billing import lead_usage
from app.telephony.post_call_hooks import (
    apply_qualified_downstream,
    classify_stream_outcome,
    meter_call_completion,
)
from app.telephony.vobiz_stream import VobizStreamSession, FRAME_PCM


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_meter_call_completion_idempotent(monkeypatch):
    """Same call_id twice → record_call_usage runs once."""
    calls: list[tuple] = []

    def _fake_record(**kw):
        calls.append(kw)
        return True

    seen: set[str] = set()

    async def _fake_seen(key: str, ttl_s=None):
        if key in seen:
            return True
        seen.add(key)
        return False

    monkeypatch.setattr("app.billing.usage.record_call_usage", _fake_record)
    with patch("app.billing.idempotency.seen_before", side_effect=_fake_seen):
        assert _run(meter_call_completion("sid-1", client_id="c1", duration_seconds=90)) is True
        assert _run(meter_call_completion("sid-1", client_id="c1", duration_seconds=90)) is False
    assert len(calls) == 1
    assert calls[0]["duration_seconds"] == 90


def test_record_qualified_lead_ref_idempotent(tmp_path, monkeypatch):
    """Same ref twice → one ledger row."""
    store = tmp_path / "lead_usage.jsonl"
    monkeypatch.setattr(lead_usage, "_STORE", store)

    assert lead_usage.record_qualified_lead("client-x", ref="call-abc") is True
    assert lead_usage.record_qualified_lead("client-x", ref="call-abc") is True
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1


def test_vobiz_cleanup_meters_once(monkeypatch):
    """VobizStreamSession._cleanup invokes meter_call_completion exactly once."""
    meter = AsyncMock(return_value=True)
    monkeypatch.setattr("app.telephony.post_call_hooks.meter_call_completion", meter)

    sess = VobizStreamSession(MagicMock(), client_id="cid-1", client_name="Test Co")
    sess.stream_sid = "stream-99"
    monkeypatch.setattr(sess, "_auto_qualify", AsyncMock())
    monkeypatch.setattr(sess, "_save_recording", lambda: None)
    monkeypatch.setattr(sess, "_persist_transcript", lambda *a, **k: None)
    _run(sess._cleanup())
    _run(sess._cleanup())  # duplicate disconnect
    assert meter.await_count == 1


def test_apply_qualified_downstream_enrolls_when_flagged(monkeypatch):
    """Qualified verdict fans out to sales pipeline (cadence gated separately)."""
    enrolled: list[dict] = []
    monkeypatch.setattr(
        "app.marketing.sales_pipeline.upsert_deal",
        lambda data, stage="interested": enrolled.append({"data": data, "stage": stage}),
    )
    monkeypatch.setenv("CADENCE_ENGINE", "0")
    q = {"qualified": True, "interest_score": 80, "summary": "hot", "next_action": "call"}
    _run(
        apply_qualified_downstream(
            q,
            client_id="c1",
            phone="+919999999999",
            client_name="Acme",
            call_id="sid-1",
            niche="solar",
        )
    )
    assert len(enrolled) == 1
    assert enrolled[0]["stage"] == "interested"


def test_classify_stream_outcome_marks_zero_turn_call_as_no_answer():
    assert classify_stream_outcome(user_turns=0, turn_metrics=[]) == "no_answer"


def test_vobiz_cleanup_logs_no_answer_for_dead_call(monkeypatch):
    meter = AsyncMock(return_value=True)
    recorded: list[dict] = []
    emitted: list[tuple[str, dict]] = []
    monkeypatch.setattr("app.telephony.post_call_hooks.meter_call_completion", meter)
    monkeypatch.setattr(
        "app.platform.interaction_log.record",
        AsyncMock(side_effect=lambda **kw: recorded.append(kw) or {"ok": True}),
    )
    monkeypatch.setattr(
        "app.platform.outbound_webhooks.emit",
        AsyncMock(
            side_effect=lambda event, payload, client_id="": emitted.append((event, payload))
        ),
    )

    sess = VobizStreamSession(MagicMock(), client_id="cid-1", client_name="Test Co")
    sess.stream_sid = "stream-99"
    sess._turn_metrics = [{"outcome": "think_timeout"}]
    monkeypatch.setattr(sess, "_auto_qualify", AsyncMock())
    monkeypatch.setattr(sess, "_save_recording", lambda: None)
    monkeypatch.setattr(sess, "_persist_transcript", lambda *a, **k: None)
    _run(sess._cleanup())

    assert recorded and recorded[-1]["outcome"] == "no_answer"
    assert emitted and emitted[-1][1]["outcome"] == "no_answer"


def test_recording_master_clock_advances_on_bot(monkeypatch):
    """Regression (2026-08-24): the call-recording master clock must advance on BOT
    audio too. It only advanced on caller frames, so during Swara's reply it froze
    and the caller's NEXT utterance was written at a stale position, OVERWRITING the
    bot's audio -> mixed WAV garbled / missing Swara. Verify a later caller utterance
    lands AFTER the bot (bot audio preserved)."""
    import struct

    marker_a = struct.pack("<h", 1) * FRAME_PCM  # caller
    marker_bot = struct.pack("<h", 2)            # Swara
    marker_c = struct.pack("<h", 3) * FRAME_PCM  # caller (2nd)

    sess = VobizStreamSession(MagicMock(), client_id="c", client_name="T")
    sess._speaking = True
    sess._rec_enabled = True
    sess._rec_mixed = bytearray()
    sess._rec_timeline_samples = 0
    sess._rec_bot_playhead = None
    sess._send = AsyncMock()

    # caller's 1st utterance
    sess._rec_mix_caller(sess._rec_timeline_samples, marker_a)
    sess._rec_timeline_samples += len(marker_a) // 2
    caller_end = sess._rec_timeline_samples

    # Swara plays a multi-frame reply (the fix advances the master clock here)
    sess._rec_begin_bot_playback()
    bot_pcm = marker_bot * (FRAME_PCM * 5)
    _run(sess._play_frames(bot_pcm))
    assert sess._rec_timeline_samples > caller_end  # master clock advanced with the bot

    # caller's 2nd utterance must land AFTER the bot (no overwrite of Swara's audio)
    bot_end = sess._rec_timeline_samples
    sess._rec_mix_caller(sess._rec_timeline_samples, marker_c)
    # Swara's audio value at the bot's start is preserved (2), not overwritten to 3
    val_at_bot_start = struct.unpack_from("<h", bytes(sess._rec_mixed), caller_end * 2)[0]
    assert val_at_bot_start == 2
    # caller-2 value is present at bot_end
    val_at_bot_end = struct.unpack_from("<h", bytes(sess._rec_mixed), bot_end * 2)[0]
    assert val_at_bot_end == 3
