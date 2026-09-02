"""Tests for the close-the-loop learned-replies store (voice smart-fix Component 3)."""

import importlib

import pytest


@pytest.fixture()
def vl(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_LEARNED_INJECT", "1")
    import app.voice_agent.voice_learned as m

    importlib.reload(m)
    monkeypatch.setattr(m, "_STORE", str(tmp_path / "voice_learned.jsonl"))
    return m


def test_record_and_examples_roundtrip(vl):
    assert vl.record("ai_marketing", "kitna time lagega", "Bas 5 minute me setup, sir.")
    ex = vl.examples_for("ai_marketing")
    assert len(ex) == 1 and ex[0]["good"].startswith("Bas 5 minute")


def test_hint_for_formats_examples(vl):
    vl.record("real_estate", "budget kya hona chahiye", "Aapke area me 40 lakh se shuru, sir.")
    hint = vl.hint_for("real_estate")
    assert "accha jawab" in hint and "40 lakh" in hint


def test_niche_isolation(vl):
    vl.record("ai_marketing", "u1", "g1")
    vl.record("real_estate", "u2", "g2")
    assert vl.examples_for("ai_marketing") and "g2" not in vl.hint_for("ai_marketing")


def test_bounded_per_niche(vl):
    for i in range(12):
        vl.record("ai_marketing", f"u{i}", f"good reply {i}")
    # only the most recent _MAX_PER_NICHE kept
    assert len(vl.examples_for("ai_marketing", n=50)) <= vl._MAX_PER_NICHE


def test_empty_good_rejected(vl):
    assert vl.record("ai_marketing", "u", "   ") is False
    assert vl.examples_for("ai_marketing") == []


def test_kill_switch(tmp_path, monkeypatch):
    monkeypatch.setenv("VOICE_LEARNED_INJECT", "0")
    import app.voice_agent.voice_learned as m

    importlib.reload(m)
    monkeypatch.setattr(m, "_STORE", str(tmp_path / "vl.jsonl"))
    m.record("ai_marketing", "u", "g")  # record still works (write path)
    assert m.examples_for("ai_marketing") == []  # but injection disabled => no examples
    assert m.hint_for("ai_marketing") == ""
