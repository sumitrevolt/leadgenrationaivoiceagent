"""
Pydantic request/response models for the ML Training API.

Extracted verbatim from app/api/ml_training.py (behaviour-preserving).
"""

from pydantic import BaseModel


class TrainingConfigUpdate(BaseModel):
    nightly_training_hour: int | None = None
    nightly_training_minute: int | None = None
    weekly_training_enabled: bool | None = None
    min_conversations_for_training: int | None = None


class ManualTrainingRequest(BaseModel):
    training_type: str = "nightly"  # "nightly" or "weekly"
    tenant_id: str | None = "default"


class FeedbackSubmission(BaseModel):
    conversation_id: str
    outcome: str  # "appointment_booked", "callback", "interested", "not_interested", etc.
    call_duration: float
    notes: str | None = None
    appointment_booked: bool = False
    callback_scheduled: bool = False


class BrainTrainingRequest(BaseModel):
    brain_type: str = "all"  # "all", "sub_agent", "voice_agent", "production"
    trigger: str = "scheduled"  # "scheduled", "behavior", "error_rate", "user_feedback"
    force: bool = False


class BrainFeedbackRequest(BaseModel):
    brain_type: str
    action: str
    accepted: bool
    feedback_score: float | None = None


class VertexTrainRequest(BaseModel):
    brain_type: str = "all"  # "all", "sub_agent", "voice_agent", "production"
    priority: int = 3  # 1=CRITICAL, 2=HIGH, 3=NORMAL, 4=LOW, 5=MAINTENANCE
    trigger_reason: str = "manual"


class VertexBehaviorRecord(BaseModel):
    brain_type: str
    action: str
    success: bool
    latency_ms: int
    user_accepted: bool | None = None
