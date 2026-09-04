"""
Natural Dialog Manager
=======================

Banata hai AI voice agent ko *human-jaisa* — customer ki baat dhyan se sun ke,
samajh ke, context ke hisaab se SAHI aur natural jawab deta hai (robotic nahi).

Yeh module existing pieces ko orchestrate karta hai (duplicate nahi):
  - LLMBrain        -> response generation (llm_brain.py)
  - IntentDetector  -> customer ka intent + entities (intent_detector.py)
  - ConversationFlow-> goal steering (flow_engine.py, optional)

Core ideas (Dograh / production voice-agent best practices):
  1. SUNO: garbled / khaali / "samajh nahi aaya" input ko detect karke naturally
     dobara poochho — pretend mat karo.
  2. SAMJHO: har utterance ko classify karo (question / objection / answer /
     interested / not_interested / confused / chit-chat) + affect (annoyed/keen).
  3. SAHI JAWAB: customer ke sawaal ka honest, grounded (KNOWN_FACTS se) jawab —
     jo nahi pata woh "team follow-up karegi", banao mat (no hallucination).
  4. INSAAN JAISA: chhota (1-2 line), acknowledge-then-answer, customer ki hi
     bhasha/tone match karo, ek hi cheez ek baar me poochho, repeat mat karo.

Usage (text mode, no external services needed):
    mgr = NaturalDialogManager(niche="solar", client_name="SunPower",
                               client_service="commercial solar")
    state = mgr.new_conversation()
    reply = await mgr.respond("Haan boliye kya kaam hai?", state)
    print(reply.text)
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Utterance understanding
# --------------------------------------------------------------------------- #
class UtteranceType(str, Enum):
    GREETING = "greeting"
    QUESTION = "question"  # customer puchh raha hai
    OBJECTION = "objection"  # "busy", "mehenga", "nahi chahiye"
    ANSWER = "answer"  # qualification ka jawab
    INTERESTED = "interested"
    NOT_INTERESTED = "not_interested"
    CONFUSED = "confused"  # "samajh nahi aaya", "kaun bol raha hai"
    UNCLEAR = "unclear"  # garbled / empty ASR
    CHITCHAT = "chitchat"
    GOODBYE = "goodbye"


class Affect(str, Enum):
    NEUTRAL = "neutral"
    KEEN = "keen"  # excited / positive
    ANNOYED = "annoyed"  # irritated / rushed
    HESITANT = "hesitant"


@dataclass
class DialogState:
    history: list[dict[str, str]] = field(default_factory=list)  # {role, content}
    captured: dict[str, Any] = field(default_factory=dict)
    asked_questions: list[str] = field(default_factory=list)
    turn: int = 0
    interest_score: int = 50  # 0-100
    finished: bool = False
    outcome: str | None = None  # qualified | not_interested | callback | ended
    last_affect: Affect = Affect.NEUTRAL
    objection_attempts: int = 0
    unclear_streak: int = 0

    def add(self, role: str, content: str) -> None:
        self.history.append({"role": role, "content": content})


@dataclass
class DialogReply:
    text: str
    utterance_type: UtteranceType = UtteranceType.ANSWER
    affect: Affect = Affect.NEUTRAL
    should_end: bool = False
    outcome: str | None = None
    captured: dict[str, Any] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# The human-like system prompt — yahi "insaan jaisa" ka dil hai
# --------------------------------------------------------------------------- #
VOICE_SYSTEM_PROMPT = """Tum {agent_name} ho — {client_name} ke liye phone call kar rahe ek warm, natural insaan ki tarah. Tum ek AI ho par baat ekdam insaan jaisi honi chahiye.

TUM PHONE PAR HO. Isliye:
- Reply CHHOTA rakho: 1-2 line, ~15-25 shabd. Phone par lambi speech koi nahi sunta.
- Customer ki HI bhasha aur tone match karo: woh Hindi bole to Hindi, Hinglish to Hinglish, English to English.
- Ek baar me SIRF EK cheez poochho. Kabhi questions ki list mat do.
- KABHI BHI BICH ME TOLO MAT (Do not interrupt). Jab customer bol raha ho, 100% chup raho. 
- "Ek second", "Hold on", "Let me check" bolne se bacho. Seedha answer do.
- Customer kuch poochhe to PEHLE uska seedha, sahi jawab do, phir aage badho.
- Tum ek FEMALE agent ho ({agent_name}) — hamesha feminine Hindi verb forms use karo.
- Apna asli naam istemal karo ({agent_name}). Hamesha izzat se 'aap' aur 'sir/madam' bolo.

