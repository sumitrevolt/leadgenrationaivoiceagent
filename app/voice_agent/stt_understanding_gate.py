"""Deterministic pre-LLM STT understanding gate (enterprise conversation upgrade).

Classifies transcript quality BEFORE sales state / pricing / tools / opener advance.
Junk must NOT reach the LLM as a meaningful sales turn — clarify or soft-drop.

Gated ``STT_UNDERSTANDING_GATE`` (default ON). Fail-open on error (caller continues).
Metrics counters are in-process (exported via ``snapshot_metrics`` / call session).
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

CLARIFY_LINE = (
    "Maaf kijiye, awaaz clear nahi aayi. Aap ek baar phir bolenge?"
)

# Whisper noise loops seen in live batches (roman + Devanagari variants).
_JUNK_PHRASES = (
    "aam shabd",
    "aam shabdh",
    "आम शब्द",
    "subtitles by",
    "thank you for watching",
    "thanks for watching",
    "subscribe",
    "music",
    "[music]",
    "(music)",
    "silence",
    "inaudible",
    "...",
)

_FILLERS_ONLY = re.compile(
    r"^(?:uh+|um+|ah+|hmm+|haan+|ha+|ji+|ok+|okay+|achha+|acha+|theek+|thik+|"
    r"yes+|no+|na+|nahi+|mm+|mhm+)(?:\s+(?:uh+|um+|ah+|hmm+|haan+|ji+|ok+|okay+))*$",
    re.IGNORECASE,
)

_OPT_OUT = re.compile(
    r"(?:call\s*mat|mat\s*call|do\s*not\s*call|don't\s*call|number\s*hata|"
    r"unsubscribe|opt[\s-]?out|list\s*se\s*hata|band\s*karo\s*call|"
    r"कॉल\s*मत|नंबर\s*हटा)",
    re.IGNORECASE,
)

_REJECTION = re.compile(
    r"(?:nahi\s*chahiye|interest\s*nahi|busy\s*hoon|abhi\s*nahi|mat\s*bolo|"
    r"not\s*interested|no\s*thanks|रहने\s*दो|नहीं\s*चाहिए)",
    re.IGNORECASE,
)

_CONFIRM = re.compile(
    r"^(?:haan|han|ha|ji|yes|ok|okay|theek|thik|sahi|chalega|pakka|done|"
    r"हां|जी|ठीक)[\s!.]*$",
    re.IGNORECASE,
)


class SttClass(str, Enum):
    VALID_MEANINGFUL = "valid_meaningful"
    VALID_SHORT_CONFIRMATION = "valid_short_confirmation"
    VALID_REJECTION = "valid_rejection"
    VALID_OPT_OUT = "valid_opt_out"
    LOW_CONFIDENCE = "low_confidence"
    NOISE = "noise"
    DUPLICATE = "duplicate"
    INCOMPLETE = "incomplete"
    LANGUAGE_UNCERTAIN = "language_uncertain"


@dataclass
class SttGateResult:
    cls: SttClass
    text: str
    allow_llm: bool
    advance_sales: bool
    clarify: bool
    reason: str = ""


@dataclass
class SttGateMetrics:
    stt_low_confidence_count: int = 0
    stt_noise_count: int = 0
    stt_duplicate_count: int = 0
    stt_clarification_count: int = 0
    stt_failure_close_count: int = 0
    clarify_streak: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "stt_low_confidence_count": self.stt_low_confidence_count,
            "stt_noise_count": self.stt_noise_count,
            "stt_duplicate_count": self.stt_duplicate_count,
            "stt_clarification_count": self.stt_clarification_count,
            "stt_failure_close_count": self.stt_failure_close_count,
            "clarify_streak": self.clarify_streak,
        }


def enabled() -> bool:
    return (os.environ.get("STT_UNDERSTANDING_GATE", "1") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def max_clarify_loops() -> int:
    try:
        return max(1, min(int(os.environ.get("STT_CLARIFY_MAX", "2") or "2"), 5))
    except Exception:
        return 2


def classify(
    text: str,
    *,
    last_user: str = "",
    confidence: float | None = None,
    energy_rms: int | None = None,
    vad_threshold: int | None = None,
) -> SttGateResult:
    """Classify one STT transcript. Never raises."""
    try:
        t = (text or "").strip()
        if not t:
            return SttGateResult(
                SttClass.NOISE, "", False, False, False, "empty"
            )

        low = t.lower()
        if _OPT_OUT.search(t):
            return SttGateResult(
                SttClass.VALID_OPT_OUT, t, False, False, False, "opt_out"
            )
        if _REJECTION.search(t) and len(t.split()) <= 8:
            return SttGateResult(
                SttClass.VALID_REJECTION, t, True, False, False, "rejection"
            )

        last = (last_user or "").strip()
        if last and t == last:
            return SttGateResult(
                SttClass.DUPLICATE, t, False, False, False, "exact_dup"
            )

        # Known Whisper junk loops ("Aam shabd" x N).
        for phrase in _JUNK_PHRASES:
            if phrase in low and len(set(re.findall(r"\w+", low))) <= 3:
                return SttGateResult(
                    SttClass.NOISE, t, False, False, True, f"junk:{phrase}"
                )

        toks = re.findall(r"[0-9A-Za-zऀ-ॿ']+", low)
        if len(toks) >= 4 and (len(set(toks)) / max(len(toks), 1)) <= 0.4:
            return SttGateResult(
                SttClass.NOISE, t, False, False, True, "repeat_loop"
            )

        if len(t) < 3 or re.search(r"[0-9A-Za-zऀ-ॿ]", t) is None:
            return SttGateResult(
                SttClass.NOISE, t, False, False, False, "too_short"
            )

        if confidence is not None and confidence < 0.35:
            return SttGateResult(
                SttClass.LOW_CONFIDENCE, t, False, False, True, "low_conf"
            )

        if (
            energy_rms is not None
            and vad_threshold is not None
            and energy_rms < max(1, int(vad_threshold * 0.5))
        ):
            return SttGateResult(
                SttClass.LOW_CONFIDENCE, t, False, False, True, "low_energy"
            )

        if _CONFIRM.match(t):
            return SttGateResult(
                SttClass.VALID_SHORT_CONFIRMATION, t, True, True, False, "ack"
            )

        if _FILLERS_ONLY.match(t) and len(toks) <= 3:
            return SttGateResult(
                SttClass.INCOMPLETE, t, False, False, True, "filler_only"
            )

        # Truncated mid-word / trailing ellipsis without content.
        if t.endswith("...") and len(toks) <= 2:
            return SttGateResult(
                SttClass.INCOMPLETE, t, False, False, True, "incomplete"
            )

        # Mostly Latin gibberish with no Hindi/business cues and very short.
        if len(toks) == 1 and len(toks[0]) <= 2:
            return SttGateResult(
                SttClass.INCOMPLETE, t, False, False, True, "tiny_token"
            )

        return SttGateResult(
            SttClass.VALID_MEANINGFUL, t, True, True, False, "ok"
        )
    except Exception as e:
        logger.debug("[stt_gate] classify fail-open: %s", e)
        return SttGateResult(
            SttClass.VALID_MEANINGFUL, (text or "").strip(), True, True, False, "fail_open"
        )


def apply_metrics(metrics: SttGateMetrics, result: SttGateResult) -> SttGateMetrics:
    """Mutate metrics from a classify result. Returns same object."""
    if result.cls == SttClass.LOW_CONFIDENCE:
        metrics.stt_low_confidence_count += 1
    if result.cls in (SttClass.NOISE, SttClass.INCOMPLETE):
        metrics.stt_noise_count += 1
    if result.cls == SttClass.DUPLICATE:
        metrics.stt_duplicate_count += 1
    if result.clarify:
        metrics.stt_clarification_count += 1
        metrics.clarify_streak += 1
    else:
        if result.allow_llm:
            metrics.clarify_streak = 0
    return metrics


def should_failure_close(metrics: SttGateMetrics) -> bool:
    return metrics.clarify_streak >= max_clarify_loops()


def failure_close_line() -> str:
    return (
        "Theek hai, line clear nahi aa rahi. Main baad me callback karungi — "
        "dhanyavaad, aapka din shubh ho."
    )


def gate_snapshot(extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": enabled(),
        "clarify_max": max_clarify_loops(),
        "clarify_line": CLARIFY_LINE,
    }
    if extra:
        out.update(extra)
    return out
