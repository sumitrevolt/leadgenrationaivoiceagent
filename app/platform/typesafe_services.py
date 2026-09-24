"""TypeSafe Full-Platform AI Services (2026-09-19)
=================================================
Operationalizes the 5 core TypeSafe patterns defined in the TypeSafe skill:
1. Composite Scoring & Reusable Features: Multi-dimensional Lead Qualification
2. Verify & Escalate: Pre-flight Message QA & Compliance Guardrails
3. Route & Fill Known Arguments: Inbound Reply Triage & Intent Routing
4. Select Instead of Generate: Candidate-based Value Extraction
5. State-Conditioned Decisions: Post-Call Telephony Disposition & Verification

All services follow the fail-safe invariant:
- If TypeSafe is INERT or offline, safe heuristic fallbacks are used.
- Execution is fully traced with inputs, outputs, model, and latency.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.platform.typesafe_integration import (
    Choice,
    Noul,
    Score,
    TypeSafeClient,
    _as_float,
    get_typesafe_client,
)

logger = logging.getLogger(__name__)


def _noul_prob(answer: Any, default: float) -> float:
    """Extract a Noul probability from an untyped TypeSafe answer leaf.

    The wire format for a `Noul` question is ``{"type": "noul", "noul": <p>}``
    where ``p`` is the probability that the answer is YES.

    Do NOT write ``answer.get("noul") or answer.get("probability") or default``:
    that is a falsy-coercion bug, because a legitimate ``noul == 0.0`` — the
    model confidently answering NO — is falsy and silently falls through to
    ``default``, turning a hard NO into a maybe. ``_as_float`` narrows the leaf
    by ``isinstance`` instead of calling ``float()`` on ``Any``, so a malformed
    or missing leaf degrades to ``default`` rather than raising.
    """
    if isinstance(answer, dict):
        for key in ("noul", "probability"):
            value = _as_float(answer.get(key))
            if value is not None:
                return value
        return default
    value = _as_float(answer)
    return default if value is None else value


def _score_index(answer: Any) -> int | None:
    """Narrow a `Score` answer leaf to its integer bucket, else None.

    `dict[int, str].get(Any | None)` is a mypy arg-type error and, worse, a
    silent wrong-bucket risk: these maps are keyed by int, so an un-narrowed
    value like 1.9 would miss the key and fall through to the default bucket.
    """
    value = _as_float(answer)
    return None if value is None else int(value)


# --------------------------------------------------------------------------- #
# 1. Composite Lead Qualification & Scoring
# --------------------------------------------------------------------------- #


@dataclass
class LeadQualificationResult:
    """Multi-dimensional qualification verdict for a lead."""

    score: int  # 0 - 100
    fit_level: str  # low | medium | high | exceptional
    buying_intent: bool  # True if high-intent signals detected
    intent_confidence: float  # probability from Noul
    budget_likelihood: str  # shoestring | modest | standard | enterprise
    recommended_product: str  # marketing_suite | voice_agent | combo | unqualified
    pitch_angle: str  # suggested sales messaging hook
    is_hot_lead: bool  # qualified for immediate outreach
    metadata: dict[str, Any] = field(default_factory=dict)


class TypeSafeLeadScorer:
    """Uses TypeSafe System One for calibrated composite lead qualification."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self.client = client or get_typesafe_client()

    def qualify_lead(self, lead_data: dict[str, Any]) -> LeadQualificationResult:
        """Evaluate lead across 4 parallel dimensions using System One."""
        # Baseline heuristic fallback
        base_score = 50
        fit_level = "medium"
        buying_intent = False
        intent_prob = 0.5
        budget_likelihood = "standard"
        recommended_product = "marketing_suite"
        pitch_angle = "Automated local customer acquisition"

        business_name = lead_data.get("name") or lead_data.get("business_name", "Local Business")
        niche = lead_data.get("niche", "general")
        city = lead_data.get("city", "India")
        notes = lead_data.get("notes") or lead_data.get("description", "")

        state = {
            "business": {
                "name": business_name,
                "niche": niche,
                "city": city,
                "notes": notes,
                "has_website": bool(lead_data.get("website")),
                "has_phone": bool(lead_data.get("phone")),
            },
            "offerings": [
                {"id": "marketing_suite", "name": "AI Marketing Automation", "price": "₹1,999/mo"},
                {"id": "combo", "name": "Combo Advanced", "price": "₹5,999/mo"},
                {"id": "voice_agent", "name": "AI Voice Calling Agent", "price": "₹4,999/mo"},
            ],
        }

        questions: dict[str, Choice | Noul | Score] = {
            "fit": Score(
                question="Evaluate fit for AI marketing automation or telecalling",
                criteria=[
                    "Poor fit: not a local commercial business or irrelevant sector",
                    "Moderate fit: small business with standard customer inquiries",
                    "High fit: high inquiry volume or appointment-driven local business",
                    "Exceptional fit: fast-growing local brand needing automated outreach and calls",
                ],
            ),
            "intent": Noul(
                question="Does this lead exhibit explicit or implicit commercial buying intent for growth solutions?"
            ),
            "budget": Score(
                question="Likelihood to afford ₹1,999 to ₹5,999 per month for automated marketing",
                criteria=[
                    "Low budget: micro vendor unlikely to invest in software",
                    "Modest budget: budget conscious, fits ₹1,999 starter tier",
                    "Healthy budget: established business easily affording ₹1,999 - ₹5,999",
                    "High budget: multi-location or premium brand ready for premium combo packages",
                ],
            ),
            "product": Choice(
                question="Select the primary recommended product for this business",
                criteria={
                    "marketing_suite": "AI Automated Marketing Suite (leads, SEO, reviews, ₹1,999/mo)",
                    "voice_agent": "AI Voice Calling Agent (inbound callbacks, telecalling, ₹4,999/mo)",
                    "combo": "Combo Advanced Package (full marketing + telecaller, ₹5,999/mo)",
                    "unqualified": "Not qualified or unsuitable for AI automation",
                },
            ),
        }

        resp = self.client.system_one(state, questions)
        metadata: dict[str, Any] = {
            "model": resp.model,
            "latency_sec": resp.latency_sec,
            "success": resp.success,
        }

        if resp.success and resp.result:
            answers = resp.answers
            metadata["raw_answers"] = answers

            # 1. Fit score mapping (0 to 3) -> normalized 0-100
            fit_ans = answers.get("fit") or {}
            fit_val = fit_ans.get("score") if isinstance(fit_ans, dict) else fit_ans
            if fit_val == 0 or fit_val == "Poor fit":
                fit_level = "low"
                fit_weight = 20
            elif fit_val == 1 or fit_val == "Moderate fit":
                fit_level = "medium"
                fit_weight = 50
            elif fit_val == 2 or fit_val == "High fit":
                fit_level = "high"
                fit_weight = 80
            elif fit_val == 3 or fit_val == "Exceptional fit":
                fit_level = "exceptional"
                fit_weight = 100
            else:
                fit_weight = 60

            # 2. Intent Noul
            intent_ans = answers.get("intent") or {}
            intent_prob = _noul_prob(intent_ans, 0.5)
            buying_intent = intent_prob >= 0.65

            # 3. Budget likelihood
            budget_ans = answers.get("budget") or {}
            budget_val = budget_ans.get("score") if isinstance(budget_ans, dict) else budget_ans
            if budget_val == 0:
                budget_likelihood = "shoestring"
                budget_weight = 25
            elif budget_val == 1:
                budget_likelihood = "modest"
                budget_weight = 55
            elif budget_val == 2:
                budget_likelihood = "standard"
                budget_weight = 80
            elif budget_val == 3:
                budget_likelihood = "enterprise"
                budget_weight = 100
            else:
                budget_weight = 65

            # 4. Product choice
            prod_ans = answers.get("product") or {}
            prod_choice = prod_ans.get("choice") if isinstance(prod_ans, dict) else prod_ans
            if prod_choice in ("marketing_suite", "voice_agent", "combo", "unqualified"):
                recommended_product = str(prod_choice)

            # Composite calculation: 45% fit + 35% intent + 20% budget
            calc_score = int((fit_weight * 0.45) + (intent_prob * 100 * 0.35) + (budget_weight * 0.20))
            base_score = max(5, min(99, calc_score))

            if recommended_product == "voice_agent":
                pitch_angle = "Zero-human telecalling and instant AI inbound call response"
            elif recommended_product == "combo":
                pitch_angle = "Complete hands-off growth: automated organic marketing plus 500-min AI voice"
            else:
                pitch_angle = "Affordable ₹1,999/mo Google reviews and programmatic local lead generation"

        is_hot = base_score >= 75 and buying_intent

        return LeadQualificationResult(
            score=base_score,
            fit_level=fit_level,
            buying_intent=buying_intent,
            intent_confidence=intent_prob,
            budget_likelihood=budget_likelihood,
            recommended_product=recommended_product,
            pitch_angle=pitch_angle,
            is_hot_lead=is_hot,
            metadata=metadata,
        )


