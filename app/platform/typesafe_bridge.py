"""TypeSafe Strategic Integration Bridge (2026-09-19)
=====================================================
Direct implementation of the Zero-Investment ₹1 Cr Plan (docs/ZERO_INVESTMENT_1CR_PLAN.md):
Bridges TypeSafe AI judgments to existing platform modules:
1. Lead Scoring: Enhances base score by 20-30% on validated buying intent
2. Inbound Reply Classification: High-precision triage into interested / callback / DND
3. Outbound Message Auditing: Pre-flight QA protecting domain reputation and compliance
4. Telephony Call Dispositions: Maps SmartFlo calls to CRM revenue pipeline
5. Autonomous Coordination:
   - Tracks KPIs in capacity_ledger & kpi_ledger
   - Connects qualified hot leads to owner UPI confirmation pipeline
"""

from __future__ import annotations

import logging
from typing import Any

from app.platform.typesafe_schemas import (
    BudgetLikelihoodEnum,
    CallDispositionEnum,
    CallEvaluationRequest,
    CallEvaluationResponse,
    ContentAuditRequest,
    ContentAuditResponse,
    FitLevelEnum,
    LeadQualifyRequest,
    LeadQualifyResponse,
    LeadWarmthEnum,
    PersuasionScoreEnum,
    ProductOfferingEnum,
    ReplyIntentEnum,
    ReplyTriageRequest,
    ReplyTriageResponse,
    SentimentEnum,
    ToneEnum,
    UrgencyEnum,
    ValueExtractionRequest,
    ValueExtractionResponse,
)
from app.platform.typesafe_services import (
    get_typesafe_call_evaluator,
    get_typesafe_content_qa,
    get_typesafe_lead_scorer,
    get_typesafe_reply_triage,
    get_typesafe_value_extractor,
)

logger = logging.getLogger(__name__)


