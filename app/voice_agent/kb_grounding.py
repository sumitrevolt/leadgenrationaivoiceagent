"""
Typed KB grounding + refusal contract (A1)
==========================================

`KnowledgeBase.grounded_answer()` aaj bhi hallucinate nahi karta — uske andar
relevance gate (`_MIN_GROUND_SCORE`) aur safe fallback line already hai. Problem
uske *return type* me hai: wo ek bare `str` deta hai, to caller ke paas koi
structural tareeka nahi ki

  1. ye answer tha ya refusal (sirf fallback string se compare karke pata chalta),
  2. answer kis chunk/source se aaya (audit trail zero),
  3. "answered but zero evidence" ko rok kon raha hai (aaj: sirf convention).

Ye module wahi teen gaps band karta hai — grounding ko **type** bana kar. Ulta
kaha jaaye: `answered=True` ke saath khaali citations ek `ValidationError` hai,
prose ki galti nahi.

Design constraints (jaan-boojh kar):
  - **Frozen voice surface ko chhua NAHI gaya.** Ye module `knowledge_base.py` ko
    edit nahi karta; sirf uske PUBLIC `retrieve()` ke upar compose karta hai aur
    uske constants import karta hai (taaki wording/threshold kabhi drift na ho).
  - **INERT — koi caller nahi.** Reply path wiring owner approval ka kaam hai
    (Swara/voice = FROZEN). Ye file aa jaane se prod behaviour badalta NAHI.
  - **Default threshold = aaj ka threshold** (`_MIN_GROUND_SCORE`, 0.04). Upstream
    reference 0.2 use karta hai, par hamare scores backend-dependent hain
    (keyword cosine vs Chroma `1/(1+dist)` vs Qdrant) — isliye 0.2 hardcode karna
    silent behaviour change hota. Env se tune karo, guess mat karo.

Usage:
    from app.voice_agent.kb_grounding import grounded_answer_typed
    from app.voice_agent.knowledge_base import get_knowledge_base

    ans = grounded_answer_typed(get_knowledge_base(), "pricing kya hai?",
                                namespace="_global")
    if ans.answered:
        speak(ans.text)          # har citation ka chunk_id + source audit me hai
    else:
        speak(ans.text)          # = existing safe fallback line, byte-identical

Env:
    VOICE_KB_MIN_GROUND_SCORE  float  — refusal threshold override (default = KB ka apna)
    VOICE_KB_STRICT_GROUNDING  bool   — ON: jo citation apne chunk me verbatim
                                        verify na ho wo DROP; sab drop ho gaye to
                                        refusal. OFF (default): warn-only log.
"""

from __future__ import annotations

import os
import uuid
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

# Wording/threshold/trimming ko KB se hi import karo — duplicate karne se drift
# hota hai (do jagah 0.04 likha ho to ek din ek badalti hai, doosri nahi).
try:
    from app.voice_agent.knowledge_base import _MIN_GROUND_SCORE as _KB_MIN_GROUND_SCORE
    from app.voice_agent.knowledge_base import _SAFE_FALLBACK as _KB_SAFE_FALLBACK
    from app.voice_agent.knowledge_base import _trim_sentence as _kb_trim_sentence
except Exception as _e:  # pragma: no cover - import-safety only
    logger.debug(f"kb_grounding: KB constants unavailable ({_e}); using local copies")
    _KB_MIN_GROUND_SCORE = 0.04
    _KB_SAFE_FALLBACK = (
        "Achha sawaal — main aapke liye exact detail team se confirm karwa deti hoon."
    )

    def _kb_trim_sentence(text: str, max_chars: int = 220) -> str:
        text = (text or "").strip()
        return text[:max_chars]


# Refusal reasons — bounded set, metrics/log me safe (koi customer text nahi).
REASON_EMPTY_QUERY = "empty_query"
REASON_RETRIEVE_FAILED = "retrieve_failed"
REASON_NO_HITS = "no_hits"
REASON_BELOW_MIN_SCORE = "below_min_score"
REASON_NO_VERIFIED_CITATION = "no_verified_citation"

# `grounded_answer()` ka second-chunk rule — yahi ratio wahan hardcoded hai.
_SECOND_CHUNK_RATIO = 0.6


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _min_ground_score() -> float:
    """Refusal threshold — env override, warna KB ka apna constant."""
    raw = (os.getenv("VOICE_KB_MIN_GROUND_SCORE") or "").strip()
    if not raw:
        return float(_KB_MIN_GROUND_SCORE)
    try:
        return float(raw)
    except ValueError:
        logger.warning(
            "VOICE_KB_MIN_GROUND_SCORE=%r is not a float; falling back to %s",
            raw,
            _KB_MIN_GROUND_SCORE,
        )
        return float(_KB_MIN_GROUND_SCORE)


