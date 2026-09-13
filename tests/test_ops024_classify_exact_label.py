"""OPS-024 — intent classification must match EXACTLY, not by substring.

Found in cycle 12 while narrowing the WhatsApp AI's scope (OPS-016): ``_classify``
returned the first ``_CATS`` entry *contained in* the LLM's label, and
``"not_interested"`` **contains** ``"interested"``. So every rejection was classified
``interested``.

Consequences of the bug (all real, all on the live path):
  1. Someone who said "not interested" was marked a HOT lead (Hot-Queue noise).
  2. They received a sales draft instead of being left alone.
  3. With ``WHATSAPP_AI_AUTOREPLY=1`` the AI auto-sent them a sales pitch — the
     fastest way to get a WhatsApp number reported and banned.

The fix matches the label exactly first (after normalising spaces/hyphens to
underscores) and only then falls back to a word-boundary search, so ``_CATS`` ordering
can never decide a verdict again.

Behavioural tests: they drive the real ``_classify`` with a stubbed LLM.
"""

import asyncio

import pytest

from app.platform import reply_agent as ra


def _classify_with(monkeypatch, label):
    """Run the real `_classify` with an LLM that returns `label`."""

    async def fake_chat(system, messages, max_tokens=8, temperature=0.0, **kw):
        return (label, "fake")

    from app.voice_agent import free_ai

    monkeypatch.setattr(free_ai, "chat", fake_chat)
    return asyncio.run(ra._classify("WhatsApp inbound", "koi bhi message"))


# --------------------------------------------------------------------------- #
# 1. The bug: a rejection must never be read as interest
# --------------------------------------------------------------------------- #
def test_not_interested_is_not_misread_as_interested(monkeypatch):
    """THE regression test. Pre-OPS-024 this returned 'interested'."""
    assert _classify_with(monkeypatch, "not_interested") == "not_interested"


@pytest.mark.parametrize("label", ["not interested", "Not-Interested", "not_interested."])
def test_not_interested_survives_llm_spelling_variants(monkeypatch, label):
    assert _classify_with(monkeypatch, label) == "not_interested"


# --------------------------------------------------------------------------- #
# 2. Every category must round-trip regardless of `_CATS` order
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("label", ra._CATS)
def test_every_category_round_trips_exactly(monkeypatch, label):
    assert _classify_with(monkeypatch, label) == label


def test_cat_ordering_can_never_decide_a_verdict(monkeypatch):
    """Reversing `_CATS` must not change any verdict."""
    original = list(ra._CATS)
    try:
        ra._CATS = list(reversed(original))
        for label in original:
            assert _classify_with(monkeypatch, label) == label
    finally:
        ra._CATS = original


# --------------------------------------------------------------------------- #
# 3. Fallbacks preserved: prose labels still resolve, junk still -> other
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "label,expected",
    [
        ("I am interested", "interested"),
        ("label: question", "question"),
        ("bahut mehenga hai — objection", "objection"),
        ("unsubscribe please", "unsubscribe"),
    ],
)
def test_prose_labels_still_resolve_via_word_boundary(monkeypatch, label, expected):
    assert _classify_with(monkeypatch, label) == expected


@pytest.mark.parametrize("label", ["", "   ", "banana", "12345"])
def test_unrecognised_labels_fall_back_to_other(monkeypatch, label):
    assert _classify_with(monkeypatch, label) == "other"
