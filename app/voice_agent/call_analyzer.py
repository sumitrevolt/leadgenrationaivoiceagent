"""
Post-Call Analyzer
==================

Call khatam hone ke baad poori conversation ko analyze karta hai aur ek structured
`CallAnalysis` deta hai: summary, sentiment, outcome, interest score, extracted
qualification fields, talk-ratio (agent vs customer), objections, recommended next
action, aur key quotes. Yeh production voice agents (Retell/Vapi/Bland) ka
"post-call analysis / call summary" feature hai — CRM, dashboards aur lead-scoring
ke liye gold.

Design:
  - LLMBrain available ho to uska istemal (lazy import) summary + extraction ke liye.
  - HAMESHA ek pure-python heuristic fallback (keyword + word-count based) — bina
    kisi LLM/API key ke bhi chalega, kabhi crash nahi.
  - quick_metrics() pure-python talk-ratio / turn counts deta hai.

Conversation history format (same as project-wide):
    [{"role": "assistant"/"agent", "content": "..."},
     {"role": "user"/"customer",  "content": "..."}, ...]

Usage (no LLM / no keys needed — heuristic path):
    import asyncio
    from app.voice_agent.call_analyzer import CallAnalyzer

    history = [
        {"role": "assistant", "content": "Namaste, main Riya SunPower se. Do minute hain?"},
        {"role": "user", "content": "Haan boliye, par thoda mehenga lagta hai."},
        {"role": "assistant", "content": "Samajh sakti hoon, aap sirf qualified lead ke paise dete ho."},
        {"role": "user", "content": "Achha theek hai, kal demo de do."},
    ]
    analysis = asyncio.run(CallAnalyzer().analyze(history))
    print(analysis.outcome, analysis.interest_score, analysis.sentiment)
    print(analysis.summary)
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

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
class CallAnalysis:
    """Ek call ka poora post-call analysis.

    Attributes:
        summary:          2-3 line plain summary of the call.
        sentiment:        "positive" | "neutral" | "negative" (customer ka mood).
        outcome:          "qualified" | "callback" | "not_interested" |
                          "voicemail" | "no_answer".
        interest_score:   0-100 (lead kitna interested laga).
        extracted_fields: qualification answers dict (decision_maker, budget, etc.).
        talk_ratio:       {"agent": 0-1, "customer": 0-1} word-share.
        objections:       customer ne jo objections diye (list of strings).
        next_action:      recommended next step (string).
        key_quotes:       conversation ke important quotes (list of strings).
        meta:             extra metrics (turns, word counts, source: llm/heuristic).
    """

    summary: str = ""
    sentiment: str = "neutral"
    outcome: str = "no_answer"
    interest_score: int = 50
    extracted_fields: dict[str, Any] = field(default_factory=dict)
    talk_ratio: dict[str, float] = field(default_factory=lambda: {"agent": 0.0, "customer": 0.0})
    objections: list[str] = field(default_factory=list)
    next_action: str = ""
    key_quotes: list[str] = field(default_factory=list)
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Dataclass ko plain dict me convert karo (JSON / CRM ke liye)."""
        return asdict(self)


