"""Platform-pitch dodge fix (2026-06-28): direct product questions after the
'interested hain?' opener must route to TelecallerBrain (None) so they get ANSWERED
— not mis-classified as 'yes' (via the batao/bolo YES patterns) and dodged with a
discovery question. From the user's real call: "features batao" → "marketing khud
karte ho?" (dodge).
"""

from __future__ import annotations

from app.voice_agent.platform_pitch import (
    PlatformPitchState,
    is_product_question,
    line_yes_praise,
    next_reply,
)


def _gate():
    return PlatformPitchState(phase="await_interest")


def test_product_questions_route_to_brain_not_dodge():
    praise = line_yes_praise()
    for q in (
        "kya kya features hain?",
        "Total kitne features provide karte ho aap?",
        "features batao",  # the 'batao' YES-pattern misfire
        "kya kya features hai pahle vah batao?",
        "price kitna hai",
        "kaise kaam karta hai ye",
        "क्या क्या फीचर हैं",  # Devanagari (Whisper hi)
    ):
        reply, st = next_reply(_gate(), q)
        assert reply is None, f"{q!r} should hand to brain (None), got {reply!r}"
        assert st.phase == "discovery", f"{q!r} should move to discovery, got {st.phase}"
        assert reply != praise


def test_pure_interest_still_classified_yes():
    # "haan batao" (no product word) = genuine interest → praise + discovery, NOT
    # treated as a product question.
    assert is_product_question("haan batao") is False
    reply, st = next_reply(_gate(), "haan batao sunao")
    assert reply is not None and st.phase == "discovery"


def test_bare_yes_and_no_unaffected():
    r1, s1 = next_reply(_gate(), "haan")
    assert s1.phase in ("discovery", "await_interest")  # yes/clarify path, not product-Q
    r2, s2 = next_reply(_gate(), "nahi interest nahi")
    assert s2.phase in ("await_interest_2", "closed")  # no-path


def test_is_product_question_negatives():
    assert is_product_question("haan ji") is False
    assert is_product_question("busy hoon abhi") is False
    assert is_product_question("") is False