# --------------------------------------------------------------------------- #
# 2. Verify & Escalate: Pre-Flight Message QA & Compliance Guardrail
# --------------------------------------------------------------------------- #


@dataclass
class ContentQAResult:
    """Audit verdict for an outgoing message or email."""

    approved: bool
    is_spammy: bool
    compliance_violation: bool
    persuasion_score: str  # weak | acceptable | strong | compelling
    tone: str  # professional | aggressive | passive | friendly
    reasons: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


class TypeSafeContentQA:
    """Guards outbound communication with compliance and quality verification."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self.client = client or get_typesafe_client()

    def audit_outbound_message(
        self,
        subject: str,
        body: str,
        channel: str = "email",
        recipient_context: dict[str, Any] | None = None,
    ) -> ContentQAResult:
        """Inspects outbound content before sending to protect reputation and compliance."""
        state = {
            "channel": channel,
            "subject": subject,
            "body": body,
            "recipient": recipient_context or {},
            "compliance_rules": [
                "No guaranteed earnings or misleading claims",
                "Clear sender identification (LeadsGen AI)",
                "No abusive, threatening, or high-pressure language",
                "Respects TRAI and Indian commercial regulations",
            ],
        }

        questions: dict[str, Choice | Noul | Score] = {
            "spam": Noul(
                question=(
                    "Does this message contain a TRUE spam signal? Answer YES only if at "
                    "least one of these is literally present: (a) a guaranteed income or "
                    "guaranteed-result claim, (b) a deceptive or clickbait subject line, "
                    "(c) fabricated urgency, fake scarcity, or invented testimonials, "
                    "(d) a request for bank details, OTP, passwords, or upfront payment, "
                    "(e) adult, gambling, or otherwise prohibited content. Answer NO for "
                    "ordinary business outreach that identifies the sender, makes a truthful "
                    "offer, and provides an opt-out."
                )
            ),
            "compliance": Noul(
                question=(
                    "Does this message break a commercial messaging rule? Answer YES only if "
                    "at least one of these is literally present: (a) an explicit earnings or "
                    "revenue guarantee, (b) an invented or unverifiable statistic, (c) a "
                    "factually false claim, (d) no sender identification, (e) no way for the "
                    "recipient to opt out. Answer NO if the message is truthful, identifies "
                    "the sender, and offers an opt-out."
                )
            ),
            "persuasion": Score(
                question="Rate the commercial clarity and value proposition persuasiveness",
                criteria=[
                    "Weak: confusing, generic filler, no clear benefit",
                    "Acceptable: understandable offer, basic pitch",
                    "Strong: clear value proposition tailored to local business pain points",
                    "Compelling: irresistible offer with clear CTA and low friction",
                ],
            ),
            "tone": Choice(
                question="Classify the communication tone",
                criteria={
                    "professional": "Polite, helpful, and business-appropriate",
                    "friendly": "Warm, consultative, approachable",
                    "aggressive": "Pushy, overly demanding, or high-pressure",
                    "passive": "Vague, lack of confidence, unclear call to action",
                },
            ),
        }

        resp = self.client.system_one(state, questions)
        reasons: list[str] = []

        is_spammy = False
        compliance_violation = False
        persuasion = "acceptable"
        tone = "professional"

        if resp.success and resp.result:
            answers = resp.answers

            # Spam check
            spam_ans = answers.get("spam") or {}
            spam_prob = _noul_prob(spam_ans, 0.0)
            if spam_prob >= 0.60:
                is_spammy = True
                reasons.append(f"High spam score probability ({spam_prob:.2f})")

            # Compliance check
            comp_ans = answers.get("compliance") or {}
            comp_prob = _noul_prob(comp_ans, 0.0)
            if comp_prob >= 0.40:  # strict gate for compliance
                compliance_violation = True
                reasons.append(f"Potential compliance risk detected ({comp_prob:.2f})")

            # Persuasion score
            p_ans = answers.get("persuasion") or {}
            p_raw = p_ans.get("score") if isinstance(p_ans, dict) else p_ans
            persuasion_map = {0: "weak", 1: "acceptable", 2: "strong", 3: "compelling"}
            p_idx = _score_index(p_raw)
            persuasion = "acceptable" if p_idx is None else persuasion_map.get(p_idx, "acceptable")

            # Tone
            t_ans = answers.get("tone") or {}
            tone_val = t_ans.get("choice") if isinstance(t_ans, dict) else t_ans
            if tone_val in ("professional", "friendly", "aggressive", "passive"):
                tone = str(tone_val)
                if tone == "aggressive":
                    reasons.append("Tone flagged as overly aggressive")

        approved = not is_spammy and not compliance_violation and tone != "aggressive"

        return ContentQAResult(
            approved=approved,
            is_spammy=is_spammy,
            compliance_violation=compliance_violation,
            persuasion_score=persuasion,
            tone=tone,
            reasons=reasons,
            # `success`/`has_answer` are ADDITIVE metadata (no new required
            # dataclass fields, so every existing construction site keeps
            # working). They let a caller tell "the verifier ran and produced a
            # clean verdict" apart from "the API errored / timed out / returned
            # nothing" — a fail-safe auto-send gate must HOLD in the latter case
            # rather than treat an empty answer as a pass.
            metadata={
                "latency_sec": resp.latency_sec,
                "model": resp.model,
                "success": bool(resp.success),
                "has_answer": bool(resp.has_answer),
                "attempts": int(getattr(resp, "attempts", 1) or 1),
            },
        )


# --------------------------------------------------------------------------- #
# 3. Route & Fill: Inbound Reply & Lead Intent Triage
# --------------------------------------------------------------------------- #


@dataclass
class ReplyTriageResult:
    """Structured triage for an incoming customer reply."""

    intent: str  # demo_request | pricing_query | callback_requested | question | not_interested | unsubscribe | other
    is_hot: bool  # True if requires immediate human/bot takeover
    sentiment: str  # positive | neutral | skeptical | negative
    urgency: str  # immediate | same_day | routine | low
    suggested_action: str  # schedule_call | send_pricing | answer_query | suppress_dnd | archive
    metadata: dict[str, Any] = field(default_factory=dict)


class TypeSafeReplyTriage:
    """Triages inbound communications to route leads automatically."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self.client = client or get_typesafe_client()

    def triage_reply(
        self,
        reply_text: str,
        lead_context: dict[str, Any] | None = None,
    ) -> ReplyTriageResult:
        """Categorize inbound reply and determine optimal response path."""
        state = {
            "reply_text": reply_text,
            "lead": lead_context or {},
        }

        questions: dict[str, Choice | Noul | Score] = {
            "intent": Choice(
                question="Classify the prospect's reply intent",
                criteria={
                    "demo_request": "Prospect wants to see a demo or product walkthrough",
                    "pricing_query": "Prospect is asking how much it costs or plan details",
                    "callback_requested": "Prospect asked for a phone call or telephonic discussion",
                    "question": "Prospect asked a specific question about features or suitability",
                    "not_interested": "Prospect politely or firmly declined",
                    "unsubscribe": "Prospect requested to stop contact or opt-out / DND",
                    "other": "Out of office, automated reply, or unintelligible message",
                },
            ),
            "is_hot": Noul(
                question="Is this an urgent or high-intent buying inquiry that needs prompt handling?"
            ),
            "sentiment": Choice(
                question="What is the emotional sentiment of the response?",
                criteria={
                    "positive": "Interested, enthusiastic, or welcoming",
                    "neutral": "Direct, matter-of-fact inquiry",
                    "skeptical": "Doubtful, asking for proof or references",
                    "negative": "Annoyed, angry, or hostile",
                },
            ),
            "urgency": Score(
                question="Urgency of response needed",
                criteria=[
                    "Low: out of office or passive response",
                    "Routine: general inquiry, 24-hour turnaround fine",
                    "Same day: active prospect asking questions",
                    "Immediate: hot lead asking for call or ready to purchase",
                ],
            ),
        }

        resp = self.client.system_one(state, questions)

        intent = "other"
        is_hot = False
        sentiment = "neutral"
        urgency = "routine"
        suggested_action = "answer_query"

        if resp.success and resp.result:
            answers = resp.answers

            # Intent
            int_ans = answers.get("intent") or {}
            intent = str(int_ans.get("choice") if isinstance(int_ans, dict) else int_ans) or "other"

            # Hot inquiry
            hot_ans = answers.get("is_hot") or {}
            hot_prob = _noul_prob(hot_ans, 0.0)
            is_hot = hot_prob >= 0.65

            # Sentiment
            sent_ans = answers.get("sentiment") or {}
            sentiment = str(sent_ans.get("choice") if isinstance(sent_ans, dict) else sent_ans) or "neutral"

            # Urgency
            urg_ans = answers.get("urgency") or {}
            urg_raw = urg_ans.get("score") if isinstance(urg_ans, dict) else urg_ans
            urg_map = {0: "low", 1: "routine", 2: "same_day", 3: "immediate"}
            urg_idx = _score_index(urg_raw)
            urgency = "routine" if urg_idx is None else urg_map.get(urg_idx, "routine")

        # Action mapping based on typed intent
        if intent == "unsubscribe":
            suggested_action = "suppress_dnd"
        elif intent in ("callback_requested", "demo_request") or is_hot:
            suggested_action = "schedule_call"
        elif intent == "pricing_query":
            suggested_action = "send_pricing"
        elif intent == "not_interested":
            suggested_action = "archive"
        else:
            suggested_action = "answer_query"

        return ReplyTriageResult(
            intent=intent,
            is_hot=is_hot,
            sentiment=sentiment,
            urgency=urgency,
            suggested_action=suggested_action,
            metadata={"model": resp.model, "latency_sec": resp.latency_sec},
        )


