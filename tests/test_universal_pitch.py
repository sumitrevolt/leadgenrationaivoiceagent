"""Universal voice agent intro pitch."""

from __future__ import annotations

from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO


def test_universal_intro_has_identity_and_cta():
    # LEAN opener (2026-06-27): intro = identity + ek hook only (chhota). Price/trial
    # ab PITCH_SHORT segment me — yahan intro me unhe assert NAHI karte (warna bloat
    # wapas aa jaayega). Intro chhota rehna chahiye.
    t = UNIVERSAL_AGENT_INTRO.lower()
    assert "leads generation ai" in t
    assert any(w in t for w in ("instagram", "facebook", "google", "customers"))
    assert len(UNIVERSAL_AGENT_INTRO.split()) <= 26  # opener must stay short


def test_pitch_short_carries_price_and_trial():
    from app.voice_agent.universal_pitch import PITCH_SHORT

    p = PITCH_SHORT.lower()
    assert "1,999" in PITCH_SHORT or "1999" in PITCH_SHORT
    assert "trial" in p


def test_telecaller_platform_niche_opener_is_universal():
    # ai_marketing IS the platform-selling call → universal platform pitch.
    # Parity with vobiz_stream._opening_line_raw(): returns opening_segments()[0]
    # (the universal intro WITH the TRAI AI-disclosure prefix).
    from app.voice_agent.platform_pitch import opening_segments
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    opener = brain.opening_line()
    assert opener == opening_segments()[0]
    assert "leads generation ai" in opener.lower()


def test_telecaller_vertical_niche_opener_is_not_platform_pitch():
    # A vertical niche must open with its OWN researched script opening, never the
    # marketing platform pitch (the "agent noob baat kar rahi" web-call bug).
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(niche="real_estate", client_name="Sharma Realty")
    opener = brain.opening_line()
    assert opener != UNIVERSAL_AGENT_INTRO
    assert "instagram" not in opener.lower()
    assert "sharma realty" in opener.lower()  # client placeholder filled


def test_platform_opening_segments_wired():
    from app.voice_agent.universal_pitch import platform_opening_segments

    segs = platform_opening_segments()
    assert len(segs) == 3
    assert segs[0] == UNIVERSAL_AGENT_INTRO
    assert "1,999" in segs[1]
    assert "social" in segs[1].lower() or "posts" in segs[1].lower()
    assert "interested" in segs[2].lower()
