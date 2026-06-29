"""Tests for post-STT Hinglish correction (voice smart-fix Component 1b)."""

import importlib
import os

import pytest


@pytest.fixture()
def mod(monkeypatch):
    monkeypatch.setenv("STT_CORRECT", "1")
    import app.voice_agent.hinglish_stt_fix as m

    importlib.reload(m)
    return m


def test_brand_mishears_fixed(mod):
    out = mod.correct_stt("ek free instagiram aur vatsapp pe setup karo")
    assert "Instagram" in out and "WhatsApp" in out
    assert "instagiram" not in out.lower() and "vatsapp" not in out.lower()


def test_clean_text_unchanged(mod):
    # real words / a correctly-heard sentence must NOT be rewritten
    clean = "mujhe trial chahiye, marketing ke liye Google par aana hai"
    assert mod.correct_stt(clean) == clean


def test_word_boundary_only(mod):
    # "gugal" inside another token must not be touched (word-boundary)
    assert mod.correct_stt("xgugalx") == "xgugalx"


def test_phone_digit_words_collapsed_roman(mod):
    out = mod.correct_stt("mera number five nine zero one two six zero seven hai")
    assert "59012607" in out and "five" not in out


def test_phone_digit_words_collapsed_devanagari(mod):
    out = mod.correct_stt("फाइव नाइन जीरो वन टू सिक्स जीरो सेवन")
    assert "59012607" in out


def test_short_digit_run_not_collapsed(mod):
    # a stray "two" / short run must NOT become a digit
    out = mod.correct_stt("haan two minute me baat karte hain")
    assert "2" not in out and "two" in out


def test_digit_collapse_and_mishear_together(mod):
    out = mod.correct_stt("instagiram pe daalo number eight four five nine zero one two six")
    assert "Instagram" in out and "84590126" in out


def test_empty_and_none(mod):
    assert mod.correct_stt("") == ""
    assert mod.correct_stt("   ").strip() == ""


def test_kill_switch(monkeypatch):
    monkeypatch.setenv("STT_CORRECT", "0")
    import app.voice_agent.hinglish_stt_fix as m

    importlib.reload(m)
    assert m.correct_stt("instagiram") == "instagiram"  # disabled => unchanged


def test_facebook_google_variants(mod):
    out = mod.correct_stt("fesbook aur gugal pe ads")
    assert "Facebook" in out and "Google" in out


def test_stt_keyterms_has_vocab(monkeypatch):
    monkeypatch.setenv("STT_BIAS", "1")
    from app.voice_agent.niche_scripts import stt_keyterms

    bias = stt_keyterms("ai_marketing", "LeadGen AI")
    assert "Instagram" in bias and "WhatsApp" in bias and "trial" in bias
