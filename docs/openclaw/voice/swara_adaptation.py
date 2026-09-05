"""
Swara Hinglish Adaptation Pipeline — English → Natural Indian Hinglish.

Rule 5: Pipeline for converting OpenClaw English explanations into high-quality
        conversational Hinglish for Swara.

Pipeline stages:
    1. OpenClaw English input
    2. Meaning extraction
    3. Natural Indian Hinglish adaptation
    4. Swara persona rewrite
    5. Pronunciation normalization
    6. Conversation-quality evaluation
    7. Safety/compliance evaluation
    8. Golden-example candidate
    9. Approved shared memory

Rule 3: Language mirroring — if Swara discovers better Hinglish, OpenClaw may learn it.
Rule 12: No uncontrolled self-training — candidate must pass evaluation before production.

This module provides the adaptation logic. Evaluation is in swara_eval.py.
"""

from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.utils.logger import setup_logger
from app.voice_agent.swara_config import hinglish_adaptation_enabled

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# SCHEMAS
# -----------------------------------------------------------------------------

AdaptationStage = Literal[
    "english_input",
    "meaning_extracted",
    "hinglish_adapted",
    "persona_rewritten",
    "pronunciation_normalized",
    "quality_evaluated",
    "safety_evaluated",
    "golden_candidate",
    "approved",
]

HinglishStyle = Literal[
    "casual_conversational",
    "professional_business",
    "persuasive_sales",
    "empathetic_support",
    "energetic_pitch",
    "owner_briefing",
]


@dataclass
class AdaptationCandidate:
    """A candidate utterance going through the adaptation pipeline."""
    candidate_id: str
    # Input
    english_text: str
    domain: str
    context: str
    target_style: HinglishStyle = "professional_business"
    # Pipeline outputs (filled progressively)
    extracted_meaning: str = ""
    hinglish_draft: str = ""
    persona_rewrite: str = ""
    pronunciation_normalized: str = ""
    # Evaluation scores
    quality_scores: dict[str, float] = field(default_factory=dict)
    safety_pass: bool = False
    compliance_pass: bool = False
    # Metadata
    current_stage: AdaptationStage = "english_input"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    model_version: str = "swara_language_policy_v1"
    source: str = "openclaw_english"  # openclaw_english | owner_correction | manual

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# HINGLISH ADAPTATION RULES & PATTERNS
# -----------------------------------------------------------------------------

# Common English → Hinglish transformations for business context
# These are patterns, not literal translations — preserve meaning, optimize natural speech.

