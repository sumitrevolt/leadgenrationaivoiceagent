"""Contract tests for the typed KB grounding + refusal contract (A1).

Rule R4 discipline: har test apni PRECONDITION khud set karta hai. Jo test
refusal assert karta hai wo khud weak-retrieval banata hai (fake KB), ambient
Qdrant/env pe bharosa nahi karta — warna "green" ka matlab sirf "KB khaali tha"
ho sakta hai, jo false safety hai.

In tests ka asli kaam: prove karna ki "confident answer with zero evidence"
CONSTRUCT hi nahi ho sakta.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.voice_agent import kb_grounding
from app.voice_agent.kb_grounding import (
    REASON_BELOW_MIN_SCORE,
    REASON_EMPTY_QUERY,
    REASON_NO_HITS,
    REASON_NO_VERIFIED_CITATION,
    REASON_RETRIEVE_FAILED,
    Citation,
    GroundedAnswer,
    grounded_answer_typed,
)


class FakeKB:
    """Minimal `retrieve()`-compatible double. Test hi decide karta hai kya mila."""

    def __init__(self, hits, *, raises: Exception | None = None):
        self._hits = hits
        self._raises = raises
        self.calls: list[dict] = []

    def retrieve(self, query, k=3, namespace="default", rerank=None):
        self.calls.append({"query": query, "k": k, "namespace": namespace, "rerank": rerank})
        if self._raises is not None:
            raise self._raises
        return list(self._hits)


def _hit(text, score, source="niche:test"):
    return {"text": text, "score": score, "source": source}


STRONG = 0.91
WEAK = 0.001  # KB ka apna _MIN_GROUND_SCORE 0.04 hai — ye uske neeche hai


# --------------------------------------------------------------------------- #
# The invariant itself — ye do test poore module ka reason-for-existence hain.
# --------------------------------------------------------------------------- #


def test_answered_true_with_zero_citations_is_a_validation_error():
    with pytest.raises(ValidationError):
        GroundedAnswer(text="pricing 1999 hai", citations=[], confidence=0.9, answered=True)


def test_refusal_carrying_citations_is_a_validation_error():
    citation = Citation(source="niche:test", chunk_id="abc", quoted_span="pricing 1999", score=0.9)
    with pytest.raises(ValidationError):
        GroundedAnswer(
            text="nahi pata",
            citations=[citation],
            confidence=0.0,
            answered=False,
            reason=REASON_NO_HITS,
        )


def test_refusal_requires_a_reason_and_answer_forbids_one():
    with pytest.raises(ValidationError):
        GroundedAnswer(text="nahi pata", citations=[], confidence=0.0, answered=False)

    citation = Citation(source="niche:test", chunk_id="abc", quoted_span="pricing 1999", score=0.9)
    with pytest.raises(ValidationError):
        GroundedAnswer(
            text="pricing 1999 hai",
            citations=[citation],
            confidence=0.9,
            answered=True,
            reason=REASON_NO_HITS,
        )


def test_blank_citation_fields_are_rejected():
    with pytest.raises(ValidationError):
        Citation(source="  ", chunk_id="abc", quoted_span="x", score=0.5)
    with pytest.raises(ValidationError):
        Citation(source="niche:test", chunk_id="abc", quoted_span="   ", score=0.5)


# --------------------------------------------------------------------------- #
# Refusal paths — precondition har test khud banata hai.
# --------------------------------------------------------------------------- #


def test_weak_retrieval_refuses_with_zero_citations():
    kb = FakeKB([_hit("Pricing ₹1,999/mahina hai.", WEAK)])

    answer = grounded_answer_typed(kb, "pricing kya hai?", namespace="_global")

    assert answer.answered is False
    assert answer.citations == []
    assert answer.reason == REASON_BELOW_MIN_SCORE
    assert answer.top_score == pytest.approx(WEAK, abs=1e-4)


def test_no_hits_refuses():
    answer = grounded_answer_typed(FakeKB([]), "kuch bhi", namespace="_global")

    assert answer.answered is False
    assert answer.reason == REASON_NO_HITS
    assert answer.citations == []


def test_empty_query_refuses_without_touching_the_kb():
    kb = FakeKB([_hit("Pricing ₹1,999/mahina hai.", STRONG)])

    answer = grounded_answer_typed(kb, "   ", namespace="_global")

    assert answer.answered is False
    assert answer.reason == REASON_EMPTY_QUERY
    assert kb.calls == [], "blank query pe retrieval call hi nahi honi chahiye"


def test_retrieval_exception_becomes_a_refusal_not_a_crash():
    """Voice path pe exception = dead air. Refusal must be the worst case."""
    kb = FakeKB([], raises=RuntimeError("qdrant unreachable"))

    answer = grounded_answer_typed(kb, "pricing kya hai?", namespace="_global")

    assert answer.answered is False
    assert answer.reason == REASON_RETRIEVE_FAILED


def test_refusal_text_is_the_existing_safe_fallback_not_a_new_string():
    """Wiring ke baad customer ko wahi line sunni chahiye jo aaj sunta hai."""
    from app.voice_agent.knowledge_base import _SAFE_FALLBACK

    answer = grounded_answer_typed(FakeKB([]), "kuch bhi")

    assert answer.text == _SAFE_FALLBACK


# --------------------------------------------------------------------------- #
# Answer paths
# --------------------------------------------------------------------------- #


def test_strong_retrieval_answers_with_at_least_one_verbatim_citation():
    chunk = "Pricing: Main plan ₹1,999/mahina, Advanced/Combo ₹5,999/mahina."
    kb = FakeKB([_hit(chunk, STRONG, source="business_faq")])

    answer = grounded_answer_typed(kb, "pricing kya hai?", namespace="_global")

    assert answer.answered is True
    assert answer.reason is None
    assert len(answer.citations) >= 1
    citation = answer.citations[0]
    assert citation.source == "business_faq"
    assert citation.quoted_span.rstrip("…").strip() in chunk
    assert citation.chunk_id


def test_chunk_id_matches_the_kb_deterministic_point_id():
    """Citation ka id Qdrant ke asli point id se match kare, warna audit trail
    dead-end hai."""
    from app.voice_agent.knowledge_base import _kb_point_id

    chunk = "7 din FREE trial bina card."
    kb = FakeKB([_hit(chunk, STRONG)])

    answer = grounded_answer_typed(kb, "trial hai?", namespace="_global")

    assert answer.citations[0].chunk_id == _kb_point_id("_global", chunk)


def test_strong_second_chunk_is_cited_too():
    first = "Pricing Main plan ₹1,999 per mahina hai."
    second = "Demo bilkul free hai aur 15 minute leta hai."
    kb = FakeKB([_hit(first, 0.90, "business_faq"), _hit(second, 0.80, "niche:test")])

    answer = grounded_answer_typed(kb, "pricing aur demo?", namespace="_global")

    assert answer.answered is True
    assert len(answer.citations) == 2
    assert {c.source for c in answer.citations} == {"business_faq", "niche:test"}


def test_weak_second_chunk_is_not_cited():
    """Answer text me jo nahi gaya, uski citation bhi nahi banni chahiye."""
    first = "Pricing Main plan ₹1,999 per mahina hai."
    second = "Demo bilkul free hai."
    kb = FakeKB([_hit(first, 0.90, "business_faq"), _hit(second, 0.10, "niche:test")])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert answer.answered is True
    assert len(answer.citations) == 1
    assert answer.citations[0].source == "business_faq"


def test_retrieve_is_called_without_reranking():
    """Live/voice budget — reranker latency add nahi karna."""
    kb = FakeKB([_hit("Pricing ₹1,999.", STRONG)])

    grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert kb.calls[0]["rerank"] is False


def test_legacy_retrieve_signature_without_rerank_still_works():
    class LegacyKB:
        def retrieve(self, query, k=3, namespace="default"):
            return [_hit("Pricing ₹1,999 per mahina.", STRONG)]

    answer = grounded_answer_typed(LegacyKB(), "pricing?", namespace="_global")

    assert answer.answered is True


# --------------------------------------------------------------------------- #
# Threshold + strict mode
# --------------------------------------------------------------------------- #


def test_default_threshold_is_the_kb_constant_not_a_new_number():
    """Upstream reference 0.2 use karta hai; hamare backend scores alag scale pe
    hain. Default badalna = silent behaviour change."""
    from app.voice_agent.knowledge_base import _MIN_GROUND_SCORE

    assert kb_grounding._min_ground_score() == pytest.approx(float(_MIN_GROUND_SCORE))


def test_env_threshold_override_is_respected(monkeypatch):
    monkeypatch.setenv("VOICE_KB_MIN_GROUND_SCORE", "0.95")
    kb = FakeKB([_hit("Pricing ₹1,999 per mahina.", 0.90)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert answer.answered is False
    assert answer.reason == REASON_BELOW_MIN_SCORE


def test_garbage_threshold_env_falls_back_instead_of_crashing(monkeypatch):
    monkeypatch.setenv("VOICE_KB_MIN_GROUND_SCORE", "not-a-float")
    from app.voice_agent.knowledge_base import _MIN_GROUND_SCORE

    assert kb_grounding._min_ground_score() == pytest.approx(float(_MIN_GROUND_SCORE))


def test_strict_mode_drops_non_verbatim_span_and_refuses(monkeypatch):
    """Agar answer-build kabhi text GENERATE karne lage, strict mode us citation
    ko jhooti maan kar refuse kare."""
    monkeypatch.setattr(
        kb_grounding, "_kb_trim_sentence", lambda text, max_chars=220: "ye chunk me nahi hai"
    )
    kb = FakeKB([_hit("Pricing ₹1,999 per mahina.", STRONG)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global", strict=True)

    assert answer.answered is False
    assert answer.reason == REASON_NO_VERIFIED_CITATION


def test_lenient_mode_keeps_non_verbatim_span_but_still_cites(monkeypatch):
    monkeypatch.setattr(
        kb_grounding, "_kb_trim_sentence", lambda text, max_chars=220: "ye chunk me nahi hai"
    )
    kb = FakeKB([_hit("Pricing ₹1,999 per mahina.", STRONG)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global", strict=False)

    assert answer.answered is True
    assert len(answer.citations) == 1


def test_strict_flag_defaults_off_so_import_changes_nothing(monkeypatch):
    monkeypatch.delenv("VOICE_KB_STRICT_GROUNDING", raising=False)
    assert kb_grounding._env_flag("VOICE_KB_STRICT_GROUNDING") is False


# --------------------------------------------------------------------------- #
# Leakage / scoring hygiene
# --------------------------------------------------------------------------- #


def test_audit_dict_leaks_no_chunk_or_customer_text():
    chunk = "Client ka secret pricing note: ₹1,999 special."
    kb = FakeKB([_hit(chunk, STRONG, source="client:jiya")])

    answer = grounded_answer_typed(kb, "pricing?", namespace="client:jiya")
    audit = answer.audit_dict()

    serialized = repr(audit)
    assert chunk not in serialized
    assert "secret" not in serialized
    assert audit["citation_count"] == 1
    assert audit["sources"] == ["client:jiya"]


def test_out_of_range_scores_are_clamped_not_rejected():
    """Qdrant/dot-product backends 1.0 se bada score de sakte hain — clamp karo,
    crash mat karo."""
    kb = FakeKB([_hit("Pricing ₹1,999 per mahina.", 3.7)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert answer.answered is True
    assert answer.top_score == 1.0
    assert answer.citations[0].score == 1.0


def test_negative_score_is_clamped_and_refused():
    kb = FakeKB([_hit("Pricing ₹1,999 per mahina.", -0.5)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert answer.answered is False
    assert answer.top_score == 0.0


def test_whitespace_only_chunk_does_not_become_an_answer():
    kb = FakeKB([_hit("   ", STRONG)])

    answer = grounded_answer_typed(kb, "pricing?", namespace="_global")

    assert answer.answered is False
    assert answer.citations == []