def _point_id(namespace: str, text: str) -> str:
    """Stable chunk id. KB ka `_kb_point_id` hi asli id hai — wahi use karo taaki
    citation ka id Qdrant ke point se match kare. Private symbol hai, isliye
    fallback formula bhi rakhi hai (bit-identical)."""
    try:
        from app.voice_agent.knowledge_base import _kb_point_id

        return _kb_point_id(namespace, text)
    except Exception:  # pragma: no cover
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace or 'default'}|{text or ''}"))


def _clamp01(value: Any) -> float:
    try:
        return round(min(max(float(value), 0.0), 1.0), 4)
    except (TypeError, ValueError):
        return 0.0


class Citation(BaseModel):
    """Ek retrieved chunk ka verifiable pointer. Blank field allowed nahi —
    khaali citation "audit trail hai" ka jhoota bharosa deti hai."""

    source: str = Field(description="KB source label, e.g. 'niche:solar_commercial'")
    chunk_id: str = Field(description="Deterministic KB point id (namespace|text)")
    quoted_span: str = Field(description="Verbatim span jo answer me gaya")
    score: float = Field(ge=0.0, le=1.0, description="Retrieval score, clamped")

    @field_validator("source", "chunk_id", "quoted_span")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("citation fields must not be blank")
        return value


class GroundedAnswer(BaseModel):
    """KB answer + uska evidence, ek hi type me.

    Do-tarfa invariant (yahi is module ka poora point hai):
      - `answered=True`  → kam se kam 1 citation ZAROORI
      - `answered=False` → citations BILKUL khaali

    Isse "confident answer, zero evidence" ek ValidationError ban jaata hai —
    prod me chupchaap nikal jaane wali galti nahi.
    """

    text: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)
    answered: bool
    namespace: str = "default"
    top_score: float = Field(default=0.0, ge=0.0, le=1.0)
    reason: str | None = Field(
        default=None, description="Refusal reason (bounded enum-ish string); None jab answered"
    )

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise ValueError("text must not be blank")
        return value

    @model_validator(mode="after")
    def _answer_and_citations_must_agree(self) -> GroundedAnswer:
        if self.answered and not self.citations:
            raise ValueError("answered=True requires at least one citation")
        if not self.answered and self.citations:
            raise ValueError("answered=False must carry zero citations")
        if self.answered and self.reason is not None:
            raise ValueError("answered=True must not carry a refusal reason")
        if not self.answered and not self.reason:
            raise ValueError("answered=False requires a refusal reason")
        return self

    @classmethod
    def refusal(
        cls,
        reason: str,
        *,
        namespace: str = "default",
        top_score: float = 0.0,
    ) -> GroundedAnswer:
        """Safe fallback — customer ko wahi line sunai deti hai jo aaj sunai deti
        hai (`_SAFE_FALLBACK` import kiya hua hai, copy nahi)."""
        return cls(
            text=_KB_SAFE_FALLBACK,
            citations=[],
            confidence=_clamp01(top_score),
            answered=False,
            namespace=namespace or "default",
            top_score=_clamp01(top_score),
            reason=reason,
        )

    def audit_dict(self) -> dict[str, Any]:
        """Log/metric-safe summary — koi customer text nahi, koi chunk text nahi."""
        return {
            "answered": self.answered,
            "reason": self.reason,
            "confidence": self.confidence,
            "top_score": self.top_score,
            "namespace": self.namespace,
            "citation_count": len(self.citations),
            "sources": sorted({c.source for c in self.citations}),
        }


def _verbatim_ok(span: str, chunk: str) -> bool:
    """`_trim_sentence` sirf kaat-ta hai, likhta nahi — to trimmed span apne chunk
    ka substring hona chahiye. Trailing ellipsis trimmer ne lagaya hai, chunk me
    nahi hai, isliye compare se pehle hata do."""
    span = (span or "").strip().rstrip("…").strip()
    if not span:
        return False
    return span in (chunk or "")