_ENGLISH_TO_HINGLISH_PATTERNS = [
    # Greetings & openings
    (r"\bHello\b", "Namaste"),
    (r"\bHi there\b", "Namaste"),
    (r"\bGood morning\b", "Shubh savere"),
    (r"\bGood afternoon\b", "Namaste"),
    (r"\bGood evening\b", "Namaste"),

    # Confirmation & agreement
    (r"\bPerfect\b", "Perfect"),
    (r"\bGreat\b", "Badhiya"),
    (r"\bExcellent\b", "Bahut badhiya"),
    (r"\bSure\b", "Zaroor"),
    (r"\bOf course\b", "Bilkul"),
    (r"\bAbsolutely\b", "Bilkul"),
    (r"\bDefinitely\b", "Pakka"),
    (r"\bOkay\b", "Thik hai"),
    (r"\bAlright\b", "Thik hai"),
    (r"\bSounds good\b", "Accha laga"),

    # Understanding & acknowledgment
    (r"\bI understand\b", "Main samajh gayi"),
    (r"\bI see\b", "Main samajhi"),
    (r"\bThat makes sense\b", "Ye baat samajh aa gayi"),
    (r"\bGot it\b", "Samajh gayi"),
    (r"\bUnderstood\b", "Samajh gayi"),

    # Questions
    (r"\bWould you be open to\b", "Kya aap open hain"),
    (r"\bWould you like to\b", "Kya aap chahenge"),
    (r"\bCan you\b", "Kya aap"),
    (r"\bCould you\b", "Kya aap"),
    (r"\bWhat is\b", "Kya hai"),
    (r"\bHow much\b", "Kitna"),
    (r"\bHow many\b", "Kitne"),
    (r"\bWhen\b", "Kab"),
    (r"\bWhere\b", "Kahan"),
    (r"\bWhy\b", "Kyun"),
    (r"\bWho\b", "Kaun"),

    # Time references
    (r"\btomorrow\b", "kal"),
    (r"\btoday\b", "aaj"),
    (r"\byesterday\b", "kal"),
    (r"\bnext week\b", "agli hafte"),
    (r"\bthis week\b", "is hafte"),
    (r"\bnext month\b", "agle mahine"),
    (r"\bthis month\b", "is mahine"),

    # Business terms (keep English where natural)
    (r"\bappointment\b", "appointment"),
    (r"\bmeeting\b", "meeting"),
    (r"\bcall\b", "call"),
    (r"\bcallback\b", "callback"),
    (r"\bdiscount\b", "discount"),
    (r"\boffer\b", "offer"),
    (r"\bplan\b", "plan"),
    (r"\bpackage\b", "package"),
    (r"\bprice\b", "price"),
    (r"\bcost\b", "cost"),
    (r"\bbudget\b", "budget"),
    (r"\blead\b", "lead"),
    (r"\bcustomer\b", "customer"),
    (r"\bclient\b", "client"),
    (r"\bservice\b", "service"),
    (r"\bproduct\b", "product"),
    (r"\bfeature\b", "feature"),
    (r"\bdemo\b", "demo"),
    (r"\btrial\b", "trial"),

    # Connectors & flow
    (r"\bhowever\b", "lekin"),
    (r"\bbut\b", "lekin"),
    (r"\band\b", "aur"),
    (r"\bor\b", "ya"),
    (r"\bso\b", "toh"),
    (r"\bbecause\b", "kyunki"),
    (r"\btherefore\b", "isliye"),
    (r"\bthen\b", "phir"),

    # Politeness markers
    (r"\bplease\b", ""),  # Often implied in Hindi
    (r"\bthank you\b", "shukriya"),
    (r"\bthanks\b", "shukriya"),
    (r"\bsorry\b", "maaf kijiye"),

    # Possessives
    (r"\byour\b", "aapka"),
    (r"\byour\b", "aapki"),
    (r"\byour\b", "aapke"),
    (r"\bmy\b", "mera"),
    (r"\bmy\b", "meri"),
    (r"\bmy\b", "mere"),
    (r"\bour\b", "hamara"),
    (r"\bour\b", "hamari"),
    (r"\bour\b", "hamare"),
]


# Common Hinglish sentence patterns for different styles
_STYLE_TEMPLATES = {
    "casual_conversational": {
        "opening": "{greeting}! {statement}",
        "question": "{question}?",
        "confirmation": "{confirmation}, {detail}",
    },
    "professional_business": {
        "opening": "{greeting}. {statement}",
        "question": "{question}?",
        "confirmation": "{confirmation}. {detail}",
    },
    "persuasive_sales": {
        "opening": "{greeting}! {hook}",
        "question": "{question}?",
        "confirmation": "{confirmation}! {value_prop}",
    },
    "empathetic_support": {
        "opening": "{greeting}. {empathy}",
        "question": "{question}?",
        "confirmation": "{confirmation}. {reassurance}",
    },
    "energetic_pitch": {
        "opening": "{greeting}! {energetic_hook}",
        "question": "{question}?",
        "confirmation": "{confirmation}! {benefit}",
    },
    "owner_briefing": {
        "opening": "Boss, {statement}",
        "question": "{question}?",
        "confirmation": "{confirmation}. {action_item}",
    },
}


# -----------------------------------------------------------------------------
# ADAPTATION ENGINE
# -----------------------------------------------------------------------------