# --------------------------------------------------------------------------- #
# 4. Select Instead of Generate: Candidate Value Extractor
# --------------------------------------------------------------------------- #


class TypeSafeValueExtractor:
    """Selects target values or spans from candidates instead of free-text hallucination."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self.client = client or get_typesafe_client()

    def select_best_candidate(
        self,
        context_text: str,
        field_name: str,
        candidates: list[str],
        instructions: str = "",
    ) -> str | None:
        """Picks the exact matching candidate from text using TypeSafe Choice."""
        if not candidates:
            return None
        if len(candidates) == 1:
            return candidates[0]

        criteria = {f"opt_{i}": cand for i, cand in enumerate(candidates)}
        criteria["none"] = "None of the above candidates match or apply"

        state = {
            "source_text": context_text,
            "target_field": field_name,
            "candidates": candidates,
        }

        instr = instructions or f"Select the candidate that accurately represents the {field_name} from the text"
        resp = self.client.choice(instr, state, criteria)

        if resp.success and resp.value:
            selected_key = str(resp.value)
            if selected_key.startswith("opt_"):
                try:
                    idx = int(selected_key.replace("opt_", ""))
                    return candidates[idx]
                except (ValueError, IndexError):
                    pass
            elif selected_key in criteria and selected_key != "none":
                return criteria[selected_key]

        return None


# --------------------------------------------------------------------------- #
# 5. State-Conditioned Post-Call Telephony Disposition
# --------------------------------------------------------------------------- #


@dataclass
class CallDispositionResult:
    """Post-call evaluation verdict and telemetry."""

    disposition: str  # hot_lead | callback_scheduled | follow_up_needed | not_interested | dnd_requested
    explicit_consent_given: bool
    lead_warmth: str  # cold | lukewarm | warm | hot
    next_action: str  # assign_sales_rep | send_whatsapp_deck | schedule_calendar | mark_dnd
    metadata: dict[str, Any] = field(default_factory=dict)


class TypeSafeCallEvaluator:
    """Evaluates telecaller transcripts/summaries into structured CRM actions."""

    def __init__(self, client: TypeSafeClient | None = None) -> None:
        self.client = client or get_typesafe_client()

    def evaluate_call(
        self,
        transcript_or_summary: str,
        call_metadata: dict[str, Any] | None = None,
    ) -> CallDispositionResult:
        """Extract disposition, consent, and lead warmth from call interaction."""
        state = {
            "transcript_summary": transcript_or_summary,
            "call": call_metadata or {},
        }

        questions: dict[str, Choice | Noul | Score] = {
            "disposition": Choice(
                question="Classify the final outcome of the phone call",
                criteria={
                    "hot_lead": "Customer is excited and requested immediate pricing/onboarding",
                    "callback_scheduled": "Customer agreed to a follow-up call at a later time",
                    "follow_up_needed": "Customer showed curiosity but requested info over WhatsApp/Email first",
                    "not_interested": "Customer declined the service",
                    "dnd_requested": "Customer asked not to be called again / DND",
                },
            ),
            "consent": Noul(
                question="Did the customer give clear, explicit consent for us to follow up or send information?"
            ),
            "warmth": Score(
                question="Lead warmth based on call interaction",
                criteria=[
                    "Cold: dismissive or hostile",
                    "Lukewarm: neutral, listened but showed minimal excitement",
                    "Warm: engaged, asked relevant business questions",
                    "Hot: eager to solve their marketing/calling problem right away",
                ],
            ),
        }

        resp = self.client.system_one(state, questions)

        disposition = "follow_up_needed"
        explicit_consent = False
        warmth = "lukewarm"

        if resp.success and resp.result:
            answers = resp.answers

            # Disposition
            disp_ans = answers.get("disposition") or {}
            disposition = str(disp_ans.get("choice") if isinstance(disp_ans, dict) else disp_ans) or "follow_up_needed"

            # Consent Noul
            con_ans = answers.get("consent") or {}
            con_prob = _noul_prob(con_ans, 0.0)
            explicit_consent = con_prob >= 0.50

            # Warmth
            warm_ans = answers.get("warmth") or {}
            w_raw = warm_ans.get("score") if isinstance(warm_ans, dict) else warm_ans
            w_map = {0: "cold", 1: "lukewarm", 2: "warm", 3: "hot"}
            w_idx = _score_index(w_raw)
            warmth = "lukewarm" if w_idx is None else w_map.get(w_idx, "lukewarm")

        # Derive action
        if disposition == "dnd_requested":
            action = "mark_dnd"
        elif disposition == "hot_lead":
            action = "assign_sales_rep"
        elif disposition == "callback_scheduled":
            action = "schedule_calendar"
        elif explicit_consent:
            action = "send_whatsapp_deck"
        else:
            action = "archive"

        return CallDispositionResult(
            disposition=disposition,
            explicit_consent_given=explicit_consent,
            lead_warmth=warmth,
            next_action=action,
            metadata={"model": resp.model, "latency_sec": resp.latency_sec},
        )


# Singleton factory helpers
_lead_scorer: TypeSafeLeadScorer | None = None
_content_qa: TypeSafeContentQA | None = None
_reply_triage: TypeSafeReplyTriage | None = None
_value_extractor: TypeSafeValueExtractor | None = None
_call_evaluator: TypeSafeCallEvaluator | None = None


def get_typesafe_lead_scorer() -> TypeSafeLeadScorer:
    global _lead_scorer
    if _lead_scorer is None:
        _lead_scorer = TypeSafeLeadScorer()
    return _lead_scorer


def get_typesafe_content_qa() -> TypeSafeContentQA:
    global _content_qa
    if _content_qa is None:
        _content_qa = TypeSafeContentQA()
    return _content_qa


def get_typesafe_reply_triage() -> TypeSafeReplyTriage:
    global _reply_triage
    if _reply_triage is None:
        _reply_triage = TypeSafeReplyTriage()
    return _reply_triage


def get_typesafe_value_extractor() -> TypeSafeValueExtractor:
    global _value_extractor
    if _value_extractor is None:
        _value_extractor = TypeSafeValueExtractor()
    return _value_extractor


def get_typesafe_call_evaluator() -> TypeSafeCallEvaluator:
    global _call_evaluator
    if _call_evaluator is None:
        _call_evaluator = TypeSafeCallEvaluator()
    return _call_evaluator
