"""Zero-dep text/semantic endpoint (turn-taking) — no model, no network.

Covers the tuned _INCOMPLETE_TAIL_WORDS (Hinglish + code-mixed English) so a
caller who pauses mid-thought ("...because", "...kyunki", "...warna") is NOT
cut off, while a clean sentence-final transcript ends the turn promptly.
"""

from __future__ import annotations

import pytest

from app.voice_agent.turn_detector import text_end_of_turn


@pytest.mark.parametrize(
    "text",
    [
        "haan ji bilkul.",
        "mujhe interested hai?",
        "theek hai!",
        "namaste ji।",
    ],
)
def test_complete_on_terminal_punct(text):
    assert text_end_of_turn(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "mujhe lagta hai ki yeh sahi hai because",  # English dangling
        "haan but",
        "karna to hai and",
        "le lunga warna",  # new Hinglish
        "woh banda jiska",
        "mujhe chahiye kyunki",  # existing Hinglish
        "dekhiye matlab",  # filler
        "thoda ruko,",  # trailing comma
        "haan -",  # trailing dash
    ],
)
def test_incomplete_keeps_listening(text):
    assert text_end_of_turn(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "mujhe ek website chahiye",  # plain words, no punct -> let audio decide
        "",
        "   ",
    ],
)
def test_undecided_returns_none(text):
    assert text_end_of_turn(text) is None


def test_english_connectives_are_case_insensitive():
    assert text_end_of_turn("I will do it BUT") is False
    assert text_end_of_turn("yeh karunga SO") is False
