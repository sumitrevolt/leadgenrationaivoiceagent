"""SPAM CONTENT GUARD tests (2026-07-15) — betting/gambling reply spam.

Context: 07-14 production audit — reply agent classified "Reddy Anna" gambling
spam as `interested` with a draft ready in Hot Queue. Guard drops such content
BEFORE LLM classify (email + WhatsApp paths) and hides already-saved spam rows
on the read path (`_is_noise_row`).

Offline pure-function tests — no IMAP/LLM/network.
"""

from __future__ import annotations

import pytest

from app.platform.reply_agent import _is_noise_row, _is_spam_content


SPAM_SAMPLES = [
    ("Reddy Anna Book", "Get your cricket id now, instant withdrawal"),
    ("", "REDDYANNA online betting id available 24x7"),
    ("Betting ID offer", "best betting exchange rates"),
    ("Play now", "casino jackpot deposit bonus"),
    ("", "satta matka fix number aaj ka"),
    ("Teen Patti real cash", ""),
    ("", "IPL id lo, aviator game me jeeto"),
    ("Lottery win", "your lottery ticket number confirmed"),
]

LEGIT_SAMPLES = [
    ("Re: AI Marketing for Jiya Makeover", "haan interested hoon, pricing bhejo"),
    ("Bridal package inquiry", "Sunday ka slot available hai kya?"),
    ("Re: solar quote", "roof size 800 sqft hai, subsidy milegi?"),
    ("Demo request", "kal 4 baje call kar sakte ho?"),
    # near-miss vocab that must NOT trip the guard
    ("Booking confirmed", "aapki booking id BK-1023 hai"),  # "booking id" != "betting id"
    ("Re: coaching admission", "NEET batch me seat book karni hai"),
]


@pytest.mark.parametrize("subj,body", SPAM_SAMPLES)
def test_spam_content_detected(subj, body, monkeypatch):
    monkeypatch.delenv("REPLY_SPAM_CONTENT_GUARD", raising=False)
    assert _is_spam_content(subj, body) is True


@pytest.mark.parametrize("subj,body", LEGIT_SAMPLES)
def test_legit_replies_pass(subj, body, monkeypatch):
    monkeypatch.delenv("REPLY_SPAM_CONTENT_GUARD", raising=False)
    monkeypatch.delenv("REPLY_SPAM_EXTRA_TERMS", raising=False)
    assert _is_spam_content(subj, body) is False


def test_guard_disable_flag(monkeypatch):
    monkeypatch.setenv("REPLY_SPAM_CONTENT_GUARD", "0")
    assert _is_spam_content("Reddy Anna Book", "betting id") is False


def test_operator_extra_terms(monkeypatch):
    monkeypatch.delenv("REPLY_SPAM_CONTENT_GUARD", raising=False)
    monkeypatch.setenv("REPLY_SPAM_EXTRA_TERMS", "crypto doubling, forex signals")
    assert _is_spam_content("", "guaranteed FOREX SIGNALS group join") is True
    assert _is_spam_content("", "normal business reply") is False


def test_noise_row_hides_saved_spam_draft(monkeypatch):
    monkeypatch.delenv("REPLY_SPAM_CONTENT_GUARD", raising=False)
    row = {
        "from": "918888777666",
        "subject": "Reddy Anna new id",
        "text": "cricket id whatsapp karo",
        "intent": "interested",
    }
    assert _is_noise_row(row) is True


def test_noise_row_keeps_legit_draft(monkeypatch):
    monkeypatch.delenv("REPLY_SPAM_CONTENT_GUARD", raising=False)
    monkeypatch.delenv("REPLY_SPAM_EXTRA_TERMS", raising=False)
    row = {
        "from": "prospect@salon.example",
        "subject": "Re: AI Marketing",
        "text": "pricing bhejo please",
        "intent": "interested",
    }
    assert _is_noise_row(row) is False


def test_never_raises_on_garbage():
    assert _is_spam_content(None, None) in (True, False)  # type: ignore[arg-type]
    assert _is_noise_row({}) in (True, False)
    assert _is_noise_row(None) in (True, False)  # type: ignore[arg-type]
