"""Platform pitch flow (ai_marketing outbound) — unit tests."""

from __future__ import annotations

from app.voice_agent.niche_scripts import get_script
from app.voice_agent.platform_pitch import (
    PlatformPitchState,
    classify_interest,
    initial_state,
    is_platform_pitch,
    next_reply,
    opening_segments,
)


def test_is_platform_pitch_only_ai_marketing():
    assert is_platform_pitch("ai_marketing") is True
    assert is_platform_pitch("solar_residential") is False
    assert is_platform_pitch("") is False


def test_opening_segments_three_parts():
    segs = opening_segments()
    assert len(segs) == 3
    assert "Leads Generation AI" in segs[0]
    assert "grow karna" in segs[0]
    assert "1,999" in segs[1] or "1999" in segs[1]
    assert "interested" in segs[2].lower()


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