# --------------------------------------------------------------------------- #
# Keyword banks for heuristic analysis (Hinglish + English)
# --------------------------------------------------------------------------- #
_POSITIVE = [
    "haan",
    "yes",
    "sure",
    "theek hai",
    "accha",
    "achha",
    "great",
    "perfect",
    "interested",
    "bilkul",
    "zaroor",
    "sounds good",
    "ok",
    "okay",
    "demo",
    "schedule",
    "book",
    "chaiye",
    "chahiye",
    "badhiya",
    "good",
    "love",
]
_NEGATIVE = [
    "not interested",
    "nahi chahiye",
    "no thanks",
    "mat karo",
    "busy",
    "expensive",
    "mehenga",
    "waste",
    "bekaar",
    "remove",
    "stop calling",
    "already have",
    "pehle se",
    "don't call",
    "do not call",
    "irritate",
    "pareshaan",
    "no",
    "nahi",
]
_OBJECTION_MARKERS = [
    ("price", ["mehenga", "expensive", "costly", "price", "budget", "paise", "afford"]),
    ("timing", ["busy", "abhi nahi", "baad me", "call later", "time nahi", "no time"]),
    ("trust", ["robot", "scam", "fraud", "real", "kaun ho", "who are you", "fake"]),
    ("existing_provider", ["already have", "pehle se", "current provider", "doosra", "exists"]),
    ("not_interested", ["not interested", "nahi chahiye", "no thanks", "interested nahi"]),
]
_VOICEMAIL_MARKERS = [
    "leave a message",
    "after the tone",
    "after the beep",
    "voicemail",
    "not available",
    "kripya message",
    "record your message",
    "available nahi",
]
_QUALIFIED_MARKERS = [
    "demo",
    "book",
    "schedule",
    "appointment",
    "meeting",
    "kal",
    "tomorrow",
    "send details",
    "interested",
    "let's do",
    "chalo",
    "set kar",
    "callback time",
]
_CALLBACK_MARKERS = [
    "call later",
    "baad me",
    "call back",
    "callback",
    "phir call",
    "tomorrow call",
    "next week",
    "agle hafte",
    "busy abhi",
]


