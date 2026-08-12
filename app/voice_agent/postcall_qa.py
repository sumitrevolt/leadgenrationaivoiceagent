"""Post-call QA + misunderstanding detector + 30-call training proposals.

Agents are NOT in the live audio path. Deterministic checks first; optional
free-LLM batch analysis behind flags. Never auto-changes pricing/legal/consent.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PROPOSALS_PATH = Path("data") / "voice_training_proposals.jsonl"


@dataclass
class PostCallQAResult:
    score: float
    misunderstanding: bool
    opener_repeat: bool
    pricing_invented: bool
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "misunderstanding": self.misunderstanding,
            "opener_repeat": self.opener_repeat,
            "pricing_invented": self.pricing_invented,
            "issues": list(self.issues),
            "suggestions": list(self.suggestions),
        }


def _looks_greeting(text: str) -> bool:
    t = (text or "").lower()
    return ("namaste" in t or "main swara" in t or "ai assistant" in t) and (
        "baat kar" in t or "minute" in t or "second" in t
    )


def analyze_transcript(
    history: list[dict[str, str]],
    *,
    approved_prices: list[str] | None = None,
) -> PostCallQAResult:
    """Deterministic post-call QA. Never raises."""
    issues: list[str] = []
    suggestions: list[str] = []
    assistants = [
        str(m.get("content") or "")
        for m in (history or [])
        if isinstance(m, dict) and m.get("role") == "assistant"
    ]
    users = [
        str(m.get("content") or "")
        for m in (history or [])
        if isinstance(m, dict) and m.get("role") == "user"
    ]

    opener_repeat = False
    greet_idxs = [i for i, t in enumerate(assistants) if _looks_greeting(t)]
    if len(greet_idxs) >= 2:
        opener_repeat = True
        issues.append("opener_repeat")
        suggestions.append("Block full opener after greeting_completed=1")

    misunderstanding = False
    clarify_n = sum(
        1
        for t in assistants
        if "clear nahi" in t.lower() or "dobara" in t.lower() or "repeat" in t.lower()
    )
    if clarify_n >= 3:
        misunderstanding = True
        issues.append("excessive_clarification")
        suggestions.append("Tighten STT gate / bias keyterms")

    # User asked price but bot never mentioned ₹ or plan names.
    price_ask = any(
        any(w in u.lower() for w in ("kitna", "price", "pricing", "paisa", "rupee", "₹", "plan"))
        for u in users
    )
    price_ans = any(
        "₹" in a or "1999" in a or "5999" in a or "plan" in a.lower() for a in assistants
    )
    if price_ask and not price_ans:
        misunderstanding = True
        issues.append("price_question_unanswered")
        suggestions.append("Inject APPROVED_PRICING into context block")

    pricing_invented = False
    # Crude: invented round numbers not in approved list.
    approved = set(approved_prices or ["1999", "5999", "4999", "9999", "19999"])
    for a in assistants:
        for m in __import__("re").findall(r"₹\s*([\d,]+)", a):
            digits = m.replace(",", "")
            if digits and digits not in approved and len(digits) >= 3:
                pricing_invented = True
                issues.append(f"invented_price:{digits}")
                suggestions.append("Reject model pricing; server-owned packages only")
                break

    score = 1.0
    score -= 0.25 * len(set(issues))
    if opener_repeat:
        score -= 0.2
    if misunderstanding:
        score -= 0.15
    if pricing_invented:
        score -= 0.3
    score = max(0.0, min(1.0, score))

    return PostCallQAResult(
        score=score,
        misunderstanding=misunderstanding,
        opener_repeat=opener_repeat,
        pricing_invented=pricing_invented,
        issues=issues,
        suggestions=suggestions,
    )


def propose_training_correction(
    *,
    batch_count: int,
    qa_summary: dict[str, Any],
    allowed_surfaces: list[str] | None = None,
) -> dict[str, Any]:
    """Versioned proposal — may update prompt/policy/examples/STT/route/timeout/QA.
    MUST NOT touch pricing/legal/consent/opt-out/tenant auth.
    """
    forbidden = {"pricing", "legal", "consent", "opt_out", "tenant_auth", "fine_tune"}
    surfaces = [
        s
        for s in (allowed_surfaces or ["prompt", "stt_filters", "route", "timeout", "qa_rubric"])
        if s not in forbidden
    ]
    proposal = {
        "version": f"train_{batch_count}_{int(time.time())}",
        "batch_count": batch_count,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "allowed_surfaces": surfaces,
        "forbidden_surfaces": sorted(forbidden),
        "qa_summary": qa_summary,
        "status": "pending_approval",
        "auto_fine_tune": False,
    }
    try:
        _PROPOSALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with _PROPOSALS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(proposal, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[postcall_qa] proposal write failed: %s", e)
    return proposal


def training_loop_enabled() -> bool:
    return (os.environ.get("VOICE_TRAINING_LOOP", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )
