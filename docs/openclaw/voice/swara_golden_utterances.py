"""
Swara Golden Utterances — curated library of approved Hinglish responses.

Rule 8: Maintain swara_golden_utterances organized by intent:
    greeting, lead_qualification, appointment_booking, pricing,
    objection_handling, customer_confusion, follow_up, closing,
    escalation, payment, rescheduling, support, goodbye,
    sales_discovery, owner_communication

Each golden example includes:
    intent, context, english_semantic_meaning, approved_hinglish_response,
    tone, voice_instructions, quality_score, version.

Rule 19: Version everything — swara_golden_utterances_v1
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# -----------------------------------------------------------------------------
# SCHEMA
# -----------------------------------------------------------------------------

@dataclass
class GoldenUtterance:
    """A single approved Swara utterance example."""
    intent: str
    context: str  # e.g., "cold_call_opening", "pricing_inquiry_budget"
    english_semantic_meaning: str  # What it means in plain English
    approved_hinglish_response: str  # The canonical Swara response
    tone: str = "professional"  # professional | warm | confident | empathetic | energetic
    voice_instructions: str = ""  # e.g., "pause_after_greeting", "emphasize_price", "slow_down"
    quality_score: float = 0.95  # 0-1, must be >= 0.95 per Rule 10
    version: str = "swara_golden_utterances_v1"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = "manual"  # manual | owner_approved | eval_promoted
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# -----------------------------------------------------------------------------
# DEFAULT GOLDEN UTTERANCES — PROJECT-SPECIFIC
# These are the canonical Swara responses for LeadGen AI domain.
# Add new golden examples here — they become the single source of truth.
# -----------------------------------------------------------------------------

DEFAULT_GOLDEN_UTTERANCES: dict[str, list[GoldenUtterance]] = {
    "greeting": [
        GoldenUtterance(
            intent="greeting",
            context="cold_call_opening",
            english_semantic_meaning="Hello, this is an automated AI call from [client_name]. How are you?",
            approved_hinglish_response="Namaste! Yeh {client_name} ki taraf se ek automated AI call hai. Aap kaise hain?",
            tone="warm",
            voice_instructions="pause_after_greeting,natural_breathing",
            quality_score=0.98,
            tags=["compliance_disclosure", "opening"],
        ),
        GoldenUtterance(
            intent="greeting",
            context="callback_response",
            english_semantic_meaning="Hello! Thanks for calling back. I'm calling from [client_name].",
            approved_hinglish_response="Namaste! Callback ke liye shukriya. Main {client_name} se bol rahi hoon.",
            tone="warm",
            voice_instructions="friendly_pace",
            quality_score=0.97,
            tags=["callback", "warm"],
        ),
        GoldenUtterance(
            intent="greeting",
            context="inbound_inquiry_response",
            english_semantic_meaning="Thanks for your interest in our services. Let me help you.",
            approved_hinglish_response="Aapki interest ke liye bahut shukriya! Main aapki madad kar sakti hoon.",
            tone="helpful",
            voice_instructions="enthusiastic_start",
            quality_score=0.96,
            tags=["inbound", "helpful"],
        ),
    ],

    "lead_qualification": [
        GoldenUtterance(
            intent="lead_qualification",
            context="business_type_inquiry",
            english_semantic_meaning="What type of business do you run?",
            approved_hinglish_response="Aap kaun sa business chalaate hain?",
            tone="professional",
            voice_instructions="clear_enunciation",
            quality_score=0.97,
            tags=["qualification", "business_type"],
        ),
        GoldenUtterance(
            intent="lead_qualification",
            context="current_marketing_inquiry",
            english_semantic_meaning="Are you currently doing any marketing for your business?",
            approved_hinglish_response="Kya aap abhi apne business ke liye kuch marketing kar rahe hain?",
            tone="consultative",
            voice_instructions="gentle_pace",
            quality_score=0.96,
            tags=["qualification", "marketing"],
        ),
        GoldenUtterance(
            intent="lead_qualification",
            context="budget_range_inquiry",
            english_semantic_meaning="What's your monthly budget for marketing?",
            approved_hinglish_response="Monthly marketing ka aapka budget kitna hai?",
            tone="professional",
            voice_instructions="neutral_tone",
            quality_score=0.96,
            tags=["qualification", "budget"],
        ),
    ],

    "appointment_booking": [
        GoldenUtterance(
            intent="appointment_booking",
            context="propose_meeting",
            english_semantic_meaning="Would you be open to a quick 15-minute call to discuss how we can help?",
            approved_hinglish_response="Kya aap 15 minute ki ek quick call ke liye open hain taaki main samjha sakun ki hum kaise help kar sakte hain?",
            tone="persuasive",
            voice_instructions="confident_pause_after_question",
            quality_score=0.97,
            tags=["appointment", "trial_close"],
        ),
        GoldenUtterance(
            intent="appointment_booking",
            context="confirm_time",
            english_semantic_meaning="Perfect, your appointment is confirmed for tomorrow at 4 PM.",
            approved_hinglish_response="Perfect, aapki appointment kal 4 PM ke liye confirm ho gayi hai.",
            tone="confident",
            voice_instructions="clear_time_emphasis",
            quality_score=0.98,
            tags=["appointment", "confirmation"],
        ),
        GoldenUtterance(
            intent="appointment_booking",
            context="reschedule_request",
            english_semantic_meaning="No problem, what day and time would work better for you?",
            approved_hinglish_response="Koi baat nahi, aapko kaunsa din aur time better lagega?",
            tone="accommodating",
            voice_instructions="patient_tone",
            quality_score=0.97,
            tags=["appointment", "reschedule"],
        ),
    ],

    "pricing": [
        GoldenUtterance(
            intent="pricing",
            context="starter_plan_explanation",
            english_semantic_meaning="Our starter plan is 1,999 rupees per month, which includes automated marketing.",
            approved_hinglish_response="Hamara starter plan 1,999 rupees mahina ka hai, jisme automated marketing included hai.",
            tone="clear",
            voice_instructions="emphasize_price, pause_after_price",
            quality_score=0.98,
            tags=["pricing", "starter", "transparent"],
        ),
        GoldenUtterance(
            intent="pricing",
            context="voice_agent_pricing",
            english_semantic_meaning="The AI voice calling agent starts at 4,999 rupees per month for a niche band.",
            approved_hinglish_response="AI voice calling agent 4,999 rupees mahina se start hota hai, niche band ke hisaab se.",
            tone="clear",
            voice_instructions="emphasize_price, clear_niche_reference",
            quality_score=0.97,
            tags=["pricing", "voice_agent", "niche_band"],
        ),
        GoldenUtterance(
            intent="pricing",
            context="combo_plan_explanation",
            english_semantic_meaning="The combo plan at 5,999 rupees includes both marketing automation and voice callback feature.",
            approved_hinglish_response="Combo plan 5,999 ka hai jisme marketing automation aur voice callback dono hain.",
            tone="helpful",
            voice_instructions="list_both_features",
            quality_score=0.97,
            tags=["pricing", "combo", "bundle"],
        ),
        GoldenUtterance(
            intent="pricing",
            context="payment_terms_upi",
            english_semantic_meaning="Payment is via UPI only — you'll receive a payment link, and we confirm once we see the credit in our bank.",
            approved_hinglish_response="Payment sirf UPI se hoti hai — aapko link milega, aur jaise hi hamare bank me credit aata hai, confirm kar denge.",
            tone="transparent",
            voice_instructions="clear_process, emphasize_manual_verification",
            quality_score=0.98,
            tags=["pricing", "payment", "upi", "manual_verification"],
        ),
    ],

    "objection_handling": [
        GoldenUtterance(
            intent="objection_handling",
            context="price_too_high",
            english_semantic_meaning="I understand budget is a concern. The value you get — automated leads, follow-ups, and appointments — typically pays for itself within the first month.",
            approved_hinglish_response="Samajh sakti hoon budget concern hai. Lekin jo value milegi — automated leads, follow-ups, appointments — wo usually pehle mahine me hi recover ho jaati hai.",
            tone="empathetic",
            voice_instructions="acknowledge_first, then_value_pitch",
            quality_score=0.97,
            tags=["objection", "price", "value_based"],
        ),
        GoldenUtterance(
            intent="objection_handling",
            context="not_interested",
            english_semantic_meaning="I completely respect that. May I ask what would make you consider a solution like ours in the future?",
            approved_hinglish_response="Bilkul respect karti hoon. Ek sawal pooch sakti hoon — future me kya cheez aapko aisa solution consider karne pe majboor karegi?",
            tone="respectful",
            voice_instructions="genuine_curiosity, no_push",
            quality_score=0.96,
            tags=["objection", "not_interested", "future_pipeline"],
        ),
        GoldenUtterance(
            intent="objection_handling",
            context="already_have_provider",
            english_semantic_meaning="That's great that you have a provider! Many of our clients started with another provider and switched because we automate the full funnel — leads, follow-ups, AND appointments — in one platform.",
            approved_hinglish_response="Accha hai ki provider hai! Hamare kaafi clients pehle dusre provider pe the, par switch kiye kyunki hum poora funnel automate karte hain — leads, follow-ups, aur appointments — ek hi platform me.",
            tone="consultative",
            voice_instructions="validate_first, then_differentiate",
            quality_score=0.97,
            tags=["objection", "competitor", "differentiation"],
        ),
        GoldenUtterance(
            intent="objection_handling",
            context="need_to_think",
            english_semantic_meaning="Of course, take your time. Would it help if I sent you some information on WhatsApp so you can review at your convenience?",
            approved_hinglish_response="Zaroor, time lijiye. Kya main WhatsApp pe kuch information bhej dun taaki aap apne hisaab se review kar sakein?",
            tone="helpful",
            voice_instructions="offer_concrete_next_step",
            quality_score=0.97,
            tags=["objection", "think_time", "whatsapp_handoff"],
        ),
    ],

    "customer_confusion": [
        GoldenUtterance(
            intent="customer_confusion",
            context="who_is_this",
            english_semantic_meaning="This is Swara, an AI assistant calling from [client_name]. I'm not a human operator.",
            approved_hinglish_response="Yeh Swara hai, ek AI assistant — {client_name} ki taraf se call kiya hai. Main human operator nahi hoon.",
            tone="transparent",
            voice_instructions="clear_ai_disclosure, honest_tone",
            quality_score=0.98,
            tags=["confusion", "identity", "ai_disclosure", "compliance"],
        ),
        GoldenUtterance(
            intent="customer_confusion",
            context="what_is_this_about",
            english_semantic_meaning="I'm calling about marketing automation for your business — helping you get more leads and appointments automatically.",
            approved_hinglish_response="Main marketing automation ke baare me call kar rahi hoon — aapke business ke liye leads aur appointments automatically lane ke liye.",
            tone="clear",
            voice_instructions="simple_explanation, no_jargon",
            quality_score=0.97,
            tags=["confusion", "purpose", "simple"],
        ),
    ],

    "follow_up": [
        GoldenUtterance(
            intent="follow_up",
            context="post_demo_followup",
            english_semantic_meaning="Hi, following up on the demo we discussed. Any questions or ready to move forward?",
            approved_hinglish_response="Namaste! Demo ke baare me follow-up kar rahi thi. Koi sawal hain ya aage badhna chahenge?",
            tone="professional",
            voice_instructions="reference_previous_context",
            quality_score=0.96,
            tags=["follow_up", "post_demo"],
        ),
        GoldenUtterance(
            intent="follow_up",
            context="no_response_followup",
            english_semantic_meaning="Just checking in — did you have a chance to review the information I shared?",
            approved_hinglish_response="Bas check kar rahi thi — kya aapko wo information review karne ka time mila jo maine bheji thi?",
            tone="gentle",
            voice_instructions="soft_nudge, not_pushy",
            quality_score=0.95,
            tags=["follow_up", "gentle_nudge"],
        ),
    ],

    "closing": [
        GoldenUtterance(
            intent="closing",
            context="trial_close_appointment",
            english_semantic_meaning="Great! Let's lock in that appointment. I'll send the calendar invite shortly.",
            approved_hinglish_response="Badhiya! Appointment lock karte hain. Calendar invite turant bhej dungi.",
            tone="confident",
            voice_instructions="decisive_close, confirm_action",
            quality_score=0.97,
            tags=["closing", "trial_close", "appointment"],
        ),
        GoldenUtterance(
            intent="closing",
            context="payment_initiation",
            english_semantic_meaning="Perfect! I'll send the UPI payment link now. Once you pay, we'll activate everything within 24 hours.",
            approved_hinglish_response="Perfect! UPI payment link abhi bhej rahi hoon. Payment ke baad 24 ghante me sab activate ho jayega.",
            tone="confident",
            voice_instructions="clear_next_steps, timeline_emphasis",
            quality_score=0.98,
            tags=["closing", "payment", "activation"],
        ),
        GoldenUtterance(
            intent="closing",
            context="warm_handoff",
            english_semantic_meaning="I'll have my colleague call you tomorrow to finalize the details. Thank you for your time!",
            approved_hinglish_response="Mera colleague kal aapko call karega details finalize karne ke liye. Aapke time ke liye shukriya!",
            tone="warm",
            voice_instructions="handoff_clarity, grateful_tone",
            quality_score=0.97,
            tags=["closing", "handoff", "warm"],
        ),
    ],

    "escalation": [
        GoldenUtterance(
            intent="escalation",
            context="transfer_to_human",
            english_semantic_meaning="Let me transfer you to a human colleague who can help better.",
            approved_hinglish_response="Main aapko ek human colleague se connect kar deti hoon jo better help kar sakenge.",
            tone="helpful",
            voice_instructions="smooth_handoff, reassure",
            quality_score=0.96,
            tags=["escalation", "human_transfer"],
        ),
        GoldenUtterance(
            intent="escalation",
            context="technical_issue",
            english_semantic_meaning="I'm experiencing a technical issue. Let me arrange for someone to call you back shortly.",
            approved_hinglish_response="Mujhe thoda technical issue aa raha hai. Main arrange karti hoon ki koi aapko jaldi callback kare.",
            tone="apologetic",
            voice_instructions="own_issue, clear_callback_promise",
            quality_score=0.96,
            tags=["escalation", "technical", "callback"],
        ),
    ],

    "payment": [
        GoldenUtterance(
            intent="payment",
            context="upi_link_sent",
            english_semantic_meaning="I've sent the UPI payment link to your WhatsApp. Please complete the payment to activate your subscription.",
            approved_hinglish_response="Maine UPI payment link aapke WhatsApp pe bhej diya hai. Please payment complete karein taaki subscription activate ho sake.",
            tone="clear",
            voice_instructions="clear_action_required",
            quality_score=0.97,
            tags=["payment", "upi", "whatsapp"],
        ),
        GoldenUtterance(
            intent="payment",
            context="payment_confirmed",
            english_semantic_meaning="Payment confirmed! Your subscription is now active. Welcome to LeadGen AI!",
            approved_hinglish_response="Payment confirm ho gaya! Aapki subscription ab active hai. LeadGen AI me welcome!",
            tone="celebratory",
            voice_instructions="celebration_tone, welcoming",
            quality_score=0.98,
            tags=["payment", "confirmation", "welcome"],
        ),
    ],

    "rescheduling": [
        GoldenUtterance(
            intent="rescheduling",
            context="propose_new_time",
            english_semantic_meaning="No problem at all. When would be a better time for you?",
            approved_hinglish_response="Koi problem nahi. Aapke liye kab better time hoga?",
            tone="accommodating",
            voice_instructions="patient, open_ended",
            quality_score=0.97,
            tags=["rescheduling", "flexible"],
        ),
    ],

    "support": [
        GoldenUtterance(
            intent="support",
            context="general_help",
            english_semantic_meaning="I'm here to help! What can I assist you with today?",
            approved_hinglish_response="Main yahan help ke liye hoon! Aaj main aapki kaise madad kar sakti hoon?",
            tone="helpful",
            voice_instructions="welcoming, ready_to_help",
            quality_score=0.96,
            tags=["support", "general"],
        ),
    ],

    "goodbye": [
        GoldenUtterance(
            intent="goodbye",
            context="standard_goodbye",
            english_semantic_meaning="Thank you for your time. Have a great day!",
            approved_hinglish_response="Aapke time ke liye shukriya. Aapka din shubh ho!",
            tone="warm",
            voice_instructions="genuine_warmth, proper_signoff",
            quality_score=0.98,
            tags=["goodbye", "standard"],
        ),
        GoldenUtterance(
            intent="goodbye",
            context="callback_promise_goodbye",
            english_semantic_meaning="Thanks for your time! We'll call you back at the agreed time. Goodbye!",
            approved_hinglish_response="Time ke liye shukriya! Hum aapko agreed time pe callback karenge. Alvida!",
            tone="professional",
            voice_instructions="confirm_callback_time",
            quality_score=0.97,
            tags=["goodbye", "callback_promise"],
        ),
    ],

    "sales_discovery": [
        GoldenUtterance(
            intent="sales_discovery",
            context="pain_point_probe",
            english_semantic_meaning="What's the biggest challenge you're facing with getting new customers right now?",
            approved_hinglish_response="Abhi naye customers laane me sabse badi challenge kya hai aapke liye?",
            tone="consultative",
            voice_instructions="genuine_interest, listen_actively",
            quality_score=0.97,
            tags=["discovery", "pain_point", "consultative"],
        ),
        GoldenUtterance(
            intent="sales_discovery",
            context="current_process_inquiry",
            english_semantic_meaning="How are you currently handling lead follow-ups?",
            approved_hinglish_response="Abhi lead follow-ups kaise handle kar rahe hain aap?",
            tone="curious",
            voice_instructions="neutral_inquiry",
            quality_score=0.96,
            tags=["discovery", "process", "current_state"],
        ),
    ],

    "owner_communication": [
        GoldenUtterance(
            intent="owner_communication",
            context="call_summary_report",
            english_semantic_meaning="Boss, calling pipeline healthy hai, lekin conversion rate expected level se neeche hai. Maine root cause isolate kar liya hai aur next safest action ready hai.",
            approved_hinglish_response="Boss, calling pipeline healthy hai, lekin conversion rate expected level se neeche hai. Maine root cause isolate kar liya hai aur next safest action ready hai.",
            tone="professional",
            voice_instructions="crisp_business_report, action_oriented",
            quality_score=0.98,
            tags=["owner", "reporting", "actionable"],
        ),
        GoldenUtterance(
            intent="owner_communication",
            context="voice_quality_alert",
            english_semantic_meaning="Swara voice quality check complete. All calls clear, pronunciation accuracy 97%. One correction needed for 'Nagpur' pronunciation.",
            approved_hinglish_response="Swara voice quality check complete. Sab calls clear, pronunciation accuracy 97%. Ek correction chahiye 'Nagpur' ke pronunciation ke liye.",
            tone="informative",
            voice_instructions="clear_metrics, specific_correction",
            quality_score=0.97,
            tags=["owner", "voice_quality", "correction"],
        ),
    ],
}


# -----------------------------------------------------------------------------
# STORAGE
# -----------------------------------------------------------------------------

class GoldenUtteranceLibrary:
    """
    Curated library of approved Swara utterances.

    Features:
    - Organized by intent (Rule 8)
    - Versioned (Rule 19)
    - Quality scored (Rule 10: >= 0.95)
    - JSONL persistence for audit trail
    - Retrieval for few-shot prompting during calls
    """

    def __init__(self) -> None:
        self._library: dict[str, list[GoldenUtterance]] = {}
        self._lock = threading.RLock()
        self._jsonl_path: str | None = None
        self._loaded = False

    def _init_jsonl(self) -> str | None:
        if self._jsonl_path is not None:
            return self._jsonl_path
        base = os.getenv("GOLDEN_UTTERANCES_DATA_DIR", "data/golden_utterances")
        try:
            os.makedirs(base, exist_ok=True)
            self._jsonl_path = os.path.join(base, "golden_utterances.jsonl")
        except Exception as e:
            logger.warning(f"[golden_utterances] Cannot init JSONL path: {e}")
            self._jsonl_path = None
        return self._jsonl_path

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return

            # Load defaults
            for intent, utterances in DEFAULT_GOLDEN_UTTERANCES.items():
                self._library[intent] = list(utterances)

            # Load persisted additions/overrides
            path = self._init_jsonl()
            if path and Path(path).exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                data = json.loads(line)
                                utterance = GoldenUtterance(**data)
                                if utterance.intent not in self._library:
                                    self._library[utterance.intent] = []
                                self._library[utterance.intent].append(utterance)
                            except Exception as e:
                                logger.debug(f"[golden_utterances] Skipping malformed line: {e}")
                except Exception as e:
                    logger.warning(f"[golden_utterances] Load failed: {e}")

            self._loaded = True
            total = sum(len(v) for v in self._library.values())
            logger.info(f"[golden_utterances] Loaded {total} utterances across {len(self._library)} intents")

    def _persist(self, utterance: GoldenUtterance) -> None:
        path = self._init_jsonl()
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(utterance.to_dict(), ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning(f"[golden_utterances] Persist failed: {e}")

    # -------------------------------------------------------------------------
    # PUBLIC API
    # -------------------------------------------------------------------------

    def get(self, intent: str, context: str | None = None) -> list[GoldenUtterance]:
        """Get golden utterances for an intent, optionally filtered by context."""
        self._load()
        with self._lock:
            utterances = self._library.get(intent, [])
            if context:
                return [u for u in utterances if context in u.context]
            return list(utterances)

    def get_best(self, intent: str, context: str | None = None) -> GoldenUtterance | None:
        """Get the highest quality utterance for an intent/context."""
        utterances = self.get(intent, context)
        if not utterances:
            return None
        return max(utterances, key=lambda u: u.quality_score)

    def add(self, utterance: GoldenUtterance) -> GoldenUtterance:
        """Add a new golden utterance (must pass quality gate)."""
        if utterance.quality_score < 0.95:
            raise ValueError(f"Quality score {utterance.quality_score} below minimum 0.95 (Rule 10)")

        self._load()
        with self._lock:
            if utterance.intent not in self._library:
                self._library[utterance.intent] = []
            self._library[utterance.intent].append(utterance)
            self._persist(utterance)
            logger.info(f"[golden_utterances] Added: intent={utterance.intent} context={utterance.context} score={utterance.quality_score}")
            return utterance

    def add_from_learning_event(self, event) -> GoldenUtterance:
        """Create a golden utterance from an approved learning event (Rule 9)."""
        utterance = GoldenUtterance(
            intent=event.domain,
            context=event.context,
            english_semantic_meaning=event.intended_meaning,
            approved_hinglish_response=event.swaara_hinglish_candidate or event.pronunciation_normalized or event.original_text,
            tone=event.emotional_tone,
            voice_instructions="",  # can be enriched later
            quality_score=min(event.meaning_preservation, event.natural_hinglish, event.persona_consistency),
            source="eval_promoted",
            tags=["promoted_from_learning"],
        )
        return self.add(utterance)

    def search(self, query: str, limit: int = 20) -> list[GoldenUtterance]:
        """Search utterances by semantic meaning or response text."""
        self._load()
        query_lower = query.lower()
        with self._lock:
            results = []
            for utterances in self._library.values():
                for u in utterances:
                    if (query_lower in u.english_semantic_meaning.lower() or
                        query_lower in u.approved_hinglish_response.lower() or
                        query_lower in u.context.lower() or
                        any(query_lower in tag.lower() for tag in u.tags)):
                        results.append(u)
            # Sort by quality score descending
            results.sort(key=lambda u: u.quality_score, reverse=True)
            return results[:limit]

    def get_all_intents(self) -> list[str]:
        """Get list of all intent categories."""
        self._load()
        with self._lock:
            return sorted(self._library.keys())

    def get_contexts_for_intent(self, intent: str) -> list[str]:
        """Get all contexts available for an intent."""
        self._load()
        with self._lock:
            return sorted(set(u.context for u in self._library.get(intent, [])))

    def stats(self) -> dict[str, Any]:
        """Get library statistics."""
        self._load()
        with self._lock:
            by_intent = {intent: len(utts) for intent, utts in self._library.items()}
            by_tone = {}
            by_source = {}
            for utts in self._library.values():
                for u in utts:
                    by_tone[u.tone] = by_tone.get(u.tone, 0) + 1
                    by_source[u.source] = by_source.get(u.source, 0) + 1
            total = sum(by_intent.values())
            return {
                "total_utterances": total,
                "by_intent": by_intent,
                "by_tone": by_tone,
                "by_source": by_source,
                "version": "swara_golden_utterances_v1",
            }


# -----------------------------------------------------------------------------
# SINGLETON
# -----------------------------------------------------------------------------

_library: GoldenUtteranceLibrary | None = None


def get_golden_utterance_library() -> GoldenUtteranceLibrary:
    """Get the singleton golden utterance library."""
    global _library
    if _library is None:
        _library = GoldenUtteranceLibrary()
    return _library


# -----------------------------------------------------------------------------
# CONVENIENCE FUNCTIONS
# -----------------------------------------------------------------------------

def get_golden_response(intent: str, context: str | None = None) -> str | None:
    """Get the best golden response for an intent/context."""
    utterance = get_golden_utterance_library().get_best(intent, context)
    return utterance.approved_hinglish_response if utterance else None


def add_golden_example_from_event(event) -> GoldenUtterance:
    """Add a golden utterance from an approved learning event."""
    return get_golden_utterance_library().add_from_learning_event(event)


def format_for_few_shot(intent: str, context: str | None = None, limit: int = 3) -> str:
    """Format golden utterances for few-shot prompting in LLM calls."""
    utterances = get_golden_utterance_library().get(intent, context)[:limit]
    if not utterances:
        return ""

    examples = []
    for u in utterances:
        examples.append(f"Context: {u.context}\nUser: (implied)\nSwara: {u.approved_hinglish_response}")
    return "\n\n---\n\n".join(examples)


__all__ = [
    "GoldenUtterance",
    "GoldenUtteranceLibrary",
    "get_golden_utterance_library",
    "get_golden_response",
    "add_golden_example_from_event",
    "format_for_few_shot",
    "DEFAULT_GOLDEN_UTTERANCES",
]