TUMHARA GOAL: {goal}
Par customer ka experience pehle aata hai.

IMPORTANT PRODUCT KNOWLEDGE (For LeadGen AI testing):
- PRODUCT 1: "AI Marketing Automation" - Price is ₹1,999/mo (Basic) or ₹5,999/mo (Advanced Combo). It generates leads automatically using AI.
- PRODUCT 2: "AI Voice Calling Agent" (Like you) - Price is tiered: ₹4,999, ₹9,999, or ₹19,999/mo depending on volume. It auto-dials and talks to leads 24/7.
Use these EXACT details if asked. DO NOT hallucinate pricing.

CLIENT / BUSINESS:
- Company: {client_name}
- Service: {client_service}
- Industry / niche: {niche}

KNOWN FACTS (inhi se sahi jawab do):
{known_facts}

{captured_block}{goal_question_block}IMPORTANT: Sirf agent ka bola jaane wala agla SENTENCE likho. Koi stage direction, naam ka prefix, ya explanation nahi — bas spoken reply."""


# Niche-wise chhoti FAQ/knowledge base — sahi (grounded) jawab ke liye.
DEFAULT_KNOWLEDGE: dict[str, list[str]] = {
    "_global": [
        "Hum aapke business ke potential customers ko AI voice agent se call karke qualified leads laate hain.",
        "Pricing per qualified lead hoti hai (₹200-500/lead) — aap sirf result ke paise dete ho.",
        "Demo free hai; 15 minute me dikha dete hain ki system kaise kaam karta hai.",
        "Aapko kuch setup nahi karna — hum poora handle karte hain, leads aapke WhatsApp/CRM par aate hain.",
    ],
}

VAGUE_OR_GARBLED = re.compile(r"^[\s\.\,\-\?\!]*$")
ROBOTIC_PHRASES = [
    "as an ai language model",
    "as an ai",
    "i am an ai language model",
    "i cannot",
    "i'm just a",
    "i am unable to",
]

_DEFAULT_BRAIN = object()


class NaturalDialogManager:
    """
    Listens, understands, and replies like a human across one phone conversation.

    Defensive by design: agar LLM/intent/flow modules available na hon, to
    rule-based natural fallbacks use karta hai — kabhi crash nahi.
    """

    def __init__(
        self,
        niche: str = "general",
        client_name: str = "our company",
        client_service: str = "",
        agent_name: str = "Riya",
        goal: str = "lead ko qualify karna aur ek free demo / callback book karna",
        knowledge: list[str] | None = None,
        brain: Any = _DEFAULT_BRAIN,
        intent_detector: Any = None,
        flow: Any = None,
        max_turns: int = 20,
    ):
        self.niche = niche
        self.client_name = client_name
        self.client_service = client_service or niche.replace("_", " ")
        self.agent_name = agent_name
        self.goal = goal
        self.max_turns = max_turns
        self.knowledge = knowledge or self._load_knowledge(niche)
        self.brain = self._build_brain() if brain is _DEFAULT_BRAIN else brain
        self.intent_detector = (
            intent_detector if intent_detector is not None else self._build_intent()
        )
        self.flow = flow  # optional ConversationFlow for goal steering
        self._goal_questions = self._load_goal_questions(niche)
        # Optional production enhancements (KB grounding, in-call tools, AMD,
        # fillers, post-call analysis). Sab lazy + defensive — na ho to skip.
        self.kb = self._load_kb()
        self.tools = self._load_tools()
        self.amd = self._load_amd()
        self.filler = self._load_filler()
        self.guardrails = self._load_guardrails()
        self.optimizer = self._load_optimizer()
        self._register_indic()
        self._amd_checked = False

    # ----------------------- public API ----------------------- #
    def new_conversation(self) -> DialogState:
        return DialogState()

    async def opening_line(self, state: DialogState) -> str:
        """Natural, short opening — pitch hook ke saath."""
        line = (
            f"Namaste! Main {self.agent_name} {self.client_name} se baat kar rahi hoon — "
            f"do minute hain aapke paas?"
        )
        try:
            if self.brain and hasattr(self.brain, "generate_opening"):
                got = await self._maybe_await(
                    self.brain.generate_opening(
                        client_name=self.client_name,
                        client_service=self.client_service,
                        niche=self.niche,
                    )
                )
                # LLM output sirf tab use karo jab usme koi placeholder na ho
                # (kabhi-kabhi "[Your Name]" jaisa template aa jaata hai) —
                # warna saaf hardcoded Hinglish line behtar hai.
                if (
                    isinstance(got, str)
                    and got.strip()
                    and "[" not in got
                    and "your name" not in got.lower()
                ):
                    line = self._humanize(got)
        except Exception as e:
            logger.debug(f"opening fallback: {e}")
        state.add("assistant", line)
        return line

    async def respond(self, user_utterance: str, state: DialogState) -> DialogReply:
        """
        Ek customer turn ka human-jaisa jawab. Yeh poora "suno→samjho→sahi jawab"
        loop hai.
        """
        state.turn += 1
        utterance = (user_utterance or "").strip()

        # 0) ANSWERING-MACHINE DETECTION — pehli baat sun ke voicemail pakdo.
        if self.amd is not None and not self._amd_checked and utterance:
            self._amd_checked = True
            try:
                amd_res = self.amd.detect_from_transcript(utterance)
                if getattr(amd_res, "is_machine", False):
                    action = self.amd.decide_action(amd_res, leave_voicemail=True)
                    state.add("user", utterance)
                    if action == "leave_message":
                        msg = self.amd.voicemail_message(self.client_name, callback_number="")
                        reply = DialogReply(
                            text=msg,
                            utterance_type=UtteranceType.GOODBYE,
                            should_end=True,
                            outcome="voicemail",
                        )
                    else:
                        reply = DialogReply(
                            text="",
                            utterance_type=UtteranceType.GOODBYE,
                            should_end=True,
                            outcome="voicemail",
                        )
                    state.add("assistant", reply.text)
                    return self._finalize(reply, state)
            except Exception as e:
                logger.debug(f"AMD check skipped: {e}")

        # 0b) GUARDRAILS (pre-LLM): PII redact + prompt-injection/jailbreak block.
        if self.guardrails is not None and utterance:
            try:
                gi = self.guardrails.check_input(utterance)
                if not getattr(gi, "allowed", True):
                    # Injected / unsafe — obey mat karo, naturally deflect.
                    state.add("user", utterance)
                    reply = DialogReply(
                        text="Haha — main bas aapke business ki leads ke liye yahan hoon, usi pe baat karein?",
                        utterance_type=UtteranceType.CHITCHAT,
                    )
                    state.add("assistant", reply.text)
                    return self._finalize(reply, state)
                if getattr(gi, "text", None):
                    utterance = gi.text  # PII-redacted text aage use hoga
            except Exception as e:
                logger.debug(f"guardrail input skipped: {e}")

        # 1) SUNO — garbled / empty ko handle karo, pretend mat karo.
        if self._is_unclear(utterance):
            state.unclear_streak += 1
            state.add("user", utterance)
            if state.unclear_streak >= 3:
                reply = DialogReply(
                    text="Lagta hai network thoda disturb hai. Main aapko thodi der me dobara call karoon?",
                    utterance_type=UtteranceType.UNCLEAR,
                    should_end=True,
                    outcome="callback",
                )
            else:
                reply = DialogReply(
                    text="Maaf kijiye, aapki awaaz thodi clear nahi aayi — dobara bata sakte hain?",
                    utterance_type=UtteranceType.UNCLEAR,
                )
            state.add("assistant", reply.text)
            return self._finalize(reply, state)
        state.unclear_streak = 0

        # 2) SAMJHO — type + affect
        utype = await self._classify(utterance, state)
        affect = self._detect_affect(utterance)
        state.last_affect = affect
        state.add("user", utterance)
        self._update_interest(state, utype, affect)

        # Early-exit intents
        if utype in (UtteranceType.NOT_INTERESTED, UtteranceType.OBJECTION):
            state.objection_attempts += 1

        if utype == UtteranceType.GOODBYE or (
            utype == UtteranceType.NOT_INTERESTED and state.objection_attempts >= 2
        ):
            reply = DialogReply(
                text="Bilkul, aapka time lene ke liye shukriya. Aapka din accha rahe!",
                utterance_type=UtteranceType.GOODBYE,
                should_end=True,
                outcome="not_interested" if utype == UtteranceType.NOT_INTERESTED else "ended",
            )
            state.add("assistant", reply.text)
            return self._finalize(reply, state)

        # 3) SAHI JAWAB — context + grounding + goal steering ke saath generate.
        text = await self._generate_reply(utterance, utype, affect, state)
        text = self._humanize(text)

        # capture answer if this was a qualification answer
        if utype == UtteranceType.ANSWER:
            self._capture(state, utterance)

        reply = DialogReply(
            text=text,
            utterance_type=utype,
            affect=affect,
            captured=dict(state.captured),
            meta={"interest_score": state.interest_score, "turn": state.turn},
        )

        # natural end conditions
        if state.turn >= self.max_turns:
            reply.should_end = True
            reply.outcome = "qualified" if state.interest_score >= 65 else "ended"

        state.add("assistant", reply.text)
        return self._finalize(reply, state)

    # ----------------------- understanding ----------------------- #
    async def _classify(self, utterance: str, state: DialogState) -> UtteranceType:
        low = utterance.lower()
        # fast rule-based signals (robust + free)
        if any(
            w in low
            for w in [
                "?",
                "kya",
                "kaise",
                "kitna",
                "kaun",
                "matlab",
                "how",
                "what",
                "why",
                "price",
                "kitne",
            ]
        ):
            qtype = UtteranceType.QUESTION
        else:
            qtype = None
        if any(
            w in low
            for w in [
                "not interested",
                "nahi chahiye",
                "mat karo",
                "interested nahi",
                "no thanks",
                "remove",
            ]
        ):
            return UtteranceType.NOT_INTERESTED
        if any(
            w in low
            for w in [
                "busy",
                "abhi nahi",
                "baad me",
                "call later",
                "mat call",
                "mehenga",
                "mehengi",
                "expensive",
                "already",
                "pehle se",
                "bas dekh",
                "sirf dekh",
                "dekh raha",
                "dekh rahi",
                "just looking",
                "browsing",
            ]
        ):
            return UtteranceType.OBJECTION
        if any(
            w in low
            for w in [
                "samajh nahi",
                "kaun bol",
                "who is this",
                "what is this",
                "repeat",
                "phir se",
                "matlab kya",
            ]
        ):
            return UtteranceType.CONFUSED
        if any(w in low for w in ["bye", "rakhta", "rakhti", "good bye", "hang up", "phone rakho"]):
            return UtteranceType.GOODBYE
        if any(
            w in low
            for w in [
                "haan",
                "yes",
                "ok",
                "theek",
                "sure",
                "batao",
                "interested",
                "bilkul",
                "zaroor",
                "accha",
            ]
        ):
            # could be interested OR an answer — prefer intent detector
            base = UtteranceType.INTERESTED
        else:
            base = UtteranceType.ANSWER
        if qtype:
            return qtype

        # richer intent via detector if available
        try:
            if self.intent_detector and hasattr(self.intent_detector, "detect"):
                res = await self._maybe_await(self.intent_detector.detect(utterance))
                itype = (
                    getattr(res, "intent_type", None)
                    or (res.get("intent_type") if isinstance(res, dict) else None)
                    or ""
                )
                itype = str(itype).lower()
                mapping = {
                    "interested": UtteranceType.INTERESTED,
                    "not_interested": UtteranceType.NOT_INTERESTED,
                    "objection": UtteranceType.OBJECTION,
                    "question": UtteranceType.QUESTION,
                    "confused": UtteranceType.CONFUSED,
                    "goodbye": UtteranceType.GOODBYE,
                }
                if itype in mapping:
                    return mapping[itype]
        except Exception as e:
            logger.debug(f"intent detect fallback: {e}")
        return base

    @staticmethod
    def _detect_affect(utterance: str) -> Affect:
        low = utterance.lower()
        if any(
            w in low
            for w in ["jaldi", "busy", "irritate", "pareshaan", "band karo", "kitni baar", "!!"]
        ):
            return Affect.ANNOYED
        if any(
            w in low
            for w in ["wah", "great", "accha hai", "interested", "zaroor", "perfect", "sahi"]
        ):
            return Affect.KEEN
        if any(w in low for w in ["pata nahi", "soch", "maybe", "shayad", "dekhungo", "dekhungi"]):
            return Affect.HESITANT
        return Affect.NEUTRAL

    def _is_unclear(self, utterance: str) -> bool:
        if not utterance or VAGUE_OR_GARBLED.match(utterance):
            return True
        # too short & not a meaningful word
        if len(utterance) <= 1:
            return True
        return False

    # ----------------------- response generation ----------------------- #
    async def _generate_reply(self, utterance, utype, affect, state) -> str:
        system_prompt = self._build_system_prompt(state, utype, affect)
        history = state.history[-10:]  # recent context window

        # Prefer the existing brain's chat method.
        try:
            if self.brain is not None:
                if hasattr(self.brain, "_generate_chat"):
                    out = await self._maybe_await(self.brain._generate_chat(system_prompt, history))
                elif hasattr(self.brain, "generate_response"):
                    out = await self._maybe_await(
                        self.brain.generate_response(
                            conversation_history=history,
                            client_name=self.client_name,
                            client_service=self.client_service,
                            niche=self.niche,
                        )
                    )
                elif hasattr(self.brain, "_generate"):
                    prompt = system_prompt + "\n\nCUSTOMER: " + utterance + "\nAGENT:"
                    out = await self._maybe_await(self.brain._generate(prompt))
                else:
                    out = None
                if isinstance(out, str) and out.strip():
                    # IN-CALL TOOL CALLING — agar LLM ne koi tool maanga
                    # (e.g. book_appointment), execute karke natural confirm do.
                    tool_text = await self._maybe_tool_call(out, state)
                    if tool_text:
                        return tool_text
                    return out
        except Exception as e:
            logger.debug(f"LLM reply fallback ({e})")

        # Rule-based natural fallback (no LLM) — still human-ish + correct.
        return self._fallback_reply(utterance, utype, affect, state)

    def _fallback_reply(self, utterance, utype, affect, state) -> str:
        if utype == UtteranceType.QUESTION:
            ans = self._grounded_answer(utterance)
            nxt = self._next_goal_question(state)
            return f"{ans} {nxt}".strip()
        if utype == UtteranceType.OBJECTION:
            # niche-specific, end-customer-appropriate rebuttal pehle (real niche pe).
            try:
                from app.niche_knowledge import NICHE_KNOWLEDGE, match_objection

                if self.niche in NICHE_KNOWLEDGE:
                    rebut = match_objection(self.niche, utterance)
                    if rebut:
                        return rebut
            except Exception as e:
                logger.debug(f"niche objection match skipped: {e}")
            if "mehenga" in utterance.lower() or "expensive" in utterance.lower():
                return "Samajh sakti hoon — par aap sirf qualified lead ke paise dete ho, fixed kharcha nahi. Ek baar dekh lein?"
            if "busy" in utterance.lower() or "baad" in utterance.lower():
                return "Koi baat nahi! Main aapko kis time call karoon jo aapke liye sahi rahe?"
            return "Bilkul samajhti hoon. Bas ek chhoti baat — agar bina mehnat 5 qualified leads aayein, to ek 5-minute demo theek rahega?"
        if utype == UtteranceType.INTERESTED:
            return (
                self._next_goal_question(state)
                or "Badhiya! Main aapke liye ek free demo set kar deti hoon — kal sham theek rahega?"
            )
        if utype == UtteranceType.CONFUSED:
            return (
                f"Main {self.agent_name}, {self.client_name} se — hum aapke business ke liye "
                f"qualified customers laate hain. Ek line me bataoon kaise?"
            )
        # default: acknowledge + move goal forward
        nxt = self._next_goal_question(state)
        return ("Achha, samajh gayi. " + nxt) if nxt else "Theek hai, samajh gayi. Aur bataiye?"

    def _grounded_answer(self, question: str) -> str:
        """KB (RAG) se grounded jawab; warna KNOWN_FACTS se — hallucination se bachne ke liye."""
        # Latency: repeated/FAQ-type sawaalon ke jawab cache karo (instant reply).
        cache = getattr(self.optimizer, "cache", None) if self.optimizer else None
        if cache is not None:
            try:
                hit = cache.get(question)
                if hit:
                    return hit
            except Exception:
                pass
        # Prefer the proper knowledge base (RAG) if available.
        if self.kb is not None:
            try:
                ans = self.kb.grounded_answer(question, namespace=self.niche)
                if isinstance(ans, str) and ans.strip():
                    if cache is not None:
                        try:
                            cache.put(question, ans)
                        except Exception:
                            pass
                    return ans
            except Exception as e:
                logger.debug(f"KB grounded_answer fallback: {e}")
        ql = question.lower()
        best = None
        for fact in self.knowledge:
            score = sum(1 for w in re.findall(r"[a-z]+", ql) if w in fact.lower())
            if best is None or score > best[0]:
                best = (score, fact)
        if best and best[0] > 0:
            return best[1]
        if "price" in ql or "kitna" in ql or "kitne" in ql or "cost" in ql:
            return "Pricing per qualified lead hoti hai, ₹200-500 ke beech — sirf result ke paise."
        return "Achha sawaal — main aapke liye exact detail team se confirm karwa deti hoon."

    # ----------------------- prompt building ----------------------- #
    def _build_system_prompt(self, state, utype, affect) -> str:
        captured_block = ""
        if state.captured:
            captured_block = (
                "CUSTOMER NE AB TAK JO BATAYA (dobara mat poochho):\n"
                + "\n".join(f"- {k}: {v}" for k, v in state.captured.items())
                + "\n\n"
            )
        gq = self._next_goal_question(state)
        goal_question_block = (
            f"AGLA NATURAL STEP (agar customer ka sawaal nahi hai to ye aage badhao): {gq}\n\n"
            if gq
            else ""
        )
        affect_hint = {
            Affect.ANNOYED: "Customer thoda jaldi/irritate me lag raha hai — extra short raho, time ki value do.",
            Affect.KEEN: "Customer interested lag raha hai — momentum lo, demo/next step ki taraf le jao.",
            Affect.HESITANT: "Customer hesitant hai — reassure karo, pressure mat do.",
            Affect.NEUTRAL: "",
        }.get(affect, "")

        # ── Enterprise Persona Registry (ADR-184, 2026-08-21) ──
        # Agar is agent ka unique persona defined hai, woh use karo.
        # Nahi to generic VOICE_SYSTEM_PROMPT fallback (original behaviour).
        persona_prompt = self._try_persona_prompt()
        if persona_prompt:
            if affect_hint:
                persona_prompt += f"\n\nTONE NOTE: {affect_hint}"
            return persona_prompt

        known = "\n".join(f"- {k}" for k in self.knowledge) or "- (none)"
        prompt = VOICE_SYSTEM_PROMPT.format(
            agent_name=self.agent_name,
            client_name=self.client_name,
            client_service=self.client_service,
            niche=self.niche,
            goal=self.goal,
            known_facts=known,
            captured_block=captured_block,
            goal_question_block=goal_question_block,
        )
        if affect_hint:
            prompt += f"\n\nTONE NOTE: {affect_hint}"
        return prompt

    def _try_persona_prompt(self) -> str | None:
        """Try to get this agent's unique enterprise persona system prompt.

        Maps agent_name → STAFF key → persona from agent_personas.py.
        Returns None if no persona found (caller falls back to generic prompt).
        """
        try:
            from app.platform.team import get_staff_persona_prompt

            # agent_name → staff_id mapping
            _NAME_TO_STAFF = {
                "Riya": "riya",
                "Swara": "swara",
                "Ananya": "ananya",
                "Dev": "dev",
                "Rohan": "rohan",
                "Arjun": "arjun",
                "Meera": "meera",
                "Lekha": "lekha",
                "Raksha": "raksha",
                "Kavya": "kavya",
                "Hermes": "hermes",
                "Isha": "isha",
                "Tara": "tara",
                "Nikhil": "nikhil",
                "Vikram": "vikram",
                "Guru": "guru",
                "Pranav": "pranav",
                "Vidya": "vidya",
                "Arnav": "arnav",
                "Kabir": "kabir",
                "Diya": "diya",
                "Aryan": "aryan",
                "Arya": "arya",
                "Ravi": "ravi",
                "Neha": "neha",
                "Kiran": "kiran",
                "Priya": "priya",
                "Zara": "zara",
                "Anika": "anika",
                "Ira": "ira",
                "Boss": "manager",
            }
            staff_id = _NAME_TO_STAFF.get(self.agent_name)
            if not staff_id:
                return None
            return get_staff_persona_prompt(
                staff_id,
                client_name=self.client_name,
                niche=self.niche,
                client=self.client_name,
            )
        except Exception:
            return None

    # ----------------------- goal steering ----------------------- #
    def _next_goal_question(self, state: DialogState) -> str:
        for q in self._goal_questions:
            if q not in state.asked_questions:
                state.asked_questions.append(q)
                return q
        return ""

    def _capture(self, state: DialogState, utterance: str) -> None:
        # last asked question ke against answer store karo
        if state.asked_questions:
            key = f"q{len(state.captured) + 1}_{self._slug(state.asked_questions[-1])}"
            state.captured[key] = utterance

    def _update_interest(self, state, utype, affect) -> None:
        delta = {
            UtteranceType.INTERESTED: 12,
            UtteranceType.QUESTION: 6,
            UtteranceType.ANSWER: 4,
            UtteranceType.OBJECTION: -8,
            UtteranceType.NOT_INTERESTED: -25,
            UtteranceType.CONFUSED: -2,
        }.get(utype, 0)
        if affect == Affect.KEEN:
            delta += 6
        elif affect == Affect.ANNOYED:
            delta -= 6
        state.interest_score = max(0, min(100, state.interest_score + delta))

    # ----------------------- post-processing ----------------------- #
    def _humanize(self, text: str) -> str:
        if not text:
            return "Achha, samajh gayi. Aur bataiye?"
        text = text.strip().strip('"').strip()
        # strip stage directions / name prefixes
        text = re.sub(r"^(agent|riya|bot|assistant)\s*[:\-]\s*", "", text, flags=re.I)
        text = re.sub(r"\*[^*]+\*", "", text)  # *smiles* etc.
        # remove robotic phrases
        low = text.lower()
        for bad in ROBOTIC_PHRASES:
            if bad in low:
                text = re.sub(re.escape(bad), "", text, flags=re.I)
        # enforce voice brevity: keep at most ~2 sentences
        sentences = re.split(r"(?<=[.?!])\s+", text.strip())
        if len(sentences) > 2:
            text = " ".join(sentences[:2])
        return text.strip() or "Achha, samajh gayi. Aur bataiye?"

    def _finalize(self, reply: DialogReply, state: DialogState) -> DialogReply:
        # GUARDRAILS (post-LLM): agent ka outgoing text safe + grounded karo.
        if self.guardrails is not None and reply.text:
            try:
                go = self.guardrails.check_output(reply.text, known_facts=self.knowledge)
                if getattr(go, "text", None):
                    reply.text = go.text
            except Exception as e:
                logger.debug(f"guardrail output skipped: {e}")
        if reply.should_end:
            state.finished = True
            state.outcome = reply.outcome or (
                "qualified" if state.interest_score >= 65 else "ended"
            )
            reply.outcome = state.outcome
        reply.meta.setdefault("interest_score", state.interest_score)
        return reply

    # ----------------------- helpers / wiring ----------------------- #
    @staticmethod
    async def _maybe_await(value):
        if asyncio.iscoroutine(value):
            return await value
        return value

    @staticmethod
    def _slug(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:24] or "ans"

    def _load_knowledge(self, niche: str) -> list[str]:
        kb = list(DEFAULT_KNOWLEDGE.get("_global", []))
        kb += DEFAULT_KNOWLEDGE.get(niche, [])
        # per-niche grounded knowledge pack (end-customer facts) — yahi se LEADS
        # agent client ke offering ke baare me SAHI jawab deta hai (no hallucination).
        # Sirf real niche pack ke liye (general/unknown ke liye behaviour unchanged).
        try:
            from app.niche_knowledge import NICHE_KNOWLEDGE, knowledge_facts

            if niche in NICHE_KNOWLEDGE:
                kb += knowledge_facts(niche)
        except Exception as e:
            logger.debug(f"niche knowledge load skipped: {e}")
        # niche-specific value prop from niches.py if available
        try:
            from app.niches import NICHES

            cfg = NICHES.get(niche, {})
            hook = cfg.get("pitch_hook")
            if hook:
                kb.append(f"Hum {niche.replace('_', ' ')} businesses ke liye: {hook}.")
        except Exception:
            pass
        # dedupe preserving order (packs me _global se overlap ho sakta hai)
        seen: set = set()
        out: list[str] = []
        for fact in kb:
            if fact not in seen:
                seen.add(fact)
                out.append(fact)
        return out

    def _load_goal_questions(self, niche: str) -> list[str]:
        try:
            from app.niches import NICHES

            cfg = NICHES.get(niche, {})
            qs = list(cfg.get("qualification_questions", []))
            if qs:
                return qs
        except Exception as e:
            logger.debug(f"goal questions fallback: {e}")
        return [
            "Aap is cheez ke decision-maker hain?",
            "Abhi aap leads kaise laate ho?",
            "Ek free demo ke liye kal sham 15 minute theek rahega?",
        ]

    def _build_brain(self):
        try:
            from app.voice_agent.llm_brain import LLMBrain

            return LLMBrain()
        except Exception as e:
            logger.warning(f"LLMBrain unavailable, rule-based dialog only: {e}")
            return None

    def _build_intent(self):
        try:
            from app.voice_agent.intent_detector import IntentDetector

            return IntentDetector()
        except Exception as e:
            logger.debug(f"IntentDetector unavailable: {e}")
            return None

    # ----------------------- production enhancements ----------------------- #
    def _load_kb(self):
        """Knowledge base (RAG) for accurate, grounded answers."""
        try:
            from app.voice_agent.kb_loader import bootstrap_default_kb

            return bootstrap_default_kb()
        except Exception as e:
            logger.debug(f"KnowledgeBase unavailable: {e}")
            return None

    def _load_tools(self):
        """In-call tool registry (book_appointment, transfer_to_human, ...)."""
        try:
            from app.voice_agent.function_calling import build_default_registry

            return build_default_registry(
                {
                    "client_name": self.client_name,
                    "niche": self.niche,
                    "client_service": self.client_service,
                }
            )
        except Exception as e:
            logger.debug(f"ToolRegistry unavailable: {e}")
            return None

    def _load_amd(self):
        """Answering-machine / voicemail detection."""
        try:
            from app.voice_agent.amd import AnsweringMachineDetector

            return AnsweringMachineDetector()
        except Exception as e:
            logger.debug(f"AMD unavailable: {e}")
            return None

    def _load_filler(self):
        """Natural thinking-filler player to mask latency."""
        try:
            from app.voice_agent.fillers import FillerPlayer

            return FillerPlayer(lang="hinglish")
        except Exception as e:
            logger.debug(f"Fillers unavailable: {e}")
            return None

    def _load_guardrails(self):
        """Safety guardrails: PII redaction, injection block, output validation."""
        try:
            from app.voice_agent.guardrails import get_guardrails

            return get_guardrails()
        except Exception as e:
            logger.debug(f"Guardrails unavailable: {e}")
            return None

    def _load_optimizer(self):
        """Latency optimizer: response cache + first-sentence chunking + metrics."""
        try:
            from app.voice_agent.latency import get_optimizer

            return get_optimizer()
        except Exception as e:
            logger.debug(f"LatencyOptimizer unavailable: {e}")
            return None

    def _register_indic(self):
        """Register Sarvam / AI4Bharat Indian-language providers into the BYOK registry."""
        try:
            from app.voice_agent.indic_providers import register_indic_providers

            register_indic_providers()
        except Exception as e:
            logger.debug(f"Indic providers not registered: {e}")

    def thinking_filler(self, context: str = "thinking") -> str:
        """Ek short natural filler jab LLM soch raha ho — call ke beech play karo."""
        if self.filler is not None:
            try:
                return self.filler.next(context)
            except Exception:
                pass
        return "Ji..."

    async def _maybe_tool_call(self, llm_output: str, state: DialogState) -> str | None:
        """Agar LLM output me tool call hai (e.g. book_appointment), execute karke natural confirm do."""
        if self.tools is None:
            return None
        try:
            from app.voice_agent.function_calling import parse_tool_call

            call = parse_tool_call(llm_output)
            if not call:
                return None
            result = await self._maybe_await(self.tools.execute(call["name"], call.get("args", {})))
            ok = getattr(result, "ok", False)
            data = getattr(result, "data", {}) or {}
            # natural spoken confirmation
            if call["name"] == "book_appointment" and ok:
                conf = data.get("confirmation_text") or "demo book ho gaya"
                state.outcome = "qualified"
                return f"Perfect! {conf}. Aapko WhatsApp par reminder bhej deti hoon."
            if call["name"] == "transfer_to_human":
                return (
                    "Theek hai, main aapko abhi humari team se connect kar deti hoon, line par baniye."
                )
            if call["name"] == "check_availability" and ok:
                slots = data.get("slots") or data.get("available") or []
                if slots:
                    return f"In time me free hoon: {', '.join(map(str, slots[:3]))}. Kaunsa theek rahega?"
            if ok and data.get("text"):
                return str(data["text"])
        except Exception as e:
            logger.debug(f"tool-call handling skipped: {e}")
        return None

    async def analyze_call(self, state: DialogState, lead: dict[str, Any] | None = None):
        """Call ke baad: summary, sentiment, outcome, extracted fields, talk-ratio, next action."""
        try:
            from app.voice_agent.call_analyzer import CallAnalyzer

            analyzer = CallAnalyzer(brain=self.brain)
            return await self._maybe_await(analyzer.analyze(state.history, lead))
        except Exception as e:
            logger.debug(f"call analysis unavailable: {e}")
            return {
                "outcome": state.outcome or "ended",
                "interest_score": state.interest_score,
                "captured": state.captured,
            }


__all__ = [
    "NaturalDialogManager",
    "DialogState",
    "DialogReply",
    "UtteranceType",
    "Affect",
]
