"""Unit tests for the free-stack deterministic eval metrics (no network)."""

from __future__ import annotations

from app.agents import eval_metrics as em


def _bot(c):
    return {"role": "assistant", "content": c}


def test_clean_conversation_scores_perfect():
    msgs = [
        _bot("Main LeadGen AI se ek AI assistant hoon. 2 minute hain?"),
        {"role": "user", "content": "haan"},
        _bot("Free Google audit kar sakte hain. Interested?"),
    ]
    r = em.voice_turn_score(msgs)
    assert r["score"] == 1.0
    assert r["bot_turns"] == 2
    assert sum(r["flags"].values()) == 0


def test_double_question_flagged():
    r = em.voice_turn_score([_bot("Aap kaun hain? Kya chahiye? Batayein?")])
    assert r["flags"]["double_question"] == 1
    assert r["score"] < 1.0


def test_empty_and_echo_flagged():
    r = em.voice_turn_score([_bot("   "), _bot("[echo of caller]")])
    assert r["flags"]["empty"] == 2
    assert r["score"] == 0.0  # both bot turns empty


def test_consecutive_repeat_flagged():
    r = em.voice_turn_score([_bot("Theek hai ji."), _bot("Theek hai ji.")])
    assert r["flags"]["repeat"] == 1


def test_too_long_flagged():
    r = em.voice_turn_score([_bot("Pehla. Doosra. Teesra. Chautha.")])
    assert r["flags"]["too_long"] == 1


def test_empty_conversation_is_neutral():
    r = em.voice_turn_score([])
    assert r["score"] == 1.0
    assert r["bot_turns"] == 0


def test_grounding_full_overlap():
    ctx = "LeadGen AI offers free Google Business audit and marketing automation."
    ans = "free Google audit marketing"
    assert em.grounding_score(ans, ctx) >= 0.9


def test_grounding_none_and_empty():
    assert em.grounding_score("quantum blockchain spaceship", "local bakery in Pune") < 0.2
    assert em.grounding_score("", "anything") == 0.0
    assert em.grounding_score("anything here", "") == 0.0


def test_transcript_quality_scalar_matches_score():
    msgs = [_bot("Ek line. Interested?")]
    assert em.transcript_quality(msgs) == em.voice_turn_score(msgs)["score"]