class CallAnalyzer:
    """Post-call analyzer with optional LLM + always-on heuristic fallback.

    LLMBrain inject kar sakte ho (ya khud lazy-build hoga). Agar LLM na ho /
    fail ho, to pure-python heuristic analysis use hoti hai — output shape same.
    """

    def __init__(self, brain: Any = None):
        """
        Args:
            brain: (optional) LLMBrain-like object with extract_qualification_data()
                   aur _generate(). Na do to lazy build hoga; vo bhi fail ho to
                   sirf heuristic.
        """
        self._brain = brain
        self._brain_tried = brain is not None

    # ----------------------- public API ----------------------- #
    async def analyze(
        self,
        conversation_history: list[dict[str, str]],
        lead: dict[str, Any] | None = None,
    ) -> CallAnalysis:
        """Poori conversation ka post-call analysis.

        Args:
            conversation_history: [{"role","content"}, ...] turns.
            lead:                 (optional) lead metadata (name, phone, niche...).

        Returns:
            CallAnalysis (LLM-enriched jahan possible, warna heuristic).
        """
        history = self._normalize(conversation_history)

        # Base: pure-python heuristics (hamesha milta hai, kabhi fail nahi).
        analysis = self._heuristic_analyze(history, lead)

        # Empty conversation -> no_answer (machine ko bhi customer side se detect).
        if not history:
            analysis.outcome = "no_answer"
            analysis.summary = "Call connect nahi hui / koi baat nahi hui (no answer)."
            analysis.meta["source"] = "heuristic"
            return analysis

        # Enrich with LLM if available (summary + structured extraction).
        brain = self._get_brain()
        if brain is not None:
            try:
                # 1) qualification extraction (reuse LLMBrain ka proven method)
                if hasattr(brain, "extract_qualification_data"):
                    extracted = await brain.extract_qualification_data(history)
                    if isinstance(extracted, dict) and "raw_response" not in extracted:
                        analysis.extracted_fields = {**analysis.extracted_fields, **extracted}
                        # interest_level se score refine
                        lvl = str(extracted.get("interest_level", "")).lower()
                        mapped = {"high": 85, "medium": 60, "low": 30, "none": 10}.get(lvl)
                        if mapped is not None:
                            analysis.interest_score = mapped

                # 2) natural-language summary via LLM
                if hasattr(brain, "_generate"):
                    summary = await self._llm_summary(brain, history)
                    if summary:
                        analysis.summary = summary

                analysis.meta["source"] = "llm+heuristic"
                logger.info("📊 Call analyzed with LLM enrichment")
                return analysis
            except Exception as e:
                logger.warning(f"LLM call-analysis failed, using heuristic: {e}")

        analysis.meta["source"] = "heuristic"
        return analysis

    def quick_metrics(self, conversation_history: list[dict[str, str]]) -> dict[str, Any]:
        """Pure-python conversation metrics (no LLM).

        Returns dict:
            talk_ratio:      {"agent": float, "customer": float}  (word share)
            agent_turns:     int
            customer_turns:  int
            total_turns:     int
            agent_words:     int
            customer_words:  int
            avg_agent_words: float  (per agent turn)
        """
        history = self._normalize(conversation_history)
        agent_words = customer_words = 0
        agent_turns = customer_turns = 0

        for turn in history:
            n = self._word_count(turn["content"])
            if turn["role"] == "agent":
                agent_words += n
                agent_turns += 1
            else:
                customer_words += n
                customer_turns += 1

        total_words = agent_words + customer_words or 1
        return {
            "talk_ratio": {
                "agent": round(agent_words / total_words, 3),
                "customer": round(customer_words / total_words, 3),
            },
            "agent_turns": agent_turns,
            "customer_turns": customer_turns,
            "total_turns": agent_turns + customer_turns,
            "agent_words": agent_words,
            "customer_words": customer_words,
            "avg_agent_words": round(agent_words / agent_turns, 2) if agent_turns else 0.0,
        }

    # ----------------------- heuristic engine ----------------------- #
    def _heuristic_analyze(
        self,
        history: list[dict[str, str]],
        lead: dict[str, Any] | None,
    ) -> CallAnalysis:
        metrics = self.quick_metrics(history)
        customer_text = " ".join(t["content"] for t in history if t["role"] == "customer").lower()
        full_text = " ".join(t["content"] for t in history).lower()

        # --- sentiment (keyword balance) ---
        pos = sum(customer_text.count(w) for w in _POSITIVE)
        neg = sum(customer_text.count(w) for w in _NEGATIVE)
        if pos > neg and pos > 0:
            sentiment = "positive"
        elif neg > pos and neg > 0:
            sentiment = "negative"
        else:
            sentiment = "neutral"

        # --- objections ---
        objections: list[str] = []
        for label, markers in _OBJECTION_MARKERS:
            if any(m in customer_text for m in markers):
                objections.append(label)

        # --- outcome ---
        outcome = self._infer_outcome(history, customer_text, full_text)

        # --- interest score (0-100) ---
        score = 50
        score += 10 * pos
        score -= 12 * neg
        score -= 5 * len(objections)
        if any(m in customer_text for m in _QUALIFIED_MARKERS):
            score += 20
        if outcome == "qualified":
            score = max(score, 70)
        elif outcome == "not_interested":
            score = min(score, 20)
        elif outcome in ("voicemail", "no_answer"):
            score = min(score, 10)
        interest_score = max(0, min(100, score))

        # --- extracted fields (regex/keyword based, LLM-free) ---
        extracted = self._extract_fields_heuristic(history, customer_text)

        # --- key quotes (customer ki important lines) ---
        key_quotes = self._key_quotes(history)

        # --- next action ---
        next_action = self._recommend_action(outcome, objections, interest_score)

        # --- summary ---
        summary = self._heuristic_summary(
            history, outcome, sentiment, interest_score, objections, metrics, lead
        )

        return CallAnalysis(
            summary=summary,
            sentiment=sentiment,
            outcome=outcome,
            interest_score=interest_score,
            extracted_fields=extracted,
            talk_ratio=metrics["talk_ratio"],
            objections=objections,
            next_action=next_action,
            key_quotes=key_quotes,
            meta={
                "turns": metrics["total_turns"],
                "agent_words": metrics["agent_words"],
                "customer_words": metrics["customer_words"],
                "avg_agent_words": metrics["avg_agent_words"],
                "source": "heuristic",
            },
        )

    def _infer_outcome(
        self, history: list[dict[str, str]], customer_text: str, full_text: str
    ) -> str:
        # voicemail: machine markers + customer ne bola hi nahi
        customer_turns = [t for t in history if t["role"] == "customer"]
        if any(m in full_text for m in _VOICEMAIL_MARKERS):
            return "voicemail"
        if not customer_turns:
            return "no_answer"
        if any(
            m in customer_text
            for m in [
                "not interested",
                "nahi chahiye",
                "no thanks",
                "interested nahi",
                "do not call",
                "don't call",
                "stop calling",
            ]
        ):
            return "not_interested"
        if any(m in customer_text for m in _QUALIFIED_MARKERS):
            return "qualified"
        if any(m in customer_text for m in _CALLBACK_MARKERS):
            return "callback"
        # bola to interested-ish but no clear signal
        return "callback" if len(customer_turns) >= 2 else "no_answer"

    def _extract_fields_heuristic(
        self, history: list[dict[str, str]], customer_text: str
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {}

        # decision maker
        if any(
            w in customer_text for w in ["main hi", "owner", "i am the", "decision", "haan main"]
        ):
            fields["is_decision_maker"] = True
        elif any(
            w in customer_text
            for w in ["malik se", "boss", "owner se", "manager se", "puchhna padega"]
        ):
            fields["is_decision_maker"] = False

        # email
        m = re.search(r"[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}", customer_text)
        if m:
            fields["email"] = m.group(0)

        # phone (10-digit India-ish)
        pm = re.search(r"(?:\+?91[\-\s]?)?[6-9]\d{9}", customer_text)
        if pm:
            fields["phone"] = pm.group(0)

        # budget (numbers with currency-ish context)
        bm = re.search(
            r"(?:rs\.?|₹|inr|budget)\s*([\d,]+(?:\s?(?:lakh|lac|cr|crore|k|thousand))?)",
            customer_text,
        )
        if bm:
            fields["budget_mentioned"] = bm.group(0)

        # callback time
        tm = re.search(
            r"(kal|tomorrow|monday|tuesday|wednesday|thursday|friday|"
            r"saturday|sunday|sham|subah|\d{1,2}\s?(?:am|pm|baje))",
            customer_text,
        )
        if tm:
            fields["callback_time_hint"] = tm.group(0)

        # interest level (string form, mirrors LLMBrain output)
        if any(
            w in customer_text for w in ["very interested", "bahut interested", "zaroor", "demo de"]
        ):
            fields["interest_level"] = "high"
        elif any(w in customer_text for w in ["not interested", "nahi chahiye"]):
            fields["interest_level"] = "none"
        elif any(w in customer_text for w in ["maybe", "shayad", "soch", "dekhte hain"]):
            fields["interest_level"] = "low"

        return fields

    def _key_quotes(self, history: list[dict[str, str]], max_quotes: int = 4) -> list[str]:
        """Customer ki sabse 'load-bearing' lines (signal words wali) nikaalo."""
        signal = (
            _POSITIVE
            + _NEGATIVE
            + [m for _, ms in _OBJECTION_MARKERS for m in ms]
            + _QUALIFIED_MARKERS
            + _CALLBACK_MARKERS
        )
        scored: list[tuple] = []
        for t in history:
            if t["role"] != "customer":
                continue
            low = t["content"].lower()
            hits = sum(1 for s in signal if s in low)
            if hits > 0:
                scored.append((hits, t["content"]))
        scored.sort(key=lambda x: x[0], reverse=True)
        quotes = [q for _, q in scored[:max_quotes]]
        # agar kuch signal-rich nahi mila, to pehla + aakhri customer turn le lo
        if not quotes:
            cust = [t["content"] for t in history if t["role"] == "customer"]
            quotes = list(dict.fromkeys(cust[:1] + cust[-1:]))[:max_quotes]
        return quotes

    def _recommend_action(self, outcome: str, objections: list[str], score: int) -> str:
        if outcome == "qualified":
            return "Lead ko CRM me 'hot' mark karo aur demo/appointment confirm karo."
        if outcome == "callback":
            return "Scheduled time par callback karo; lead warm hai."
        if outcome == "voicemail":
            return "Voicemail mila — alag time par dobara try karo, ya WhatsApp follow-up bhejo."
        if outcome == "no_answer":
            return "No answer — 2-3 alag time slots par retry karo."
        if outcome == "not_interested":
            return "Do-not-call respect karo; nurture list me daal ke 1-2 mahine baad WhatsApp."
        if "price" in objections:
            return "Pricing concern tha — per-lead model wala ROI case email/WhatsApp karo."
        return "Warm follow-up bhejo aur ek callback time fix karne ki koshish karo."

    def _heuristic_summary(
        self, history, outcome, sentiment, score, objections, metrics, lead
    ) -> str:
        who = ""
        if lead:
            nm = lead.get("name") or lead.get("company") or lead.get("lead_name")
            if nm:
                who = f"{nm} ke saath "
        obj = f" Objections: {', '.join(objections)}." if objections else ""
        outcome_hi = {
            "qualified": "lead qualified hua — interest dikha aur next step pe raazi",
            "callback": "callback chahiye — abhi commit nahi par baat khatam nahi",
            "not_interested": "lead interested nahi tha",
            "voicemail": "voicemail / answering machine mila",
            "no_answer": "koi proper baat nahi hui (no answer)",
        }.get(outcome, outcome)
        return (
            f"Call {who}me {outcome_hi}. Customer ka mood {sentiment} laga "
            f"(interest score ~{score}/100).{obj} "
            f"Agent talk-share {int(metrics['talk_ratio']['agent'] * 100)}%, "
            f"customer {int(metrics['talk_ratio']['customer'] * 100)}%."
        )

    # ----------------------- LLM helpers ----------------------- #
    async def _llm_summary(self, brain: Any, history: list[dict[str, str]]) -> str:
        import json

        prompt = (
            "Yeh ek sales call ki conversation hai. 2-3 line ka crisp summary do "
            "(Hinglish me): kya hua, customer ka interest, aur recommended next "
            "step. Sirf summary text do, koi heading/JSON nahi.\n\n"
            + json.dumps(history, ensure_ascii=False, indent=2)
        )
        try:
            out = await brain._generate(prompt)
            return (out or "").strip()
        except Exception as e:
            logger.debug(f"LLM summary fallback: {e}")
            return ""

    def _get_brain(self) -> Any:
        if self._brain is not None:
            return self._brain
        if self._brain_tried:
            return None
        self._brain_tried = True
        try:
            from app.voice_agent.llm_brain import LLMBrain

            self._brain = LLMBrain()
            return self._brain
        except Exception as e:
            logger.debug(f"LLMBrain unavailable for analysis: {e}")
            self._brain = None
            return None

    # ----------------------- normalization ----------------------- #
    @staticmethod
    def _normalize(conversation_history: list[dict[str, str]] | None) -> list[dict[str, str]]:
        """Mixed role labels ko {agent|customer} me normalize karo.

        Accepts: assistant/agent/bot -> agent ; user/customer/human -> customer.
        """
        out: list[dict[str, str]] = []
        for turn in conversation_history or []:
            if not isinstance(turn, dict):
                continue
            role = str(turn.get("role", "")).lower()
            content = str(turn.get("content", "") or "").strip()
            if not content:
                continue
            if role in ("assistant", "agent", "bot", "ai", "system"):
                norm = "agent"
            else:
                norm = "customer"
            out.append({"role": norm, "content": content})
        return out

    @staticmethod
    def _word_count(text: str) -> int:
        return len(re.findall(r"\w+", text or ""))


__all__ = ["CallAnalyzer", "CallAnalysis"]
