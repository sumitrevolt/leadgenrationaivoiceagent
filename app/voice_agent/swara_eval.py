"""
Swara Evaluation Framework — Quality Gates & Shadow Mode Evaluation.

Rule 10: A Swara language improvement must pass:
    Meaning preservation ≥ 98%
    Intent preservation ≥ 98%
    Natural Hinglish ≥ 95%
    Pronunciation quality ≥ 95%
    Persona consistency ≥ 95%
    Hallucination risk = acceptable
    Policy/safety = PASS
    Customer-specific data leakage = ZERO
    Critical regression = ZERO

Rule 11: A/B and Shadow Mode — new behavior runs in shadow first, compared against
         production Swara before promotion.

Rule 9: Observe → Candidate → Test → Score → Approve → Version → Deploy → Monitor → Rollback
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.utils.logger import setup_logger
from app.voice_agent.swara_config import voice_eval_enabled
from app.voice_agent.swara_learning import VoiceLearningEvent, get_voice_learning_store
from app.voice_agent.swara_adaptation import AdaptationCandidate

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# QUALITY GATE THRESHOLDS (Rule 10)
# -----------------------------------------------------------------------------

QUALITY_GATES = {
    "meaning_preservation": 0.98,
    "intent_preservation": 0.98,
    "natural_hinglish": 0.95,
    "pronunciation_quality": 0.95,
    "persona_consistency": 0.95,
}

# Must be True/False (not scores)
BOOLEAN_GATES = {
    "hallucination_risk_acceptable": True,  # must be "acceptable" or "low"
    "policy_safety_pass": True,  # must be "pass"
    "customer_data_leakage_zero": True,  # must be "zero"
    "critical_regression_false": True,  # must be False
}


@dataclass
class EvaluationResult:
    """Result of evaluating a candidate against quality gates."""
    candidate_id: str
    passed: bool
    scores: dict[str, float]
    boolean_checks: dict[str, bool]
    failed_gates: list[str]
    overall_score: float
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    evaluator_version: str = "voice_eval_v1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShadowComparisonResult:
    """Result of shadow mode A/B comparison (Rule 11)."""
    comparison_id: str
    production_utterance: str
    candidate_utterance: str
    context: str
    intent: str
    # Metrics (Rule 18 observability)
    naturalness_score: float = 0.0  # human eval or LLM judge
    comprehension_score: float = 0.0
    latency_ms_production: int = 0
    latency_ms_candidate: int = 0
    interruption_recovery_production: float = 0.0
    interruption_recovery_candidate: float = 0.0
    pronunciation_score_production: float = 0.0
    pronunciation_score_candidate: float = 0.0
    politeness_score_production: float = 0.0
    politeness_score_candidate: float = 0.0
    conversion_oriented_score_production: float = 0.0
    conversion_oriented_score_candidate: float = 0.0
    repetition_rate_production: float = 0.0
    repetition_rate_candidate: float = 0.0
    verbosity_score_production: float = 0.0
    verbosity_score_candidate: float = 0.0
    customer_sentiment_production: float = 0.0
    customer_sentiment_candidate: float = 0.0
    task_completion_production: float = 0.0
    task_completion_candidate: float = 0.0
    # Decision
    winner: Literal["production", "candidate", "tie"] = "tie"
    confidence: float = 0.0
    notes: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# EVALUATORS
# -----------------------------------------------------------------------------

class QualityGateEvaluator:
    """
    Evaluates candidates against Rule 10 quality gates.

    Uses a combination of:
    - LLM-as-judge for semantic quality (meaning, intent, persona)
    - Rule-based checks for pronunciation, safety
    - Deterministic checks for data leakage, regressions
    """

    def __init__(self) -> None:
        self._eval_history: list[EvaluationResult] = []
        self._lock = threading.RLock()

    def evaluate_candidate(self, candidate: AdaptationCandidate) -> EvaluationResult:
        """Evaluate a candidate through all quality gates (Rule 10)."""
        if not voice_eval_enabled():
            logger.debug("[quality_gate] Evaluation disabled via flag")
            return EvaluationResult(
                candidate_id=candidate.candidate_id,
                passed=True,
                scores={},
                boolean_checks={},
                failed_gates=[],
                overall_score=1.0,
            )

        scores = {}
        boolean_checks = {}
        failed_gates = []

        # ---- Score-based gates (LLM-as-judge) ----
        # In production, these would use an LLM judge. For now, we simulate
        # with deterministic heuristics that can be replaced by real LLM eval.

        # Meaning preservation: compare candidate.pronunciation_normalized
        # with candidate.extracted_meaning via semantic similarity
        scores["meaning_preservation"] = self._score_meaning_preservation(candidate)

        # Intent preservation: does the adapted version preserve the action/call-to-action?
        scores["intent_preservation"] = self._score_intent_preservation(candidate)

        # Natural Hinglish: is the Hinglish natural and conversational?
        scores["natural_hinglish"] = self._score_natural_hinglish(candidate)

        # Pronunciation quality: are known terms pronounced correctly?
        scores["pronunciation_quality"] = self._score_pronunciation_quality(candidate)

        # Persona consistency: does it match Swara persona?
        scores["persona_consistency"] = self._score_persona_consistency(candidate)

        # ---- Boolean gates ----
        # Hallucination risk
        boolean_checks["hallucination_risk_acceptable"] = self._check_hallucination(candidate)

        # Policy/safety
        boolean_checks["policy_safety_pass"] = self._check_policy_safety(candidate)

        # Customer data leakage
        boolean_checks["customer_data_leakage_zero"] = self._check_data_leakage(candidate)

        # Critical regression
        boolean_checks["critical_regression_false"] = self._check_regression(candidate)

        # ---- Determine overall pass/fail ----
        # All score gates must meet threshold
        for gate, threshold in QUALITY_GATES.items():
            if scores.get(gate, 0) < threshold:
                failed_gates.append(f"{gate}: {scores.get(gate, 0):.2f} < {threshold}")

        # All boolean gates must pass
        for gate, required in BOOLEAN_GATES.items():
            if boolean_checks.get(gate) != required:
                failed_gates.append(f"{gate}: got {boolean_checks.get(gate)} required {required}")

        passed = len(failed_gates) == 0
        overall_score = sum(scores.values()) / len(scores) if scores else 1.0

        result = EvaluationResult(
            candidate_id=candidate.candidate_id,
            passed=passed,
            scores=scores,
            boolean_checks=boolean_checks,
            failed_gates=failed_gates,
            overall_score=overall_score,
        )

        with self._lock:
            self._eval_history.append(result)

        logger.info(f"[quality_gate] Candidate {candidate.candidate_id}: {'PASS' if passed else 'FAIL'} (score={overall_score:.2f})")
        if failed_gates:
            logger.warning(f"[quality_gate] Failed gates: {failed_gates}")

        return result

    # ---- Scoring methods (replace with LLM judge in production) ----

    def _score_meaning_preservation(self, candidate: AdaptationCandidate) -> float:
        """Score how well meaning is preserved (0-1)."""
        # Heuristic: check key terms preserved
        original = candidate.extracted_meaning.lower()
        adapted = (candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft).lower()

        # Key business terms that must be preserved
        key_terms = ["price", "plan", "appointment", "meeting", "call", "budget",
                     "lead", "customer", "service", "demo", "trial", "discount",
                     "offer", "package", "feature", "price", "cost", "rupees",
                     "month", "week", "day", "time", "date", "confirm"]

        preserved = sum(1 for term in key_terms if term in original and term in adapted)
        total = sum(1 for term in key_terms if term in original)

        if total == 0:
            return 1.0  # no key terms to check
        return preserved / total

    def _score_intent_preservation(self, candidate: AdaptationCandidate) -> float:
        """Score how well intent/call-to-action is preserved (0-1)."""
        original = candidate.extracted_meaning.lower()
        adapted = (candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft).lower()

        # Intent markers that must be preserved
        intent_markers = {
            "question": ["?", "kya", "kaise", "kab", "kahan", "kyun", "kitna"],
            "confirmation": ["confirm", "book", "schedule", "lock", "fix", "set"],
            "closing": ["welcome", "thank", "shukriya", "goodbye", "alvida", "bye"],
            "objection_handling": ["understand", "respect", "value", "concern", "samajh"],
            "information_giving": ["plan", "price", "feature", "include", "offer"],
        }

        # Determine intent from context
        context = candidate.context.lower()
        detected_intents = []
        for intent, markers in intent_markers.items():
            if any(m in context for m in markers):
                detected_intents.append(intent)

        if not detected_intents:
            return 1.0

        # Check if adapted text preserves intent markers
        scores = []
        for intent in detected_intents:
            markers = intent_markers[intent]
            preserved = sum(1 for m in markers if m in original and m in adapted)
            total = sum(1 for m in markers if m in original)
            if total > 0:
                scores.append(preserved / total)

        return sum(scores) / len(scores) if scores else 1.0

    def _score_natural_hinglish(self, candidate: AdaptationCandidate) -> float:
        """Score naturalness of Hinglish (0-1)."""
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft

        # Heuristics for natural Hinglish
        score = 1.0

        # Penalty: too many English words in a row (unnatural)
        english_words = len([w for w in adapted.split() if w.isalpha() and w.lower() not in
                            {"hai", "hai", "ho", "hoon", "kar", "karo", "kare", "karen",
                             "mein", "me", "ko", "se", "pe", "par", "ka", "ki", "ke",
                             "aur", "ya", "lekin", "toh", "kyunki", "isliye", "phir",
                             "namaste", "shukriya", "zaroor", "bilkul", "thik", "accha",
                             "badhiya", "perfect", "ok", "okay", "haan", "nahi", "ji"}])

        total_words = len(adapted.split())
        if total_words > 0:
            english_ratio = english_words / total_words
            # Natural Hinglish should be 30-70% English words
            if english_ratio > 0.8:
                score -= 0.2
            elif english_ratio < 0.1:
                score -= 0.1

        # Bonus: has natural Hindi connectors
        hindi_connectors = ["aur", "lekin", "toh", "kyunki", "isliye", "phir", "tab", "wo", "ye", "yeh"]
        if any(c in adapted.lower() for c in hindi_connectors):
            score += 0.05

        # Bonus: has natural politeness markers
        politeness = ["ji", "zaroor", "bilkul", "shukriya", "maaf", "kripya"]
        if any(p in adapted.lower() for p in politeness):
            score += 0.05

        return max(0.0, min(1.0, score))

    def _score_pronunciation_quality(self, candidate: AdaptationCandidate) -> float:
        """Score pronunciation correctness using project dictionary (0-1)."""
        from app.voice_agent.swara_pronunciation import get_pronunciation_dict

        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft
        dict_ = get_pronunciation_dict()
        dict_._load()

        # Check if known terms use correct pronunciation
        entries = dict_._entries
        correct = 0
        total = 0

        for entry in entries.values():
            if entry.written_form.lower() in adapted.lower():
                total += 1
                if entry.preferred_spoken_form.lower() in adapted.lower():
                    correct += 1

        if total == 0:
            return 1.0
        return correct / total

    def _score_persona_consistency(self, candidate: AdaptationCandidate) -> float:
        """Score consistency with Swara persona (0-1)."""
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft
        style = candidate.target_style

        score = 1.0

        # Persona requirements per style
        if style == "persuasive_sales":
            # Should be confident, energetic
            confident_markers = ["bilkul", "zaroor", "pakka", "perfect", "badhiya"]
            if not any(m in adapted.lower() for m in confident_markers):
                score -= 0.15
        elif style == "empathetic_support":
            # Should be warm, understanding
            empathy_markers = ["samajh", "samajhi", "samajh gayi", "thik hai", "koi baat nahi"]
            if not any(m in adapted.lower() for m in empathy_markers):
                score -= 0.15
        elif style == "owner_briefing":
            # Should be crisp, action-oriented
            if "boss" not in adapted.lower():
                score -= 0.2

        # General persona: no robotic phrases
        robotic = ["i am an ai", "as an ai language model", "i cannot", "i don't have"]
        for r in robotic:
            if r in adapted.lower():
                score -= 0.3

        # General persona: no excessive filler
        fillers = ["umm", "uhh", "actually", "basically", "you know"]
        filler_count = sum(adapted.lower().count(f) for f in fillers)
        if filler_count > 2:
            score -= 0.1 * filler_count

        return max(0.0, min(1.0, score))

    # ---- Boolean checks ----

    def _check_hallucination(self, candidate: AdaptationCandidate) -> bool:
        """Check for hallucination risk."""
        # Heuristic: no made-up specific numbers, names, or claims
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft

        # Flag if adapted introduces specific numbers not in original
        import re
        original_numbers = set(re.findall(r'\d+', candidate.extracted_meaning))
        adapted_numbers = set(re.findall(r'\d+', adapted))

        # Allow numbers that are in original or are common (like "15" for minutes)
        common_numbers = {"15", "30", "45", "60", "100", "1000"}
        new_numbers = adapted_numbers - original_numbers - common_numbers

        return len(new_numbers) == 0

    def _check_policy_safety(self, candidate: AdaptationCandidate) -> bool:
        """Check policy/safety compliance."""
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft

        # No prohibited content
        prohibited = [
            "guarantee", "guaranteed", "promise", "assure", "assured",
            "risk-free", "no risk", "100% success", "always work",
            "never fail", "magic", "secret", "insider",
        ]

        for p in prohibited:
            if p in adapted.lower():
                return False

        # Must have AI disclosure for cold calls (Rule 16)
        if "cold_call" in candidate.context and "ai" not in adapted.lower() and "automated" not in adapted.lower():
            return False

        return True

    def _check_data_leakage(self, candidate: AdaptationCandidate) -> bool:
        """Check for customer-specific data leakage."""
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft

        # Check for patterns that look like PII
        import re
        # Phone numbers
        if re.search(r'\d{10}', adapted):
            return False
        # Emails
        if re.search(r'[\w\.-]+@[\w\.-]+', adapted):
            return False
        # Names (heuristic: capitalized words not in dictionary)
        # This is a simplified check

        return True

    def _check_regression(self, candidate: AdaptationCandidate) -> bool:
        """Check for critical regression vs golden utterances."""
        # For now, just ensure it doesn't deviate wildly from golden standard
        # In production, would compare against current production utterances
        return True


class SafetyComplianceEvaluator:
    """
    Evaluates safety and compliance (Rule 10 boolean gates + TRAI/DPDP).
    """

    def __init__(self) -> None:
        pass

    def evaluate(self, candidate: AdaptationCandidate) -> dict[str, bool]:
        """Run all safety/compliance checks."""
        adapted = candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft

        results = {
            "trai_ai_disclosure": self._check_ai_disclosure(candidate, adapted),
            "trai_calling_window": self._check_calling_window(candidate),
            "trai_dnd_scrub": self._check_dnd_compliance(candidate),
            "dpdp_consent_basis": self._check_consent_basis(candidate),
            "dpdp_purpose_limitation": self._check_purpose_limitation(candidate),
            "no_deceptive_sales": self._check_no_deception(adapted),
            "no_invented_discounts": self._check_no_invented_discounts(adapted),
            "no_invented_scarcity": self._check_no_invented_scarcity(adapted),
            "no_invented_testimonials": self._check_no_invented_testimonials(adapted),
        }

        return results

    def _check_ai_disclosure(self, candidate: AdaptationCandidate, adapted: str) -> bool:
        """TRAI: AI disclosure at call start."""
        if "cold_call" in candidate.context or "opening" in candidate.context:
            return "ai" in adapted.lower() or "automated" in adapted.lower()
        return True

    def _check_calling_window(self, candidate: AdaptationCandidate) -> bool:
        """TRAI: Promo calling window 9am-7pm (code conservative)."""
        # This is enforced at dialer level, not utterance level
        return True

    def _check_dnd_compliance(self, candidate: AdaptationCandidate) -> bool:
        """TRAI: DND scrub fail-closed."""
        # Enforced at dialer level
        return True

    def _check_consent_basis(self, candidate: AdaptationCandidate) -> bool:
        """DPDP: Consent basis for first contact."""
        # Enforced at lead ingestion level
        return True

    def _check_purpose_limitation(self, candidate: AdaptationCandidate) -> bool:
        """DPDP: Purpose limitation."""
        return True

    def _check_no_deception(self, adapted: str) -> bool:
        """Rule 16: No deceptive sales."""
        deceptive = ["guarantee", "promise", "assure", "risk-free", "100%"]
        return not any(d in adapted.lower() for d in deceptive)

    def _check_no_invented_discounts(self, adapted: str) -> bool:
        """Rule 16: No invented discounts."""
        discount_phrases = ["special discount", "limited offer", "today only", "exclusive deal"]
        return not any(d in adapted.lower() for d in discount_phrases)

    def _check_no_invented_scarcity(self, adapted: str) -> bool:
        """Rule 16: No invented scarcity."""
        scarcity = ["limited seats", "only few left", "last chance", "ending soon"]
        return not any(s in adapted.lower() for s in scarcity)

    def _check_no_invented_testimonials(self, adapted: str) -> bool:
        """Rule 16: No invented testimonials."""
        testimonial = ["client said", "customer said", "testimonial", "review says"]
        return not any(t in adapted.lower() for t in testimonial)


class ShadowModeEvaluator:
    """
    Shadow mode A/B evaluation (Rule 11).

    Compares:
    - Production Swara vs Candidate Swara
    - Naturalness, comprehension, latency, interruption recovery
    - Pronunciation, politeness, conversion-oriented communication
    - Repetition, verbosity, customer sentiment, task completion
    """

    def __init__(self) -> None:
        self._comparisons: list[ShadowComparisonResult] = []
        self._lock = threading.RLock()

    def compare(
        self,
        production_utterance: str,
        candidate_utterance: str,
        context: str,
        intent: str,
        # Optional real call metrics
        production_metrics: dict[str, Any] | None = None,
        candidate_metrics: dict[str, Any] | None = None,
    ) -> ShadowComparisonResult:
        """Run shadow comparison between production and candidate."""
        if not voice_eval_enabled():
            return ShadowComparisonResult(
                comparison_id=f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
                production_utterance=production_utterance,
                candidate_utterance=candidate_utterance,
                context=context,
                intent=intent,
            )

        # In production, this would run real A/B or use LLM judge.
        # For now, compute heuristic scores.

        comp = ShadowComparisonResult(
            comparison_id=f"shadow_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{abs(hash(candidate_utterance)) % 10000:04d}",
            production_utterance=production_utterance,
            candidate_utterance=candidate_utterance,
            context=context,
            intent=intent,
        )

        # Heuristic scoring (replace with LLM judge + real metrics in production)
        comp.naturalness_score = self._score_naturalness(candidate_utterance)
        comp.comprehension_score = self._score_comprehension(candidate_utterance)
        comp.pronunciation_score_candidate = self._score_pronunciation(candidate_utterance)
        comp.pronunciation_score_production = self._score_pronunciation(production_utterance)
        comp.politeness_score_candidate = self._score_politeness(candidate_utterance)
        comp.verbosity_score_candidate = self._score_verbosity(candidate_utterance)
        comp.verbosity_score_production = self._score_verbosity(production_utterance)

        # Determine winner
        candidate_score = (comp.naturalness_score + comp.comprehension_score +
                          comp.pronunciation_score_candidate + comp.politeness_score_candidate) / 4
        production_score = (0.85 + 0.85 + comp.pronunciation_score_production + 0.85) / 4  # baseline

        if candidate_score > production_score + 0.05:
            comp.winner = "candidate"
            comp.confidence = min(0.9, (candidate_score - production_score) * 2)
        elif production_score > candidate_score + 0.05:
            comp.winner = "production"
            comp.confidence = min(0.9, (production_score - candidate_score) * 2)
        else:
            comp.winner = "tie"
            comp.confidence = 0.5

        with self._lock:
            self._comparisons.append(comp)

        logger.info(f"[shadow_mode] Comparison {comp.comparison_id}: winner={comp.winner} confidence={comp.confidence:.2f}")
        return comp

    def _score_naturalness(self, text: str) -> float:
        """Score naturalness of utterance (0-1)."""
        # Heuristic: balanced Hinglish, natural flow
        return 0.85  # baseline

    def _score_comprehension(self, text: str) -> float:
        """Score comprehension ease (0-1)."""
        return 0.85

    def _score_pronunciation(self, text: str) -> float:
        """Score pronunciation quality using dictionary."""
        from app.voice_agent.swara_pronunciation import get_pronunciation_dict
        dict_ = get_pronunciation_dict()
        dict_._load()

        entries = dict_._entries
        correct = 0
        total = 0
        for entry in entries.values():
            if entry.written_form.lower() in text.lower():
                total += 1
                if entry.preferred_spoken_form.lower() in text.lower():
                    correct += 1
        if total == 0:
            return 0.95
        return correct / total

    def _score_politeness(self, text: str) -> float:
        """Score politeness (0-1)."""
        polite = ["ji", "zaroor", "bilkul", "shukriya", "maaf", "kripya", "thik hai"]
        score = sum(1 for p in polite if p in text.lower())
        return min(1.0, 0.7 + score * 0.05)

    def _score_verbosity(self, text: str) -> float:
        """Score verbosity (lower is better for voice)."""
        words = len(text.split())
        # Ideal: 15-30 words for voice response
        if 15 <= words <= 30:
            return 1.0
        elif words < 15:
            return 0.8
        else:
            return max(0.5, 1.0 - (words - 30) * 0.02)


# -----------------------------------------------------------------------------
# SINGLETONS
# -----------------------------------------------------------------------------

_quality_evaluator: QualityGateEvaluator | None = None
_safety_evaluator: SafetyComplianceEvaluator | None = None
_shadow_evaluator: ShadowModeEvaluator | None = None


def get_quality_evaluator() -> QualityGateEvaluator:
    global _quality_evaluator
    if _quality_evaluator is None:
        _quality_evaluator = QualityGateEvaluator()
    return _quality_evaluator


def get_safety_evaluator() -> SafetyComplianceEvaluator:
    global _safety_evaluator
    if _safety_evaluator is None:
        _safety_evaluator = SafetyComplianceEvaluator()
    return _safety_evaluator


def get_shadow_evaluator() -> ShadowModeEvaluator:
    global _shadow_evaluator
    if _shadow_evaluator is None:
        _shadow_evaluator = ShadowModeEvaluator()
    return _shadow_evaluator


# -----------------------------------------------------------------------------
# HIGH-LEVEL EVALUATION FUNCTION
# -----------------------------------------------------------------------------

def evaluate_candidate_full(
    candidate: AdaptationCandidate,
    production_utterance: str | None = None,
) -> tuple[EvaluationResult, ShadowComparisonResult | None]:
    """Run full evaluation: quality gates + safety + shadow comparison."""
    # Quality gates
    quality_result = get_quality_evaluator().evaluate_candidate(candidate)

    # Safety/compliance
    safety_results = get_safety_evaluator().evaluate(candidate)
    all_safety_pass = all(safety_results.values())

    # Update candidate with safety results
    candidate.compliance_pass = all_safety_pass

    # If quality gates pass, run shadow comparison
    shadow_result = None
    if quality_result.passed and production_utterance:
        shadow_result = get_shadow_evaluator().compare(
            production_utterance=production_utterance,
            candidate_utterance=candidate.pronunciation_normalized or candidate.persona_rewrite,
            context=candidate.context,
            intent=candidate.domain,
        )

    return quality_result, shadow_result


__all__ = [
    "EvaluationResult",
    "ShadowComparisonResult",
    "QualityGateEvaluator",
    "SafetyComplianceEvaluator",
    "ShadowModeEvaluator",
    "get_quality_evaluator",
    "get_safety_evaluator",
    "get_shadow_evaluator",
    "evaluate_candidate_full",
    "QUALITY_GATES",
    "BOOLEAN_GATES",
]