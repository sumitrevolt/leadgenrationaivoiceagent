"""
Answering Machine Detection (AMD) / Voicemail Detection
========================================================

Pata lagata hai ki call uthaane wala ek *insaan* hai ya *voicemail / answering
machine*. Yeh production voice agents (Retell / Vapi / Bland) ka core feature hai —
agar machine detect ho to bot ya to ek chhota voicemail chhod de, ya hangup kar de,
warna bot kisi recording se baat karta reh jaata hai (paise + leads waste).

Design goals:
  - PURE PYTHON, no external services, import-safe (no heavy deps).
  - Transcript-based heuristics (primary, fast, reliable) + optional audio-energy
    based best-effort detection using stdlib only.
  - Hinglish + English + Hindi voicemail phrases dono support.

Usage (text mode, no external services needed):
    from app.voice_agent.amd import AnsweringMachineDetector

    amd = AnsweringMachineDetector()
    result = amd.detect_from_transcript(
        "You have reached the voicemail of Raj. Please leave a message after the beep."
    )
    print(result.is_machine, result.confidence, result.reason, result.action)
    # True 0.9x voicemail_phrase leave_message

    if result.is_machine:
        action = amd.decide_action(result, leave_voicemail=True)
        if action == "leave_message":
            msg = amd.voicemail_message("SunPower", "+919876543210")
            # ...play/synthesize `msg` then hangup
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Result shape
# --------------------------------------------------------------------------- #
@dataclass
class AMDResult:
    """Answering-machine detection ka result.

    Attributes:
        is_machine:  True agar voicemail / answering machine detect hua.
        confidence:  0.0 - 1.0 (kitna pakka hai).
        reason:      short machine-readable reason string (logging / debug ke liye).
        action:      recommended action -> "leave_message" | "hangup" | "continue".
        matched:     jo phrases / signals match hue (debug ke liye).
    """

    is_machine: bool = False
    confidence: float = 0.0
    reason: str = "human"
    action: str = "continue"
    matched: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------- #
# Voicemail phrase banks (English + Hindi + Hinglish)
# --------------------------------------------------------------------------- #
# High-confidence: classic voicemail greetings — yeh dikhe to almost certainly machine.
_STRONG_PHRASES: list[str] = [
    "leave a message after the tone",
    "leave a message after the beep",
    "leave your message after the tone",
    "record your message after the tone",
    "please leave a message",
    "please record your message",
    "after the tone",
    "after the beep",
    "at the tone",
    "you have reached the voicemail",
    "you've reached the voicemail",
    "you have reached the voice mail",
    "the person you are calling is not available",
    "the number you have dialed is not available",
    "the person you have called is not available",
    "is not available right now",
    "is currently not available",
    "is unable to take your call",
    "cannot take your call right now",
    "unavailable to take your call",
    "please leave your name and number",
    "leave your name and number",
    "record your message",
    "this is the voicemail",
    "you have reached the answering machine",
    # Hindi / Hinglish
    "kripya message",
    "kripya apna sandesh",
    "apna message record",
    "sandesh record",
    "beep ke baad",
    "tone ke baad",
    "abhi available nahi",
    "available nahi hai",
    "uplabdh nahi hai",
    "switch off hai",
    "voicemail par",
    "sampark nahi ho",
]

# Medium-confidence signals — alone weak, combined ya repeated to machine likely.
_WEAK_PHRASES: list[str] = [
    "voicemail",
    "voice mail",
    "answering machine",
    "not available",
    "call back later",
    "we are sorry",
    "the number you are trying",
    "please try again later",
    "beep",
    "leave a message",
    "available nahi",
    "message chhod",
]

# Carrier / network auto-messages (call hi nahi lagi) -> hangup.
_CARRIER_PHRASES: list[str] = [
    "the number you have dialed is incorrect",
    "the number you are calling is not in service",
    "number does not exist",
    "call cannot be completed",
    "is switched off",
    "switch off hai",
    "is out of coverage area",
    "coverage area ke bahar",
    "incoming call facility",
    "do not exist",
]

# "beep" detection regex (transcripts me STT often [beep], (beep), *beep* deta hai)
_BEEP_RE = re.compile(r"[\(\[\*]?\s*bee+p+\s*[\)\]\*]?|<\s*tone\s*>", re.IGNORECASE)


class AnsweringMachineDetector:
    """Voicemail / answering-machine detector.

    Pure-python heuristics; koi external call nahi. Do tareeke:
      1. detect_from_transcript(text, timing_ms) — primary, fast, accurate.
      2. detect_from_audio_energy(samples)       — best-effort, optional/defensive.

    Phir decide_action() recommended action deta hai aur voicemail_message()
    ek natural chhota message banata hai chhodne ke liye.
    """

    def __init__(
        self,
        strong_phrases: Sequence[str] | None = None,
        weak_phrases: Sequence[str] | None = None,
        carrier_phrases: Sequence[str] | None = None,
        long_utterance_chars: int = 220,
        long_utterance_ms: int = 6500,
    ):
        self.strong_phrases = [p.lower() for p in (strong_phrases or _STRONG_PHRASES)]
        self.weak_phrases = [p.lower() for p in (weak_phrases or _WEAK_PHRASES)]
        self.carrier_phrases = [p.lower() for p in (carrier_phrases or _CARRIER_PHRASES)]
        # ek insaan ka pehla "hello" chhota hota hai; voicemail greeting lambi + bina ruke.
        self.long_utterance_chars = long_utterance_chars
        self.long_utterance_ms = long_utterance_ms

    # ----------------------- transcript-based ----------------------- #
    def detect_from_transcript(
        self,
        text: str,
        timing_ms: int | None = None,
    ) -> AMDResult:
        """Transcript (STT output) se voicemail detect karo.

        Args:
            text:       customer-side first utterance / greeting ka transcript.
            timing_ms:  (optional) us utterance ki duration ms me — lambi
                        uninterrupted speech machine ka strong signal hai.

        Returns:
            AMDResult — is_machine / confidence / reason / action.
        """
        raw = (text or "").strip()
        low = raw.lower()
        matched: list[str] = []

        if not low:
            # Khaali transcript — koi detection nahi, continue (human ho sakta hai).
            return AMDResult(False, 0.0, "empty_transcript", "continue")

        # 1) Carrier / network auto message -> call hi nahi lagi -> hangup.
        for p in self.carrier_phrases:
            if p in low:
                matched.append(p)
                logger.debug(f"AMD carrier message matched: {p!r}")
                return AMDResult(
                    is_machine=True,
                    confidence=0.95,
                    reason="carrier_message",
                    action="hangup",
                    matched=matched,
                )

        score = 0.0

        # 2) Strong voicemail phrases.
        strong_hits = [p for p in self.strong_phrases if p in low]
        if strong_hits:
            matched.extend(strong_hits)
            # ek strong phrase hi kaafi; multiple ho to aur pakka.
            score += 0.75 + 0.1 * min(len(strong_hits) - 1, 2)

        # 3) Weak phrases (cumulative).
        weak_hits = [p for p in self.weak_phrases if p in low]
        if weak_hits:
            matched.extend(weak_hits)
            score += 0.18 * min(len(weak_hits), 3)

        # 4) "beep"/tone marker.
        if _BEEP_RE.search(raw):
            matched.append("beep_marker")
            score += 0.5

        # 5) Long uninterrupted first utterance (machine greetings lambi hoti hain).
        if len(low) >= self.long_utterance_chars:
            matched.append("long_utterance_chars")
            score += 0.2
        if timing_ms is not None and timing_ms >= self.long_utterance_ms:
            matched.append("long_utterance_ms")
            score += 0.2

        score = max(0.0, min(1.0, score))
        is_machine = score >= 0.6

        if is_machine:
            reason = "voicemail_phrase" if strong_hits else "voicemail_signals"
            action = "leave_message"
        else:
            reason = "human"
            action = "continue"

        result = AMDResult(
            is_machine=is_machine,
            confidence=round(score, 3),
            reason=reason,
            action=action,
            matched=matched,
        )
        if is_machine:
            logger.info(
                f"📼 AMD: machine detected (conf={result.confidence}, "
                f"reason={reason}, signals={matched})"
            )
        return result

    # ----------------------- audio-energy based ----------------------- #
    def detect_from_audio_energy(
        self,
        samples: Sequence[float] | bytes,
        sample_rate: int = 16000,
        frame_ms: int = 30,
    ) -> AMDResult:
        """Best-effort AMD raw audio se, sirf stdlib (RMS) se.

        Idea: voicemail greeting = lambi *continuous* speech (kam pauses) jiske
        baad ek choti tez energy spike (the "beep"). Insaan ka "hello?" chhota
        hota hai uske baad silence (woh aapke bolne ka wait karta hai).

        Yeh DEFENSIVE / optional hai — agar samples na milein ya parse na ho,
        to safe "continue" (human assume) return karta hai, kabhi crash nahi.

        Args:
            samples:      int16 PCM `bytes` YA float/int samples ka sequence.
            sample_rate:  Hz (default 16000).
            frame_ms:     analysis frame size ms me.

        Returns:
            AMDResult (heuristic).
        """
        try:
            vals = self._to_float_samples(samples)
            if not vals:
                return AMDResult(False, 0.0, "no_audio", "continue")

            frame_len = max(1, int(sample_rate * frame_ms / 1000))
            frames: list[float] = []
            for i in range(0, len(vals), frame_len):
                chunk = vals[i : i + frame_len]
                if chunk:
                    frames.append(self._rms(chunk))
            if not frames:
                return AMDResult(False, 0.0, "no_frames", "continue")

            peak = max(frames) or 1e-9
            thresh = peak * 0.25  # speech vs silence cutoff
            voiced = [f >= thresh for f in frames]
            voiced_ratio = sum(voiced) / len(voiced)

            # longest continuous voiced run (frames -> ms)
            longest_run = cur = 0
            for v in voiced:
                cur = cur + 1 if v else 0
                longest_run = max(longest_run, cur)
            longest_ms = longest_run * frame_ms

            # trailing beep: aakhri ~10% frames me ek sharp high-energy spike,
            # aur usse pehle thodi shaant region.
            tail_n = max(1, len(frames) // 10)
            tail = frames[-tail_n:]
            pre_tail = frames[:-tail_n] or [0.0]
            beep_like = (max(tail) >= peak * 0.8) and (
                (sum(tail) / len(tail)) > 1.5 * (sum(pre_tail) / len(pre_tail))
            )

            matched: list[str] = []
            score = 0.0
            # continuous speech (kam pauses) = machine signal
            if voiced_ratio >= 0.7 and longest_ms >= self.long_utterance_ms:
                matched.append("continuous_speech")
                score += 0.45
            elif voiced_ratio >= 0.6:
                matched.append("mostly_voiced")
                score += 0.2
            if beep_like:
                matched.append("trailing_beep")
                score += 0.4

            score = max(0.0, min(1.0, score))
            is_machine = score >= 0.6
            return AMDResult(
                is_machine=is_machine,
                confidence=round(score, 3),
                reason="audio_energy" if is_machine else "human",
                action="leave_message" if is_machine else "continue",
                matched=matched,
            )
        except Exception as e:  # pragma: no cover - defensive
            logger.debug(f"detect_from_audio_energy fallback: {e}")
            return AMDResult(False, 0.0, "audio_error", "continue")

    # ----------------------- action decision ----------------------- #
    def decide_action(self, result: AMDResult, leave_voicemail: bool = True) -> str:
        """AMDResult ko final action me convert karo.

        Args:
            result:           detect_from_*() ka output.
            leave_voicemail:  agar machine mile to message chhodna hai? (False ->
                              seedha hangup, e.g. compliance / cost bachane ke liye).

        Returns:
            "leave_message" | "hangup" | "continue"
        """
        if not result.is_machine:
            return "continue"
        # carrier / network message par message chhodne ka koi fayda nahi.
        if result.reason == "carrier_message" or result.action == "hangup":
            return "hangup"
        return "leave_message" if leave_voicemail else "hangup"

    # ----------------------- voicemail script ----------------------- #
    def voicemail_message(
        self,
        client_name: str,
        callback_number: str | None = None,
        agent_name: str = "Riya",
        lang: str = "hinglish",
    ) -> str:
        """Voicemail par chhodne ke liye ek chhota, natural message banao.

        Pure python — koi LLM/external call nahi. Phone-friendly: chhota,
        clear, ek call-to-action + callback number.

        Args:
            client_name:      jis company ke liye call kar rahe hain.
            callback_number:  callback number (optional).
            agent_name:       agent ka naam.
            lang:             "hinglish" | "hi" | "en".

        Returns:
            Voicemail script string.
        """
        cb = ""
        if callback_number:
            cb = {
                "en": f" You can reach us back at {callback_number}.",
                "hi": f" Aap humein {callback_number} par call kar sakte hain.",
                "hinglish": f" Aap humein {callback_number} par callback kar sakte hain.",
            }.get(lang, f" Callback number: {callback_number}.")

        if lang == "en":
            return (
                f"Hi, this is {agent_name} calling from {client_name}. "
                f"Sorry I missed you — I had a quick idea that could bring you more "
                f"qualified leads. Please give us a call back when you get a moment.{cb} "
                f"Thank you, have a great day!"
            ).strip()
        if lang == "hi":
            return (
                f"Namaste, main {agent_name}, {client_name} se baat kar rahi hoon. "
                f"Aapse baat nahi ho payi — humare paas aapke business ke liye ek "
                f"acchi idea thi jo aapko zyada qualified leads de sakti hai. "
                f"Time mile to ek call kar dijiyega.{cb} Dhanyavaad, aapka din accha rahe!"
            ).strip()
        # default: hinglish
        return (
            f"Namaste, main {agent_name} {client_name} se. "
            f"Aapse baat nahi ho payi — ek chhoti si baat thi jo aapke business ke "
            f"liye zyada qualified leads la sakti hai. Jab time mile, ek callback "
            f"de dijiyega.{cb} Shukriya, aapka din accha rahe!"
        ).strip()

    # ----------------------- internal helpers ----------------------- #
    @staticmethod
    def _to_float_samples(samples: Sequence[float] | bytes) -> list[float]:
        """int16 PCM bytes ya numeric sequence ko float list me convert karo."""
        if isinstance(samples, (bytes, bytearray)):
            import array

            arr = array.array("h")  # signed short (int16)
            # even length tak hi parse karo (last odd byte drop)
            n = len(samples) - (len(samples) % 2)
            arr.frombytes(bytes(samples[:n]))
            return [float(x) for x in arr]
        try:
            return [float(x) for x in samples]
        except Exception:
            return []

    @staticmethod
    def _rms(chunk: Sequence[float]) -> float:
        if not chunk:
            return 0.0
        return math.sqrt(sum(x * x for x in chunk) / len(chunk))


__all__ = ["AnsweringMachineDetector", "AMDResult"]
