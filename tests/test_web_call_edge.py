"""Web-call EdgeTTS + auto-learn helpers."""

from __future__ import annotations

import os

from app.api import web_call as wc


def test_web_call_edge_default_on():
    old = os.environ.pop("WEB_CALL_EDGE_TTS", None)
    try:
        assert wc._web_call_edge_enabled() is True
        os.environ["WEB_CALL_EDGE_TTS"] = "0"
        assert wc._web_call_edge_enabled() is False
    finally:
        if old is None:
            os.environ.pop("WEB_CALL_EDGE_TTS", None)
        else:
            os.environ["WEB_CALL_EDGE_TTS"] = old


def test_split_sentences_short_fragment():
    parts = wc._split_sentences("Pehla. Chhota. Aur lamba jawab yahan hai?")
    assert len(parts) >= 2


# --------------------------------------------------------------------------- #
# 2026-07-17 — live-call quality parity: web (test/demo) path must match the
# phone agent — no "ji/sir" habit fillers spoken; Swara prosody consistent.
# 2026-08-23 owner tune: pace +28%→+32% ("abhi bhi slow"), pitch -8Hz (deeper),
# turn-end silence 650ms→500ms ("1 second to bolna hi nahi chahiye").
# --------------------------------------------------------------------------- #
def test_web_filler_lines_have_no_address_fillers():
    banned = ("ji", "sir", "madam", "haji", "haan ji", "achha ji")
    for line in wc._FILLER_LINES:
        low = line.lower().strip(" .")
        toks = low.replace(".", " ").split()
        assert "ji" not in toks, line
        assert not any(b in low for b in ("sir", "madam", "haji")), line


def test_swara_prosody_defaults_phone_and_web_match():
    # Real contract (R4): source literals pin karo, env-read tautology nahi.
    # Web path default = phone path default — dono +32% rate, -8Hz pitch.
    import inspect

    import app.telephony.vobiz_stream as vs

    web_src = inspect.getsource(wc)
    phone_src = inspect.getsource(vs)
    assert '"WEB_TTS_RATE", "+32%"' in web_src
    assert '"WEB_TTS_PITCH", "-8Hz"' in web_src
    assert 'or "+32%"' in phone_src  # VOBIZ_TTS_RATE/PHONE_TTS_RATE fallback
    assert 'or "-8Hz"' in phone_src  # VOBIZ_TTS_PITCH/PHONE_TTS_PITCH fallback


def test_swara_turn_end_silence_default_snappy():
    # Owner directive 2026-08-23: turn-end silence 500 ms default on vobiz
    # (shared TURN_SILENCE_MS env ab bhi win karta hai).
    import inspect

    import app.telephony.vobiz_stream as vs

    src = inspect.getsource(vs)
    assert "_shared_silence_ms(500.0)" in src
    # purana 650 ms literal sirf history-comment me ho sakta hai, code me nahi:
    assert "_shared_silence_ms(650.0)" not in src


def test_web_never_hang_fallback_source_has_no_ji_sir():
    # The hardcoded "never hang" reply is sent WITHOUT _clean(), so its source
    # literal must not carry the banned habit-address filler.
    import inspect

    src = inspect.getsource(wc.web_call_ws)
    assert "Ji sir, sun rahi" not in src
    assert "Sun rahi hoon — thoda detail me bataye?" in src
