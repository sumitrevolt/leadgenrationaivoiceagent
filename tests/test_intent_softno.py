"""
Tests for app.voice_agent.intent_softno — D-8 polite-no 2-strike de-escalation.
Pure policy; no LLM/network.
"""

from app.voice_agent import intent_softno as sn


def test_enabled_default_on(monkeypatch):
    monkeypatch.delenv("SOFTNO_DEESCALATE", raising=False)
    assert sn.enabled() is True
    monkeypatch.setenv("SOFTNO_DEESCALATE", "0")
    assert sn.enabled() is False


def test_soft_no_count_history_without_current():
    # current_text NOT yet in history -> counted on top
    hist = [
        {"role": "assistant", "content": "demo dikhau?"},
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye"},
    ]
    assert sn.soft_no_count(hist, "dekhte hain baad me") == 2


def test_soft_no_count_history_with_current_already_appended():
    # vobiz appends the user turn BEFORE calling -> current is the last user turn
    hist = [
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye"},
        {"role": "user", "content": "dekhte hain baad me"},
    ]
    # must NOT double-count the current turn
    assert sn.soft_no_count(hist, "dekhte hain baad me") == 2


def test_should_deescalate_first_vs_second(monkeypatch):
    monkeypatch.setenv("SOFTNO_DEESCALATE", "1")
    # 1st soft-no -> allow one re-ask (no de-escalation)
    hist1 = [{"role": "user", "content": "abhi nahi"}]
    assert sn.should_deescalate(hist1, "abhi nahi") is False
    # 2nd soft-no -> de-escalate
    hist2 = [
        {"role": "user", "content": "abhi nahi"},
        {"role": "assistant", "content": "ek baar dekh lijiye"},
        {"role": "user", "content": "dekhte hain baad me"},
    ]
    assert sn.should_deescalate(hist2, "dekhte hain baad me") is True


def test_should_not_deescalate_on_interest():
    hist = [
        {"role": "user", "content": "abhi nahi"},
        {"role": "user", "content": "haan demo dikhao"},
    ]
    # current turn is interest, not a refusal -> never de-escalate
    assert sn.should_deescalate(hist, "haan demo dikhao") is False


def test_disabled_never_deescalates(monkeypatch):
    monkeypatch.setenv("SOFTNO_DEESCALATE", "0")
    hist = [
        {"role": "user", "content": "abhi nahi"},
        {"role": "user", "content": "dekhte hain"},
    ]
    assert sn.should_deescalate(hist, "dekhte hain") is False


def test_deescalation_reply_deterministic_and_nonempty():
    a = sn.deescalation_reply("solar", "Acme")
    b = sn.deescalation_reply("solar", "Acme")
    assert a == b  # deterministic (no RNG)
    assert a and len(a.split()) > 5
    assert a in sn.DEESCALATION_TEMPLATES


def test_all_deescalation_replies_fit_spoken_word_budget():
    assert all(len(line.split()) <= 22 for line in sn.DEESCALATION_TEMPLATES)


def test_second_refusal_closers_do_not_offer_another_channel_or_pitch():
    """Two polite refusals mean a clean stop, not a WhatsApp/website CTA."""
    forbidden = ("whatsapp", "website", "leadsgenai", "demo", "detail", "jaankari")
    for line in sn.DEESCALATION_TEMPLATES:
        lowered = line.lower()
        assert not any(marker in lowered for marker in forbidden)


def test_never_raises_on_garbage():
    assert sn.should_deescalate(None, "") is False  # type: ignore[arg-type]
    assert sn.soft_no_count(None, None) == 0  # type: ignore[arg-type]
