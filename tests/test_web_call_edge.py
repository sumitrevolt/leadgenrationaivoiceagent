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