class HinglishAdaptationEngine:
    """
    Converts OpenClaw English into natural Indian Hinglish for Swara.

    This is NOT literal translation — it's meaning-preserving adaptation
    optimized for conversational quality (Rule 5).
    """

    def __init__(self) -> None:
        self._patterns = _ENGLISH_TO_HINGLISH_PATTERNS
        self._templates = _STYLE_TEMPLATES
        self._custom_patterns: list[tuple[str, str]] = []
        self._lock = threading.RLock()

    def add_custom_pattern(self, pattern: str, replacement: str) -> None:
        """Add a custom adaptation pattern (e.g., from owner corrections)."""
        with self._lock:
            self._custom_patterns.append((pattern, replacement))

    def _apply_patterns(self, text: str, patterns: list[tuple[str, str]]) -> str:
        """Apply regex patterns to text."""
        result = text
        for pattern, replacement in patterns:
            try:
                result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
            except Exception as e:
                logger.debug(f"[hinglish_adapt] Pattern failed: {pattern} - {e}")
        return result

    def extract_meaning(self, english_text: str) -> str:
        """Stage 2: Extract core semantic meaning from English."""
        # For now, return cleaned English — in future could use LLM for semantic extraction
        return english_text.strip()

    def adapt_to_hinglish(self, meaning: str, style: HinglishStyle = "professional_business") -> str:
        """Stage 3: Adapt meaning to natural Hinglish."""
        # Apply base patterns
        result = self._apply_patterns(meaning, self._patterns)

        # Apply custom patterns (owner corrections, learned adaptations)
        with self._lock:
            result = self._apply_patterns(result, self._custom_patterns)

        # Apply style-specific adjustments
        if style == "casual_conversational":
            result = result.replace("Perfect", "Perfect").replace("Namaste", "Namaste!")
        elif style == "energetic_pitch":
            result = result.replace(".", "!").replace("?", "?")
        elif style == "owner_briefing":
            if not result.startswith("Boss"):
                result = f"Boss, {result}"

        return result

    def rewrite_for_persona(self, hinglish_text: str, style: HinglishStyle) -> str:
        """Stage 4: Rewrite in Swara persona — premium, professional, warm."""
        # Swara persona rules (Rule 1):
        # - premium feminine voice
        # - Indian conversational familiarity
        # - cinematic warmth
        # - confident but not aggressive
        # - intelligent, elegant
        # - energetic when selling
        # - empathetic during objections
        # - clear pronunciation
        # - pleasant pacing
        # - natural breathing and pauses

        result = hinglish_text

        # Ensure natural breathing pauses (commas for TTS)
        result = result.replace(" lekin ", ", lekin ")
        result = result.replace(" aur ", ", aur ")
        result = result.replace(" toh ", ", toh ")
        result = result.replace(" kyunki ", ", kyunki ")

        # Style-specific persona touches
        if style == "persuasive_sales":
            # Add confidence markers
            result = result.replace("Zaroor", "Zaroor, bilkul")
            result = result.replace("Kya aap", "Kya aap")
        elif style == "empathetic_support":
            # Add warmth markers
            result = result.replace("Main samajh", "Main poori tarah samajh")
        elif style == "owner_briefing":
            # Crisp, action-oriented
            result = result.replace("Main", "Maine")

        return result

    def normalize_pronunciation(self, text: str) -> str:
        """Stage 5: Normalize pronunciation using project dictionary."""
        from app.voice_agent.swara_pronunciation import normalize_text_with_pronunciation
        return normalize_text_with_pronunciation(text)

    def adapt(
        self,
        english_text: str,
        domain: str,
        context: str,
        style: HinglishStyle = "professional_business",
    ) -> AdaptationCandidate:
        """Run the full adaptation pipeline (stages 1-5)."""
        candidate = AdaptationCandidate(
            candidate_id=f"cand_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{abs(hash(english_text)) % 10000:04d}",
            english_text=english_text,
            domain=domain,
            context=context,
            target_style=style,
        )

        # Stage 2: Meaning extraction
        candidate.extracted_meaning = self.extract_meaning(english_text)
        candidate.current_stage = "meaning_extracted"

        # Stage 3: Hinglish adaptation
        candidate.hinglish_draft = self.adapt_to_hinglish(candidate.extracted_meaning, style)
        candidate.current_stage = "hinglish_adapted"

        # Stage 4: Persona rewrite
        candidate.persona_rewrite = self.rewrite_for_persona(candidate.hinglish_draft, style)
        candidate.current_stage = "persona_rewritten"

        # Stage 5: Pronunciation normalization
        candidate.pronunciation_normalized = self.normalize_pronunciation(candidate.persona_rewrite)
        candidate.current_stage = "pronunciation_normalized"

        candidate.updated_at = datetime.now(timezone.utc).isoformat()
        return candidate


