"""Platform pitch flow (ai_marketing outbound) — unit tests."""

from __future__ import annotations

from app.voice_agent.niche_scripts import get_script
from app.voice_agent.platform_pitch import (
    PlatformPitchState,
    classify_interest,
    initial_state,
    is_platform_pitch,
    line_no_convince,
    line_yes_praise,
    next_reply,
    opening_segments,
)


def test_is_platform_pitch_only_ai_marketing():
    assert is_platform_pitch("ai_marketing") is True
    assert is_platform_pitch("solar_residential") is False
    assert is_platform_pitch("") is False


def test_opening_segments_short_opener_then_wait():
    """Opener is ONE short breath; price/pitch waits for caller yes (10–15 turns)."""
    segs = opening_segments()
    assert len(segs) == 1
    assert "LeadGen AI" in segs[0]
    assert len(segs[0].split()) <= 48
    # Permission ask stays in the opener
    assert any(w in segs[0].lower() for w in ("minute", "baat", "sakti", "hoon"))
    # Price must NOT be dumped in the opener monologue
    assert "1,999" not in segs[0] and "1999" not in segs[0]


def test_yes_praise_carries_price_after_permission():
    reply = line_yes_praise()
    assert "1,999" in reply or "1999" in reply
    assert any(w in reply.lower() for w in ("marketing", "agency", "staff", "trial", "free"))


def test_classify_interest_yes_no_unclear():
    assert classify_interest("haan") == "yes"
    assert classify_interest("ji batao") == "yes"
    assert classify_interest("nahi interest nahi") == "no"
    assert classify_interest("abhi nahi") == "no"
    assert classify_interest("kya?") == "unclear"
    assert classify_interest("") == "unclear"


def test_next_reply_yes_to_discovery():
    st = initial_state()
    reply, st = next_reply(st, "haan ji")
    assert st.phase == "discovery"
    low = (reply or "").lower()
    assert "marketing" in low or "agency" in low or "staff" in low


def test_next_reply_no_then_convince_then_close():
    st = initial_state()
    reply1, st = next_reply(st, "nahi")
    assert st.convinced_once is True
    assert st.phase == "await_interest_2"
    assert "trial" in reply1.lower() or "FREE" in reply1

    reply2, st = next_reply(st, "nahi chahiye")
    assert st.phase == "closed"
    assert "shukriya" in reply2.lower()


def test_no_convince_offers_free_trial():
    reply = line_no_convince().lower()
    assert "result dekho" in reply
    assert "7 din ka free trial" in reply


def test_next_reply_discovery_falls_through():
    st = PlatformPitchState(phase="discovery")
    reply, st = next_reply(st, "agency use karte hain")
    assert reply is None
    assert st.phase == "discovery"


def test_ai_marketing_script_has_platform_keys():
    s = get_script("ai_marketing")
    for key in (
        "opening",
        "pitch_short",
        "interest_ask",
        "yes_praise",
        "no_convince_once",
        "close_cold",
    ):
        assert key in s
        assert s[key]
    assert "1,999" in s["pitch_short"]


def test_customer_qa_answers_price_before_discovery():
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    brain.confirm_interest()
    ans = brain._customer_qa_reply("kitna paisa lagega mahine me?")
    assert ans
    assert "1,999" in ans or "1999" in ans


def test_kaun_ho_returns_reply_not_none():
    st = initial_state()
    reply, st = next_reply(st, "aap kaun ho")
    assert reply
    assert st.phase == "discovery"
    assert "swara" in reply.lower() or "leadgen" in reply.lower()


def test_solar_opening_unchanged_not_leadgen_branded():
    s = get_script("solar_residential")
    assert "LeadGen AI" not in (s.get("opening") or "")
