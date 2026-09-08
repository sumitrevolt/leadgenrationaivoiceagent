"""Deferred backlog helpers — deliverability summary + LLM stream sentence split."""

from __future__ import annotations

import pytest

from app.platform import eval_hub
from app.voice_agent.llm_stream_tts import pop_sentence, stream_tts_enabled


@pytest.mark.asyncio
async def test_record_positive_eval_flag_off(monkeypatch):
    """EVAL_KB_BOOST=0 → always False, no KB write."""
    monkeypatch.setenv("EVAL_KB_BOOST", "0")
    result = await eval_hub.record_positive_eval("kya rate hai?", "₹2999/mo", "niche:real_estate")
    assert result is False


@pytest.mark.asyncio
async def test_record_positive_eval_empty_inputs(monkeypatch):
    """Empty query/answer → False even if flag on."""
    monkeypatch.setenv("EVAL_KB_BOOST", "1")
    assert await eval_hub.record_positive_eval("", "some answer") is False
    assert await eval_hub.record_positive_eval("query", "") is False


def test_pop_sentence_splits():
    s, rest = pop_sentence("Namaste sir. Aapka budget kya hai?")
    assert s == "Namaste sir."
    assert "budget" in rest


def test_stream_tts_flag_off_by_default(monkeypatch):
    monkeypatch.delenv("USE_LLM_STREAM_TTS", raising=False)
    assert stream_tts_enabled() is False


@pytest.mark.asyncio
async def test_deliverability_summary_shape(monkeypatch):
    import app.platform.deliverability_monitor as dm
    import app.platform.email_warmup as ew

    async def _dns():
        return {
            "spf_ok": True,
            "dkim_ok": True,
            "dmarc_ok": True,
            "dmarc_policy": "none",
            "problems": [],
        }

    monkeypatch.setattr(dm, "run_check", _dns)
    monkeypatch.setattr(
        ew,
        "status",
        lambda: {
            "effective_cap": 25,
            "sent_7d": 10,
            "complaint_rate_7d_pct": 0.0,
            "complaint_pause_threshold_pct": 0.25,
            "paused": False,
        },
    )
    out = await eval_hub.deliverability_summary()
    assert out["ok"] is True
    assert "dns" in out and "warmup" in out


def test_rag_ab_compute_deltas_import():
    from scripts.rag_retrieval_ab import LABELED_SET, compute_deltas

    def fake(q, k):
        if "bill" in q:
            return [{"text": "solar_bill doc"}]
        return []

    report = compute_deltas(
        {"baseline": fake, "full": fake},
        labeled_set=LABELED_SET[:1],
        margin=0.0,
    )
    assert "baseline" in report