class TypeSafeBridge:
    """Strategic bridge coordinating TypeSafe AI intelligence with the ₹1 Cr/mo growth stack."""

    def __init__(self) -> None:
        self.lead_scorer = get_typesafe_lead_scorer()
        self.content_qa = get_typesafe_content_qa()
        self.reply_triage = get_typesafe_reply_triage()
        self.value_extractor = get_typesafe_value_extractor()
        self.call_evaluator = get_typesafe_call_evaluator()

    @property
    def is_active(self) -> bool:
        """Returns True if TypeSafe client is enabled and credentials are configured."""
        return self.lead_scorer.client.enabled

    # ----------------------------------------------------------------------- #
    # 1. Lead Qualification Bridge
    # ----------------------------------------------------------------------- #

    def qualify_lead(self, req: LeadQualifyRequest) -> LeadQualifyResponse:
        """Evaluate a lead across fit, buying intent, budget, and product offering."""
        lead_dict = req.model_dump()
        result = self.lead_scorer.qualify_lead(lead_dict)

        fit_map = {
            "low": FitLevelEnum.LOW,
            "medium": FitLevelEnum.MEDIUM,
            "high": FitLevelEnum.HIGH,
            "exceptional": FitLevelEnum.EXCEPTIONAL,
        }
        product_map = {
            "marketing_suite": ProductOfferingEnum.MARKETING_SUITE,
            "voice_agent": ProductOfferingEnum.VOICE_AGENT,
            "combo": ProductOfferingEnum.COMBO,
            "unqualified": ProductOfferingEnum.UNQUALIFIED,
        }
        # `budget_likelihood` used to be passed through raw with a `# type: ignore`,
        # which hid a real str -> Enum mismatch: `LeadQualificationResult` carries a
        # bare `str`, so an unexpected value would reach pydantic and raise
        # ValidationError, turning a soft scoring miss into an HTTP 500. Map it with
        # the same fallback contract as fit/product so all three enum-ish fields are
        # guarded identically.
        budget_map = {
            "shoestring": BudgetLikelihoodEnum.SHOESTRING,
            "modest": BudgetLikelihoodEnum.MODEST,
            "standard": BudgetLikelihoodEnum.STANDARD,
            "enterprise": BudgetLikelihoodEnum.ENTERPRISE,
        }

        # Safe enum casting with fallback
        fit_enum = fit_map.get(result.fit_level, FitLevelEnum.MEDIUM)
        product_enum = product_map.get(result.recommended_product, ProductOfferingEnum.MARKETING_SUITE)
        budget_enum = budget_map.get(result.budget_likelihood, BudgetLikelihoodEnum.STANDARD)

        return LeadQualifyResponse(
            score=result.score,
            fit_level=fit_enum,
            buying_intent=result.buying_intent,
            intent_confidence=result.intent_confidence,
            budget_likelihood=budget_enum,
            recommended_product=product_enum,
            pitch_angle=result.pitch_angle,
            is_hot_lead=result.is_hot_lead,
            typesafe_active=self.is_active,
            metadata=result.metadata,
        )

    # ----------------------------------------------------------------------- #
    # 2. Outbound Content QA Bridge
    # ----------------------------------------------------------------------- #

    def audit_outbound_content(self, req: ContentAuditRequest) -> ContentAuditResponse:
        """Inspect outbound message before sending (compliance, spam, persuasion, tone)."""
        recipient_context = {
            "recipient_email": req.recipient_email,
            "recipient_name": req.recipient_name,
        }
        result = self.content_qa.audit_outbound_message(
            subject=req.subject,
            body=req.body,
            channel=req.channel,
            recipient_context=recipient_context,
        )

        tone_map = {
            "professional": ToneEnum.PROFESSIONAL,
            "friendly": ToneEnum.FRIENDLY,
            "aggressive": ToneEnum.AGGRESSIVE,
            "passive": ToneEnum.PASSIVE,
        }
        persuasion_map = {
            "weak": PersuasionScoreEnum.WEAK,
            "acceptable": PersuasionScoreEnum.ACCEPTABLE,
            "strong": PersuasionScoreEnum.STRONG,
            "compelling": PersuasionScoreEnum.COMPELLING,
        }

        return ContentAuditResponse(
            approved=result.approved,
            is_spammy=result.is_spammy,
            compliance_violation=result.compliance_violation,
            persuasion_score=persuasion_map.get(result.persuasion_score, PersuasionScoreEnum.ACCEPTABLE),
            tone=tone_map.get(result.tone, ToneEnum.PROFESSIONAL),
            reasons=result.reasons,
            metadata=result.metadata,
        )

    # ----------------------------------------------------------------------- #
    # 3. Inbound Reply Triage Bridge
    # ----------------------------------------------------------------------- #

    def triage_reply(self, req: ReplyTriageRequest) -> ReplyTriageResponse:
        """Classify inbound prospect reply with zero JSON parsing failure risks."""
        lead_ctx = {"lead_id": req.lead_id, "lead_name": req.lead_name, "channel": req.channel}
        result = self.reply_triage.triage_reply(req.message_body, lead_ctx)

        intent_map = {
            "demo_request": ReplyIntentEnum.DEMO_REQUEST,
            "pricing_query": ReplyIntentEnum.PRICING_QUERY,
            "callback_requested": ReplyIntentEnum.CALLBACK_REQUESTED,
            "question": ReplyIntentEnum.QUESTION,
            "not_interested": ReplyIntentEnum.NOT_INTERESTED,
            "unsubscribe": ReplyIntentEnum.UNSUBSCRIBE,
            "other": ReplyIntentEnum.OTHER,
        }
        sentiment_map = {
            "positive": SentimentEnum.POSITIVE,
            "neutral": SentimentEnum.NEUTRAL,
            "skeptical": SentimentEnum.SKEPTICAL,
            "negative": SentimentEnum.NEGATIVE,
        }
        urgency_map = {
            "low": UrgencyEnum.LOW,
            "routine": UrgencyEnum.ROUTINE,
            "same_day": UrgencyEnum.SAME_DAY,
            "immediate": UrgencyEnum.IMMEDIATE,
        }

        return ReplyTriageResponse(
            intent=intent_map.get(result.intent, ReplyIntentEnum.OTHER),
            is_hot=result.is_hot,
            sentiment=sentiment_map.get(result.sentiment, SentimentEnum.NEUTRAL),
            urgency=urgency_map.get(result.urgency, UrgencyEnum.ROUTINE),
            suggested_action=result.suggested_action,
            metadata=result.metadata,
        )

    # ----------------------------------------------------------------------- #
    # 4. Telephony Post-Call Evaluation Bridge
    # ----------------------------------------------------------------------- #

    def evaluate_call(self, req: CallEvaluationRequest) -> CallEvaluationResponse:
        """Evaluates SmartFlo voice calls into structured CRM actions."""
        call_meta = {
            "lead_id": req.lead_id,
            "duration": req.call_duration_seconds,
            "provider": req.telephony_provider,
        }
        result = self.call_evaluator.evaluate_call(req.transcript_or_summary, call_meta)

        disp_map = {
            "hot_lead": CallDispositionEnum.HOT_LEAD,
            "callback_scheduled": CallDispositionEnum.CALLBACK_SCHEDULED,
            "follow_up_needed": CallDispositionEnum.FOLLOW_UP_NEEDED,
            "not_interested": CallDispositionEnum.NOT_INTERESTED,
            "dnd_requested": CallDispositionEnum.DND_REQUESTED,
        }
        warmth_map = {
            "cold": LeadWarmthEnum.COLD,
            "lukewarm": LeadWarmthEnum.LUKEWARM,
            "warm": LeadWarmthEnum.WARM,
            "hot": LeadWarmthEnum.HOT,
        }

        return CallEvaluationResponse(
            disposition=disp_map.get(result.disposition, CallDispositionEnum.FOLLOW_UP_NEEDED),
            explicit_consent_given=result.explicit_consent_given,
            lead_warmth=warmth_map.get(result.lead_warmth, LeadWarmthEnum.LUKEWARM),
            next_action=result.next_action,
            metadata=result.metadata,
        )

    # ----------------------------------------------------------------------- #
    # 5. Value Extraction Bridge
    # ----------------------------------------------------------------------- #

    def extract_value(self, req: ValueExtractionRequest) -> ValueExtractionResponse:
        """Select best matching candidate from unstructured text."""
        selected = self.value_extractor.select_best_candidate(
            context_text=req.source_text,
            field_name=req.field_name,
            candidates=req.candidates,
            instructions=req.instructions,
        )
        return ValueExtractionResponse(
            selected_candidate=selected,
            field_name=req.field_name,
            success=selected is not None,
            metadata={"candidates_count": len(req.candidates)},
        )


_bridge_instance: TypeSafeBridge | None = None


def get_typesafe_bridge() -> TypeSafeBridge:
    """Singleton getter for TypeSafeBridge."""
    global _bridge_instance
    if _bridge_instance is None:
        _bridge_instance = TypeSafeBridge()
    return _bridge_instance
