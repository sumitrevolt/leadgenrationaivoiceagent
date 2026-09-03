"""
Regression and contract tests for Swara Enterprise Voice Agent Upgrade:
1. Dual-Product Pitch (AI Marketing + AI Voice Calling Agent).
2. Elimination of 'ek second' from all filler banks and prompt responses.
3. Telecaller Brain enterprise Q&A for Voice Calling and Marketing products.
"""

from __future__ import annotations

import pytest
from app.voice_agent.fillers import FILLERS, pick_filler, FillerPlayer
from app.voice_agent.universal_pitch import (
    UNIVERSAL_AGENT_INTRO,
    PITCH_SHORT,
    VOICE_AGENT_INTRO,
    VOICE_AGENT_PITCH_SHORT,
)
from app.voice_agent.telecaller_brain import TelecallerBrain
from app.voice_agent.platform_pitch import is_product_question


def test_no_ek_second_in_fillers():
    for lang, categories in FILLERS.items():
        for cat, phrases in categories.items():
            for phrase in phrases:
                assert "ek second" not in phrase.lower(), f"Found 'ek second' in {lang}:{cat} -> {phrase}"


def test_filler_player_never_returns_ek_second():
    fp = FillerPlayer(lang="hinglish")
    for _ in range(50):
        filler = fp.next("thinking")
        assert "ek second" not in filler.lower()


def test_universal_pitches_defined():
    assert "Instagram" in UNIVERSAL_AGENT_INTRO or "Facebook" in UNIVERSAL_AGENT_INTRO
    assert "₹1,999" in PITCH_SHORT
    assert "AI telecaller" in VOICE_AGENT_INTRO
    assert "₹4,999" in VOICE_AGENT_PITCH_SHORT or "unlimited calls" in VOICE_AGENT_PITCH_SHORT


def test_telecaller_brain_voice_product_qa():
    brain = TelecallerBrain(niche="ai_voice_agent")
    
    # Price ask for voice calling
    res_price = brain._customer_qa_reply("AI voice agent calling ka kitna charge hai?")
    assert "₹4,999" in res_price
    assert "ek second" not in res_price.lower()
    
    # Feature ask for voice calling
    res_feat = brain._customer_qa_reply("Aapka voice telecaller kya karta hai?")
    assert "AI Voice Telecaller" in res_feat or "60s" in res_feat or "calls" in res_feat
    assert "ek second" not in res_feat.lower()


def test_telecaller_brain_marketing_product_qa():
    brain = TelecallerBrain(niche="ai_marketing")
    
    # General price ask
    res_price = brain._customer_qa_reply("Aapka monthly pricing kitna hai?")
    assert "₹1,999" in res_price or "₹4,999" in res_price
    assert "ek second" not in res_price.lower()

    # Feature ask
    res_feat = brain._customer_qa_reply("Aap kya kya service provide karte ho?")
    assert "AI Marketing" in res_feat or "AI Voice Telecaller" in res_feat
    assert "ek second" not in res_feat.lower()


def test_is_product_question_handles_voice_and_marketing():
    assert is_product_question("Aapka telecaller kitne ka hai?")
    assert is_product_question("Calling service kaise kaam karti hai?")
    assert is_product_question("Kya kya features dete ho?")
    assert is_product_question("Price kya hai?")
