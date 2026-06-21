"""Universal voice agent intro pitch."""

from __future__ import annotations

from app.voice_agent.universal_pitch import UNIVERSAL_AGENT_INTRO


def test_universal_intro_has_identity_and_cta():
    t = UNIVERSAL_AGENT_INTRO.lower()
    assert "leads generation ai" in t
    assert "grow karna" in t
    assert "trial" in t
    assert "best solution" in t


def test_telecaller_default_opener_is_universal():
    from app.voice_agent.telecaller_brain import TelecallerBrain

    brain = TelecallerBrain(niche="ai_marketing", client_name="LeadGen AI")
    assert brain.opening_line() == UNIVERSAL_AGENT_INTRO


def test_platform_opening_segments_wired():
    from app.voice_agent.universal_pitch import platform_opening_segments

    segs = platform_opening_segments()
    assert len(segs) == 3
    assert segs[0] == UNIVERSAL_AGENT_INTRO
    assert "1,199" in segs[1]
    assert "social" in segs[1].lower() or "posts" in segs[1].lower()
    assert "interested" in segs[2].lower()
