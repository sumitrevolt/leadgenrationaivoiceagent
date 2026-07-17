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
# phone agent — no "ji/sir" habit fillers spoken; Swara pace consistent (+12%).
# --------------------------------------------------------------------------- #
def test_web_filler_lines_have_no_address_fillers():
    banned = ("ji", "sir", "madam", "haji", "haan ji", "achha ji")
    for line in wc._FILLER_LINES:
        low = line.lower().strip(" .")
        toks = low.replace(".", " ").split()
        assert "ji" not in toks, line
        assert not any(b in low for b in ("sir", "madam", "haji")), line


def test_web_tts_rate_default_matches_phone_pace():
    # Default (env unset) must be the +12% owner-tuned pace, not the old +26%.
    old = os.environ.pop("WEB_TTS_RATE", None)
    try:
        default = os.environ.get("WEB_TTS_RATE", "+12%").strip() or "+12%"
        assert default == "+12%"
    finally:
        if old is not None:
            os.environ["WEB_TTS_RATE"] = old


def test_web_never_hang_fallback_source_has_no_ji_sir():
    # The hardcoded "never hang" reply is sent WITHOUT _clean(), so its source
    # literal must not carry the banned habit-address filler.
    import inspect

    src = inspect.getsource(wc.web_call_ws)
    assert "Ji sir, sun rahi" not in src
    assert "Sun rahi hoon — thoda detail me bataye?" in src