# -----------------------------------------------------------------------------
# PIPELINE ORCHESTRATOR
# -----------------------------------------------------------------------------

class HinglishAdaptationPipeline:
    """
    Complete pipeline: English → Candidate → Evaluation → Golden Example.

    Coordinates:
    - HinglishAdaptationEngine (stages 1-5)
    - QualityEvaluator (stage 6) — in swara_eval.py
    - SafetyEvaluator (stage 7) — in swara_eval.py
    - GoldenUtteranceLibrary (stages 8-9)
    """

    def __init__(self) -> None:
        self.engine = HinglishAdaptationEngine()
        self._candidates: dict[str, AdaptationCandidate] = {}
        self._lock = threading.RLock()

    def create_candidate(
        self,
        english_text: str,
        domain: str,
        context: str,
        style: HinglishStyle = "professional_business",
    ) -> AdaptationCandidate:
        """Create and run adaptation for an English input (stages 1-5)."""
        if not hinglish_adaptation_enabled():
            logger.debug("[hinglish_pipeline] Adaptation disabled via flag")
            return AdaptationCandidate(
                candidate_id="disabled",
                english_text=english_text,
                domain=domain,
                context=context,
                target_style=style,
                current_stage="disabled",
            )

        candidate = self.engine.adapt(english_text, domain, context, style)

        with self._lock:
            self._candidates[candidate.candidate_id] = candidate

        logger.info(f"[hinglish_pipeline] Created candidate {candidate.candidate_id}: {english_text[:50]}...")
        return candidate

    def get_candidate(self, candidate_id: str) -> AdaptationCandidate | None:
        """Get a candidate by ID."""
        with self._lock:
            return self._candidates.get(candidate_id)

    def list_candidates(self, stage: AdaptationStage | None = None) -> list[AdaptationCandidate]:
        """List candidates, optionally filtered by stage."""
        with self._lock:
            candidates = list(self._candidates.values())
            if stage:
                candidates = [c for c in candidates if c.current_stage == stage]
            return candidates


# -----------------------------------------------------------------------------
# SINGLETON
# -----------------------------------------------------------------------------

_pipeline: HinglishAdaptationPipeline | None = None


def get_hinglish_pipeline() -> HinglishAdaptationPipeline:
    """Get the singleton adaptation pipeline."""
    global _pipeline
    if _pipeline is None:
        _pipeline = HinglishAdaptationPipeline()
    return _pipeline


# -----------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# -----------------------------------------------------------------------------

def adapt_english_to_swara(
    english_text: str,
    domain: str,
    context: str,
    style: HinglishStyle = "professional_business",
) -> AdaptationCandidate:
    """Convenience function: adapt English to Swara Hinglish (stages 1-5)."""
    return get_hinglish_pipeline().create_candidate(english_text, domain, context, style)


def adapt_openclaw_response(
    english_response: str,
    domain: str,
    context: str = "owner_communication",
) -> str:
    """Quick adaptation for OpenClaw owner-facing responses (Rule 3)."""
    candidate = adapt_english_to_swara(english_response, domain, context, "owner_briefing")
    return candidate.pronunciation_normalized or candidate.persona_rewrite or candidate.hinglish_draft or english_response


__all__ = [
    "AdaptationCandidate",
    "AdaptationStage",
    "HinglishStyle",
    "HinglishAdaptationEngine",
    "HinglishAdaptationPipeline",
    "get_hinglish_pipeline",
    "adapt_english_to_swara",
    "adapt_openclaw_response",
]