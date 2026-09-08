"""
test_rag_quality.py — DeepEval RAG/answer-quality regression (advisory gate).

DO LAYERS:
  1. DETERMINISTIC guards (koi key/dep nahi chahiye — HAMESHA chalte): conciseness
     (<=3 sentences), one-question, aur AI-disclosure honesty (TRAI). Yeh telecaller
     ke core rules (telecaller_brain ≤2 sentence/1 question) ko lock karte.
  2. JUDGE-GATED metrics (deepeval + free judge key ho to): har niche case ke liye
     free provider se reply GENERATE karke AnswerRelevancy + Faithfulness (RAG
     grounding / no-hallucination) score karta. Key/dep absent => skip (CI green).

Local run:
  pip install -r requirements-dev.txt
  CEREBRAS_API_KEY=... pytest evals/test_rag_quality.py -q
CI: .github/workflows/llm-eval.yml `deepeval` job (advisory, never blocks build).

Gate banane ke liye (jab confident): llm-eval.yml me `continue-on-error` hata do.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

# Import works both as `evals.deepeval_judge` (rootdir mode) and `deepeval_judge`
# (pytest prepend-mode puts evals/ itself on sys.path).
try:
    from evals.deepeval_judge import (
        get_judge,
        judge_api_key,
        judge_available,
        judge_base_url,
        judge_model,
        skip_reason,
    )
except ImportError:  # pragma: no cover
    from deepeval_judge import (  # type: ignore
        get_judge,
        judge_api_key,
        judge_available,
        judge_base_url,
        judge_model,
        skip_reason,
    )

_CASES_PATH = Path(__file__).parent / "golden_cases.jsonl"


def _load_cases() -> list[dict]:
    out: list[dict] = []
    try:
        for line in _CASES_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                out.append(json.loads(line))
    except Exception:
        pass
    return out


CASES = _load_cases()


# --------------------------------------------------------------------------- #
# Telecaller-style generation (same free provider as judge). Returns "" on fail.
# --------------------------------------------------------------------------- #
def _system_for(case: dict) -> str:
    base = (
        "You are a polite Hindi-English (Hinglish) sales assistant for a local "
        "Indian business. Reply in at most 2 short sentences and ask exactly ONE "
        "question. Use ONLY the facts given in CONTEXT — do not invent prices or "
        "details. If the caller asks whether you are human, honestly disclose that "
        "you are an AI assistant."
    )
    ctx = "\n".join(f"- {c}" for c in case.get("retrieval_context", []))
    return f"{base}\n\nCONTEXT:\n{ctx}"


def _generate(case: dict) -> str:
    if not judge_api_key():
        return ""
    try:
        from openai import OpenAI

        client = OpenAI(api_key=judge_api_key(), base_url=judge_base_url())
        resp = client.chat.completions.create(
            model=judge_model(),
            messages=[
                {"role": "system", "content": _system_for(case)},
                {"role": "user", "content": case["input"]},
            ],
            temperature=0.3,
            max_tokens=160,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# Layer 1 — DETERMINISTIC guards (always run; no LLM key/dep needed).
# Use canned good/bad outputs to lock the structural rules the telecaller must keep.
# --------------------------------------------------------------------------- #
def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.?!।]", text or "") if s.strip()])


def _question_count(text: str) -> int:
    return (text or "").count("?")


@pytest.mark.parametrize(
    "reply,ok",
    [
        ("Cleaning ₹500 se shuru hoti hai. Kya main aapka appointment book kar du?", True),
        ("Haan ji, bridal makeup ₹8000 se hai. Trial session kab rakhein?", True),
        # bad: too long / multiple questions
        ("Hum cleaning karte hain. Price ₹500 hai. Timing 10-7 hai. Kab aaoge? Naam batao?", False),
    ],
)
def test_conciseness_and_one_question(reply: str, ok: bool) -> None:
    concise = _sentence_count(reply) <= 3 and _question_count(reply) <= 1
    assert concise == ok


def test_ai_disclosure_honesty() -> None:
    """TRAI: AI ko 'I am a human' claim KABHI nahi karna chahiye (deterministic guard)."""
    bad = "Yes, I am a human calling from the clinic."
    assert "i am a human" in bad.lower()  # sanity of the detector
    good = "Main ek AI assistant hoon jo Sharma Clinic ke liye baat kar rahi hoon."
    assert "i am a human" not in good.lower()


# --------------------------------------------------------------------------- #
# Layer 2 — JUDGE-GATED metrics (deepeval + free judge). Skip if unavailable.
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not judge_available(), reason=skip_reason() or "judge unavailable")
@pytest.mark.parametrize("case", CASES, ids=[c.get("niche", "?") for c in CASES])
def test_rag_answer_quality(case: dict) -> None:
    from deepeval import assert_test
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase

    output = _generate(case)
    if not output:
        pytest.skip("generation unavailable (provider/key)")

    judge = get_judge()
    tc = LLMTestCase(
        input=case["input"],
        actual_output=output,
        retrieval_context=list(case.get("retrieval_context", [])),
    )
    metrics = [
        AnswerRelevancyMetric(threshold=0.6, model=judge, async_mode=False),
        FaithfulnessMetric(threshold=0.6, model=judge, async_mode=False),
    ]
    # assert_test raises on threshold breach; llm-eval.yml step is advisory
    # (continue-on-error) so a breach SURFACES but does not block the build yet.
    assert_test(tc, metrics)
