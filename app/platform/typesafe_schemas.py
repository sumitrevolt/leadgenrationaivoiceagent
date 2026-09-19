"""TypeSafe Strict Type Contracts & Schemas (2026-09-19)
======================================================
Provides complete, end-to-end Pydantic models and type definitions across
all data flows, request/response models, and error boundaries.

Eliminates untyped dict manipulation across TypeSafe operations:
- Request/Response validation
- Strongly typed Enums for dispositions, intents, fit levels, and channels
- Calibrated probability and confidence types
- Consistent, predictable error envelopes (fail-safe)
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Strongly Typed Domain Enums
# --------------------------------------------------------------------------- #


class FitLevelEnum(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    EXCEPTIONAL = "exceptional"


class BudgetLikelihoodEnum(str, Enum):
    SHOESTRING = "shoestring"
    MODEST = "modest"
    STANDARD = "standard"
    ENTERPRISE = "enterprise"


class ProductOfferingEnum(str, Enum):
    MARKETING_SUITE = "marketing_suite"
    VOICE_AGENT = "voice_agent"
    COMBO = "combo"
    UNQUALIFIED = "unqualified"


class ToneEnum(str, Enum):
    PROFESSIONAL = "professional"
    FRIENDLY = "friendly"
    AGGRESSIVE = "aggressive"
    PASSIVE = "passive"


class PersuasionScoreEnum(str, Enum):
    WEAK = "weak"
    ACCEPTABLE = "acceptable"
    STRONG = "strong"
    COMPELLING = "compelling"


class ReplyIntentEnum(str, Enum):
    DEMO_REQUEST = "demo_request"
    PRICING_QUERY = "pricing_query"
    CALLBACK_REQUESTED = "callback_requested"
    QUESTION = "question"
    NOT_INTERESTED = "not_interested"
    UNSUBSCRIBE = "unsubscribe"
    OTHER = "other"


class SentimentEnum(str, Enum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    SKEPTICAL = "skeptical"
    NEGATIVE = "negative"


class UrgencyEnum(str, Enum):
    LOW = "low"
    ROUTINE = "routine"
    SAME_DAY = "same_day"
    IMMEDIATE = "immediate"


class CallDispositionEnum(str, Enum):
    HOT_LEAD = "hot_lead"
    CALLBACK_SCHEDULED = "callback_scheduled"
    FOLLOW_UP_NEEDED = "follow_up_needed"
    NOT_INTERESTED = "not_interested"
    DND_REQUESTED = "dnd_requested"


class LeadWarmthEnum(str, Enum):
    COLD = "cold"
    LUKEWARM = "lukewarm"
    WARM = "warm"
    HOT = "hot"


# --------------------------------------------------------------------------- #
# Request Schemas
# --------------------------------------------------------------------------- #


class LeadQualifyRequest(BaseModel):
    """Payload for composite lead qualification."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., description="Business or lead contact name")
    niche: str = Field("general", description="Industry or business category")
    city: str = Field("India", description="Operating city or region")
    phone: str | None = Field(None, description="Phone number")
    website: str | None = Field(None, description="Website URL if scraped")
    notes: str | None = Field(None, description="Contextual notes or scraped description")


class ContentAuditRequest(BaseModel):
    """Payload for auditing outbound communication."""

    model_config = ConfigDict(extra="ignore")

    subject: str = Field(..., description="Email/message subject or header")
    body: str = Field(..., description="Message body to inspect")
    channel: str = Field("email", description="Channel: email | whatsapp | sms")
    recipient_email: str | None = Field(None, description="Recipient email address")
    recipient_name: str | None = Field(None, description="Recipient contact name")


class ReplyTriageRequest(BaseModel):
    """Payload for incoming message triage."""

    model_config = ConfigDict(extra="ignore")

    message_body: str = Field(..., description="Inbound response or email content")
    channel: str = Field("email", description="Inbound communication channel")
    lead_id: str | None = Field(None, description="Associated Lead ID if known")
    lead_name: str | None = Field(None, description="Prospect business name")


class CallEvaluationRequest(BaseModel):
    """Payload for post-call voice disposition."""

    model_config = ConfigDict(extra="ignore")

    transcript_or_summary: str = Field(..., description="Call transcript or AI call summary")
    lead_id: str | None = Field(None, description="Lead ID")
    call_duration_seconds: int = Field(0, description="Duration of call in seconds")
    telephony_provider: str = Field("tata_smartflo", description="tata_smartflo or vobiz")


class ValueExtractionRequest(BaseModel):
    """Payload for candidate-based entity extraction."""

    model_config = ConfigDict(extra="ignore")

    source_text: str = Field(..., description="Unstructured source text")
    field_name: str = Field(..., description="Target property name to extract")
    candidates: list[str] = Field(..., min_length=1, description="Candidate values to select from")
    instructions: str = Field("", description="Optional prompt guidance")


# --------------------------------------------------------------------------- #
# Response Schemas (Strict End-to-End Contracts)
# --------------------------------------------------------------------------- #


class LeadQualifyResponse(BaseModel):
    """Structured response for lead qualification."""

    score: int = Field(..., ge=0, le=100, description="0-100 composite score")
    fit_level: FitLevelEnum
    buying_intent: bool
    intent_confidence: float = Field(..., ge=0.0, le=1.0)
    budget_likelihood: BudgetLikelihoodEnum
    recommended_product: ProductOfferingEnum
    pitch_angle: str
    is_hot_lead: bool
    typesafe_active: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContentAuditResponse(BaseModel):
    """Structured response for content QA."""

    approved: bool
    is_spammy: bool
    compliance_violation: bool
    persuasion_score: PersuasionScoreEnum
    tone: ToneEnum
    reasons: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ReplyTriageResponse(BaseModel):
    """Structured response for reply triage."""

    intent: ReplyIntentEnum
    is_hot: bool
    sentiment: SentimentEnum
    urgency: UrgencyEnum
    suggested_action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class CallEvaluationResponse(BaseModel):
    """Structured response for call evaluation."""

    disposition: CallDispositionEnum
    explicit_consent_given: bool
    lead_warmth: LeadWarmthEnum
    next_action: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValueExtractionResponse(BaseModel):
    """Structured response for candidate selection."""

    selected_candidate: str | None
    field_name: str
    success: bool
    metadata: dict[str, Any] = Field(default_factory=dict)


class TypeSafeSystemStatusResponse(BaseModel):
    """Health and configuration status of TypeSafe integration."""

    enabled: bool
    credential_present: bool
    credential_source: str
    fingerprint: str
    model: str
    services_ready: bool
    active_consumers_count: int