def grounded_answer_typed(
    kb: Any,
    query: str,
    *,
    namespace: str = "default",
    k: int = 3,
    min_score: float | None = None,
    strict: bool | None = None,
) -> GroundedAnswer:
    """`kb.grounded_answer()` ka typed, cited equivalent.

    Answer text jaan-boojh kar wahi banaya gaya hai jo `grounded_answer()` banata
    hai (top chunk + optional second chunk jab wo `0.6 * top` se strong ho) —
    taaki wiring ke waqt customer ko sunai dene wali line na badle. Naya sirf ye
    hai ki har chunk ab ek verifiable `Citation` ban kar wapas aata hai, aur
    refusal ek `bool` hai, string-compare nahi.

    Args:
        kb: `KnowledgeBase` (ya koi bhi object jiske paas compatible `retrieve`).
        query: user ka sawaal.
        namespace: client/niche scope.
        k: top-k.
        min_score: threshold override; `None` = env/KB default.
        strict: `None` = `VOICE_KB_STRICT_GROUNDING` env se.

    Returns:
        `GroundedAnswer` — kabhi raise nahi karta retrieval failure pe; refusal
        deta hai (voice path pe exception = dead air).
    """
    ns = namespace or "default"
    if not (query or "").strip():
        return GroundedAnswer.refusal(REASON_EMPTY_QUERY, namespace=ns)

    threshold = _min_ground_score() if min_score is None else float(min_score)
    strict_mode = _env_flag("VOICE_KB_STRICT_GROUNDING") if strict is None else bool(strict)

    # rerank=False — live/voice path pe latency budget nahi hai (KB docstring ka
    # apna guidance). Retrieval fail = refusal, crash nahi.
    try:
        hits = kb.retrieve(query, k=max(1, k), namespace=ns, rerank=False) or []
    except TypeError:
        # koi test-double / purana signature jise `rerank` nahi pata.
        try:
            hits = kb.retrieve(query, k=max(1, k), namespace=ns) or []
        except Exception as e:  # pragma: no cover
            logger.warning(f"kb_grounding retrieve failed (compat path): {e}")
            return GroundedAnswer.refusal(REASON_RETRIEVE_FAILED, namespace=ns)
    except Exception as e:
        logger.warning(f"kb_grounding retrieve failed: {e}")
        return GroundedAnswer.refusal(REASON_RETRIEVE_FAILED, namespace=ns)

    if not hits:
        return GroundedAnswer.refusal(REASON_NO_HITS, namespace=ns)

    top = hits[0] or {}
    top_score = _clamp01(top.get("score", 0.0))
    # Relevance gate — kamzor match pe LLM/answer tak jaane ka koi matlab nahi.
    if top_score < threshold:
        return GroundedAnswer.refusal(REASON_BELOW_MIN_SCORE, namespace=ns, top_score=top_score)

    used: list[dict[str, Any]] = [top]
    answer = _kb_trim_sentence(top.get("text", ""))

    if len(hits) > 1:
        second = hits[1] or {}
        second_text = (second.get("text") or "").strip()
        if (
            second_text
            and _clamp01(second.get("score", 0.0)) >= top_score * _SECOND_CHUNK_RATIO
            and second_text != (top.get("text") or "").strip()
        ):
            extra = _kb_trim_sentence(second_text)
            if extra and extra.lower() not in answer.lower():
                answer = f"{answer} {extra}".strip()
                used.append(second)

    if not answer.strip():
        # top chunk khaali/whitespace tha — answered nahi keh sakte.
        return GroundedAnswer.refusal(REASON_NO_HITS, namespace=ns, top_score=top_score)

    citations: list[Citation] = []
    for hit in used:
        chunk = hit.get("text") or ""
        span = _kb_trim_sentence(chunk)
        if not span.strip():
            continue
        if not _verbatim_ok(span, chunk):
            # Aaj tak aisa hona nahi chahiye (trimmer sirf slice karta hai). Agar
            # ho gaya, to matlab answer-build ka koi rasta text *generate* kar
            # raha hai — us case me citation jhooti hai.
            logger.warning(
                "kb_grounding: non-verbatim span for source=%s ns=%s (strict=%s)",
                hit.get("source") or "kb",
                ns,
                strict_mode,
            )
            if strict_mode:
                continue
        citations.append(
            Citation(
                source=(hit.get("source") or "kb").strip() or "kb",
                chunk_id=_point_id(ns, chunk),
                quoted_span=span,
                score=_clamp01(hit.get("score", 0.0)),
            )
        )

    if not citations:
        # strict mode ne sab kuch drop kar diya → answer ke peeche evidence nahi.
        return GroundedAnswer.refusal(
            REASON_NO_VERIFIED_CITATION, namespace=ns, top_score=top_score
        )

    return GroundedAnswer(
        text=answer,
        citations=citations,
        confidence=top_score,
        answered=True,
        namespace=ns,
        top_score=top_score,
        reason=None,
    )


__all__ = [
    "Citation",
    "GroundedAnswer",
    "grounded_answer_typed",
    "REASON_EMPTY_QUERY",
    "REASON_RETRIEVE_FAILED",
    "REASON_NO_HITS",
    "REASON_BELOW_MIN_SCORE",
    "REASON_NO_VERIFIED_CITATION",
]
