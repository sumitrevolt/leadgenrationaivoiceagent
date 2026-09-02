"""
Agent Evaluation / Simulation Suite
===================================

Live jaane se PEHLE edge-case customers ko SIMULATE karo (jaise Bland / Vapi
ke "test personas" / Braintrust evals). Har persona ek scripted-but-varied
customer hai jo bot ke jawab ke hisaab se apni agli line deta hai. Suite poori
conversation drive karti hai aur check karti hai ki bot ne sahi outcome diya ya
nahi (qualified / not_interested / voicemail / callback...).

Yeh module `NaturalDialogManager` ko *as-is* use karta hai (edit nahi karta) —
`new_conversation()` + `async respond(text, state)` loop chalata hai.

Run (no keys / no external services — brain=None rule-based):
    python -m app.voice_agent.eval_suite
or import:
    from app.voice_agent.eval_suite import run_suite, PERSONAS
    report = await run_suite(lambda: NaturalDialogManager(niche="solar", brain=None))
    print(report.pass_rate)
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

try:  # D-13 conversation QA judges (pure, import-safe) — reused in criteria.
    from app.voice_agent import qa_checks as _qc
except Exception:  # pragma: no cover
    _qc = None  # type: ignore[assignment]


# --------------------------------------------------------------------------- #
# Persona definition
# --------------------------------------------------------------------------- #
@dataclass
class Persona:
    """
    Ek simulated customer.

    next_line(bot_text, turn) -> str:  bot ke last reply (aur turn no.) ke hisaab
        se customer ki agli line deta hai. Empty string return kare to customer
        ne phone "rakh diya" (conversation end) maana jayega.
    success_criteria(run) -> (passed: bool, note: str):  EvalRun ko dekh ke decide
        karta hai ki test pass hua ya nahi.
    """

    name: str
    opening: str
    next_line: Callable[[str, int], str]
    expected_outcome: str
    success_criteria: Callable[[EvalRun], Any]
    description: str = ""


@dataclass
class EvalRun:
    persona: str
    transcript: list[dict[str, str]] = field(default_factory=list)  # {role, content}
    outcome: str | None = None
    passed: bool = False
    score: float = 0.0
    notes: list[str] = field(default_factory=list)
    turns: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "persona": self.persona,
            "transcript": list(self.transcript),
            "outcome": self.outcome,
            "passed": self.passed,
            "score": round(self.score, 3),
            "notes": list(self.notes),
            "turns": self.turns,
        }


@dataclass
class EvalReport:
    runs: list[EvalRun] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    by_persona: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "runs": [r.to_dict() for r in self.runs],
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 3),
            "by_persona": dict(self.by_persona),
        }


# --------------------------------------------------------------------------- #
# Helpers for criteria
# --------------------------------------------------------------------------- #
def _bot_said_goodbye_politely(run: EvalRun) -> bool:
    """Last bot line me polite close-words hon (thanks / shukriya / din accha)."""
    bot_lines = [t["content"].lower() for t in run.transcript if t["role"] == "assistant"]
    if not bot_lines:
        return False
    last = bot_lines[-1]
    polite = ["shukriya", "thank", "din accha", "din acha", "time", "dhanyawad", "aabhar"]
    return any(p in last for p in polite)


def _never_pushy(run: EvalRun, max_followups: int = 3) -> bool:
    """Bot ne 'naa' ke baad hadd se zyada baar push to nahi kiya."""
    return run.turns <= 14


# --------------------------------------------------------------------------- #
# Built-in personas — rule-based "agar bot ne X bola to main Y bolunga"
# --------------------------------------------------------------------------- #
def _interested_next(bot_text: str, turn: int) -> str:
    bl = (bot_text or "").lower()
    if turn == 0:
        return "Haan boliye, kya kaam hai?"
    if "demo" in bl or "kal" in bl or "time" in bl or "sham" in bl:
        return "Haan bilkul, kal sham theek rahega. Book kar do."
    if "?" in bl:
        return "Haan, main hi decision leta hoon. Aur batao."
    return "Sahi hai, mujhe interest hai. Aage badho."


def _busy_rude_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Yaar main bahut busy hoon abhi, jaldi bolo!"
    if turn == 1:
        return "Time nahi hai mere paas, baad me call karo."
    return "Bola na busy hoon! Rakhta hoon phone."


def _confused_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Kaun bol raha hai? Mujhe samajh nahi aaya."
    if turn == 1:
        return "Matlab kya? Ye kya cheez hai?"
    if turn == 2:
        return "Achha achha, ab thoda samajh aaya. Aur batao kaise help karoge?"
    return "Theek hai, samajh gaya. Aage boliye."


def _price_objector_next(bot_text: str, turn: int) -> str:
    bl = (bot_text or "").lower()
    if turn == 0:
        return "Ye sab kaafi mehenga hota hai na? Budget nahi hai."
    if "lead" in bl or "result" in bl or "₹" in bot_text or "qualified" in bl:
        return "Achha, sirf result ke paise? Toh thoda interest hai. Aage batao."
    if turn >= 2:
        return "Haan theek hai, ek demo dekh leta hoon."
    return "Phir bhi mehenga lagta hai mujhe."


def _voicemail_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return (
            "Aap jis vyakti ko call kar rahe hain woh abhi uplabdh nahi hai. "
            "Kripya beep ke baad apna sandesh record karein."
        )
    return ""  # machine doesn't talk back


def _not_interested_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Nahi bhai, mujhe interest nahi hai."
    if turn == 1:
        return "Nahi chahiye, please remove my number."
    return "Bilkul nahi chahiye."


def _language_switcher_next(bot_text: str, turn: int) -> str:
    # Customer Hindi me reply karta hai throughout (language match test).
    if turn == 0:
        return "Haan ji boliye, kaun bol raha hai?"
    if turn == 1:
        return "Achha, toh aap kya seva dete hain? Mujhe Hindi me batayein."
    if turn == 2:
        return "Theek hai ji, mujhe ruchi hai. Aage batayein."
    if turn == 3:
        return "Haan ji, demo ke liye kal shaam theek rahega."
    return "Dhanyawad, book kar dijiye."


PERSONAS: list[Persona] = [
    Persona(
        name="interested_buyer",
        description="Keen decision-maker — demo book karna chahta hai.",
        opening="Haan boliye, kya kaam hai?",
        next_line=_interested_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            (
                run.outcome == "qualified"
                or any(
                    w in (run.transcript[-1]["content"].lower() if run.transcript else "")
                    for w in ["demo", "book", "perfect", "badhiya"]
                ),
                "interested buyer ko qualify/demo tak pahunchna chahiye",
            )
        ),
    ),
    Persona(
        name="busy_rude",
        description="Irritated, jaldi me — phone rakh dega.",
        opening="Yaar main bahut busy hoon abhi, jaldi bolo!",
        next_line=_busy_rude_next,
        expected_outcome="callback",
        success_criteria=lambda run: (
            (
                run.outcome in ("callback", "ended", "not_interested") or run.turns <= 8,
                "busy customer ka time respect ho — callback/short close",
            )
        ),
    ),
    Persona(
        name="confused",
        description="Pehle confused, phir samajh ke aage badhta hai.",
        opening="Kaun bol raha hai? Mujhe samajh nahi aaya.",
        next_line=_confused_next,
        expected_outcome="ended",
        success_criteria=lambda run: (
            (
                any(
                    "?" in t["content"] or "main" in t["content"].lower()
                    for t in run.transcript
                    if t["role"] == "assistant"
                ),
                "confused customer ko bot ne explain/clarify kiya hona chahiye",
            )
        ),
    ),
    Persona(
        name="price_objector",
        description="Pehle mehenga bolta hai, value sun ke convince hota hai.",
        opening="Ye sab kaafi mehenga hota hai na? Budget nahi hai.",
        next_line=_price_objector_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            (
                any(
                    w
                    in " ".join(
                        t["content"].lower() for t in run.transcript if t["role"] == "assistant"
                    )
                    for w in ["lead", "result", "demo", "qualified"]
                ),
                "price objection pe bot ne value (per-lead/result) samjhana chahiye",
            )
        ),
    ),
    Persona(
        name="voicemail",
        description="Answering machine / voicemail uthata hai.",
        opening=(
            "Aap jis vyakti ko call kar rahe hain woh abhi uplabdh nahi hai. "
            "Kripya beep ke baad apna sandesh record karein."
        ),
        next_line=_voicemail_next,
        expected_outcome="voicemail",
        success_criteria=lambda run: (
            (
                run.outcome in ("voicemail", "callback", "ended"),
                "voicemail detect ho ya gracefully end ho (machine se baat na karta rahe)",
            )
        ),
    ),
    Persona(
        name="not_interested",
        description="Saaf mana karta hai — politely close hona chahiye.",
        opening="Nahi bhai, mujhe interest nahi hai.",
        next_line=_not_interested_next,
        expected_outcome="not_interested",
        success_criteria=lambda run: (
            (
                run.outcome == "not_interested" and _bot_said_goodbye_politely(run),
                "not_interested -> politely close (thanks/shukriya), pushy nahi",
            )
        ),
    ),
    Persona(
        name="language_switcher",
        description="Customer poori call Hindi me karta hai (language match test).",
        opening="Haan ji boliye, kaun bol raha hai?",
        next_line=_language_switcher_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            (
                run.turns >= 3
                and not any(
                    "i cannot" in t["content"].lower() or "as an ai" in t["content"].lower()
                    for t in run.transcript
                    if t["role"] == "assistant"
                ),
                "Hindi customer ke saath bot natural chala (robotic/refusal nahi)",
            )
        ),
    ),
]


# --------------------------------------------------------------------------- #
# EXTENDED personas (D-13 / P4) — the India failure-modes that drive D-8/D-10.
# Kept SEPARATE from the default PERSONAS so the baseline suite contract stays
# stable; these are ASPIRATIONAL (some FAIL against today's rule-based bot — that
# is the signal). Opt in: run_suite(factory, personas=PERSONAS + EXTENDED_PERSONAS).
# --------------------------------------------------------------------------- #
def _bot_turns_text(run: EvalRun) -> str:
    return " ".join(t["content"].lower() for t in run.transcript if t["role"] == "assistant")


def _no_refusal(run: EvalRun) -> bool:
    txt = _bot_turns_text(run)
    return not any(m in txt for m in ("as an ai", "i cannot", "i can't", "language model"))


def _polite_no_next(bot_text: str, turn: int) -> str:
    # Escalating soft-no's — a good bot stops pitching after the 2nd.
    seq = [
        "Haan boliye?",
        "Achha... dekhte hain baad me.",
        "Abhi nahi, time nahi hai.",
        "Nahi bhai, zarurat nahi hai abhi.",
    ]
    return seq[turn] if turn < len(seq) else ""


def _whatsapp_brushoff_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Haan, WhatsApp pe bhej do na details."
    if turn == 1:
        return "Bas WhatsApp pe bhej do, baad me dekh lunga."
    return ""


def _incumbent_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Hum already ek dusri company se marketing karwa rahe hain."
    if turn == 1:
        return "Wo theek chal raha hai, aap kya alag dete ho?"
    if turn == 2:
        return "Achha, thoda interest hai. Aur batao."
    return "Theek hai, demo dekh lunga."


def _formal_hindi_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Namaskar, kripya bataiye aap kaun bol rahe hain?"
    if turn == 1:
        return "Aap kaun si seva pradan karte hain? Vistaar se bataiye."
    if turn == 2:
        return "Achha, mujhe ruchi hai. Aage kahiye."
    return "Theek hai, demo nirdharit kar dijiye."


def _english_dominant_next(bot_text: str, turn: int) -> str:
    if turn == 0:
        return "Yeah hi, who is this? What is this regarding?"
    if turn == 1:
        return "Okay so what exactly do you guys do?"
    if turn == 2:
        return "Hmm interesting, tell me more about pricing."
    return "Alright, let's set up a demo then."


EXTENDED_PERSONAS: list[Persona] = [
    Persona(
        name="polite_no_indian",
        description="2+ soft refusals — bot ko 2nd soft-no ke baad push BAND karna hai.",
        opening="Haan boliye?",
        next_line=_polite_no_next,
        expected_outcome="not_interested",
        success_criteria=lambda run: (
            (not _qc.check_pushy_after_softno(run.transcript)) if _qc else (run.turns <= 8),
            "2nd soft-no ke baad bot ne push nahi karna chahiye (India: rude + trust-tod)",
        ),
    ),
    Persona(
        name="whatsapp_brushoff",
        description="'WhatsApp pe bhej do' brush-off — bot ko qualify-before-send karna hai.",
        opening="Haan, WhatsApp pe bhej do na details.",
        next_line=_whatsapp_brushoff_next,
        expected_outcome="callback",
        success_criteria=lambda run: (
            any("?" in t["content"] for t in run.transcript if t["role"] == "assistant"),
            "WhatsApp brush-off pe bot ko kam se kam 1 qualifying sawal puchna chahiye",
        ),
    ),
    Persona(
        name="incumbent_user",
        description="Already dusri company use karta — bot ko incumbent trash NAHI karna.",
        opening="Hum already ek dusri company se marketing karwa rahe hain.",
        next_line=_incumbent_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            not any(
                w in _bot_turns_text(run) for w in ("bekaar", "ghatiya", "faltu", "worst", "bakwas")
            )
            and any("?" in t["content"] for t in run.transcript if t["role"] == "assistant"),
            "incumbent ko gaali nahi (agree-explore-reframe), aur ek sawal se explore",
        ),
    ),
    Persona(
        name="formal_hindi_speaker",
        description="Shuddh formal Hindi — bot natural register mirror kare, robotic nahi.",
        opening="Namaskar, kripya bataiye aap kaun bol rahe hain?",
        next_line=_formal_hindi_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            _no_refusal(run)
            and (
                not any(
                    _qc.check_literal_translation(t["content"])
                    for t in run.transcript
                    if t["role"] == "assistant"
                )
                if _qc
                else True
            ),
            "formal Hindi pe bot natural (no refusal, no robotic translationese)",
        ),
    ),
    Persona(
        name="english_dominant",
        description="English-heavy caller — bot ko Hindi-only force NAHI karna, engage kare.",
        opening="Yeah hi, who is this? What is this regarding?",
        next_line=_english_dominant_next,
        expected_outcome="qualified",
        success_criteria=lambda run: (
            _no_refusal(run) and run.turns >= 2,
            "English caller ke saath bot engage kare (Hindi-only force / refusal nahi)",
        ),
    ),
]


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #
def _coerce_criteria(result: Any) -> (bool, str):
    """success_criteria ke return ko (passed, note) me normalize karo."""
    if isinstance(result, tuple) and len(result) == 2:
        return bool(result[0]), str(result[1])
    return bool(result), ""


async def run_persona(manager: Any, persona: Persona, max_turns: int = 12) -> EvalRun:
    """
    Ek persona ke saath poori conversation chalao aur evaluate karo.
    `manager` ek NaturalDialogManager instance hona chahiye (fresh, isolated).
    """
    run = EvalRun(persona=persona.name)
    try:
        state = manager.new_conversation()
    except Exception as e:
        run.notes.append(f"manager.new_conversation() fail: {e!r}")
        run.passed = False
        return run

    customer_line = persona.opening
    bot_text = ""
    for turn in range(max_turns):
        if turn > 0:
            customer_line = persona.next_line(bot_text, turn)
        if not customer_line:  # customer hung up / machine silent
            run.notes.append(f"customer ended at turn {turn}")
            break

        run.transcript.append({"role": "user", "content": customer_line})
        try:
            reply = await manager.respond(customer_line, state)
        except Exception as e:
            run.notes.append(f"respond() crashed at turn {turn}: {e!r}")
            run.passed = False
            run.turns = turn + 1
            return run

        bot_text = getattr(reply, "text", "") or ""
        run.transcript.append({"role": "assistant", "content": bot_text})
        run.turns = turn + 1

        # outcome track (latest non-None wins)
        out = getattr(reply, "outcome", None)
        if out:
            run.outcome = out
        if getattr(reply, "should_end", False) or getattr(state, "finished", False):
            if not run.outcome:
                run.outcome = getattr(state, "outcome", None)
            break

    if not run.outcome:
        run.outcome = getattr(state, "outcome", None) or "ended"

    # evaluate success criteria (crash-safe)
    try:
        passed, note = _coerce_criteria(persona.success_criteria(run))
    except Exception as e:
        passed, note = False, f"criteria error: {e!r}"
    run.passed = passed
    if note:
        run.notes.append(note)
    run.score = 1.0 if passed else 0.0
    # bonus: did final outcome match expected?
    if run.outcome == persona.expected_outcome:
        run.notes.append(f"outcome matched expected ({persona.expected_outcome})")
    else:
        run.notes.append(f"outcome={run.outcome} expected={persona.expected_outcome}")
    return run


async def run_suite(
    manager_factory: Callable[[], Any],
    personas: list[Persona] | None = None,
    max_turns: int = 12,
) -> EvalReport:
    """
    Saare personas chalao — har ek ke liye FRESH manager (isolation).
    `manager_factory()` ek naya NaturalDialogManager return kare.
    """
    personas = personas if personas is not None else PERSONAS
    report = EvalReport()
    for persona in personas:
        try:
            manager = manager_factory()
        except Exception as e:
            run = EvalRun(
                persona=persona.name, passed=False, notes=[f"manager_factory() fail: {e!r}"]
            )
            report.runs.append(run)
            report.by_persona[persona.name] = False
            continue
        run = await run_persona(manager, persona, max_turns=max_turns)
        report.runs.append(run)
        report.by_persona[persona.name] = run.passed

    report.passed = sum(1 for r in report.runs if r.passed)
    report.failed = len(report.runs) - report.passed
    report.pass_rate = (report.passed / len(report.runs)) if report.runs else 0.0
    return report


# --------------------------------------------------------------------------- #
# Demo / CLI
# --------------------------------------------------------------------------- #
async def demo() -> EvalReport:
    """No-keys run: rule-based manager (brain=None) ke saath poori suite."""
    try:
        from app.voice_agent.natural_dialog import NaturalDialogManager
    except Exception as e:  # pragma: no cover
        logger.error(f"NaturalDialogManager import fail: {e}")
        raise

    def factory():
        return NaturalDialogManager(niche="solar", brain=None)

    report = await run_suite(factory)

    # pretty print
    print("=" * 64)
    print(" AGENT EVAL SUITE — solar / rule-based (brain=None)")
    print("=" * 64)
    for run in report.runs:
        status = "PASS" if run.passed else "FAIL"
        print(
            f"[{status}] {run.persona:<18} outcome={run.outcome!s:<14} "
            f"turns={run.turns} score={run.score}"
        )
        for note in run.notes:
            print(f"        - {note}")
    print("-" * 64)
    print(f" passed={report.passed}  failed={report.failed}  pass_rate={report.pass_rate:.0%}")
    print("=" * 64)
    return report


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(demo())


__all__ = [
    "Persona",
    "EvalRun",
    "EvalReport",
    "PERSONAS",
    "EXTENDED_PERSONAS",
    "run_persona",
    "run_suite",
    "demo",
]
