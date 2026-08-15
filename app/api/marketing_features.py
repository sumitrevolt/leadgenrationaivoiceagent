"""New Marketing Features API — Review Automation, Email Drips, Appointment Reminders, Customer Health.

Mounts 4 sub-routers under /api/marketing-features with admin auth.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/marketing-features", tags=["Marketing Features"])


# ─── Review Automation ──────────────────────────────────────────────

class ReviewSeqIn(BaseModel):
    client_id: str
    business_name: str
    customer_name: str = ""
    customer_phone: str = ""
    sentiment_score: int | None = None
    trigger_event: str = "service_completed"


@router.post("/review-automation/start")
async def start_review_sequence(body: ReviewSeqIn, _user=Depends(require_admin)):
    """Start automated review request sequence for a customer."""
    from app.marketing.review_automation import start_review_sequence
    return await start_review_sequence(
        client_id=body.client_id,
        business_name=body.business_name,
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        sentiment_score=body.sentiment_score,
        trigger_event=body.trigger_event,
    )


@router.get("/review-automation/sequences")
async def list_review_sequences(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """List review request sequences."""
    from app.marketing.review_automation import list_sequences
    return {"sequences": list_sequences(client_id)}


@router.get("/review-automation/stats")
async def review_stats(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """Review sequence statistics."""
    from app.marketing.review_automation import get_sequence_stats
    return get_sequence_stats(client_id)


class ReviewReplyIn(BaseModel):
    sequence_id: str
    reply_text: str
    reply_sentiment: int | None = None


@router.post("/review-automation/reply")
async def review_reply(body: ReviewReplyIn, _user=Depends(require_admin)):
    """Handle customer reply to review request."""
    from app.marketing.review_automation import handle_reply
    return await handle_reply(
        sequence_id=body.sequence_id,
        reply_text=body.reply_text,
        reply_sentiment=body.reply_sentiment,
    )


# ─── Email Drips ───────────────────────────────────────────────────

class DripCreateIn(BaseModel):
    client_id: str
    name: str
    steps: list[dict]
    trigger: str = "manual"
    ab_test: dict | None = None


class DripStartIn(BaseModel):
    drip_id: str
    client_id: str
    customer_email: str
    customer_name: str = ""
    variables: dict | None = None


@router.post("/email-drips/create")
async def create_email_drip(body: DripCreateIn, _user=Depends(require_admin)):
    """Create a new email drip sequence."""
    from app.marketing.email_drips import create_drip
    return await create_drip(
        client_id=body.client_id,
        name=body.name,
        steps=body.steps,
        trigger=body.trigger,
        ab_test=body.ab_test,
    )


@router.post("/email-drips/start")
async def start_email_drip(body: DripStartIn, _user=Depends(require_admin)):
    """Start a drip sequence for a customer."""
    from app.marketing.email_drips import start_drip_for_customer
    return await start_drip_for_customer(
        drip_id=body.drip_id,
        client_id=body.client_id,
        customer_email=body.customer_email,
        customer_name=body.customer_name,
        variables=body.variables,
    )


@router.get("/email-drips/list")
async def list_email_drips(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """List email drip sequences."""
    from app.marketing.email_drips import list_drips
    return {"drips": list_drips(client_id)}


@router.get("/email-drips/stats")
async def email_drip_stats(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """Email drip statistics."""
    from app.marketing.email_drips import get_drip_stats
    return get_drip_stats(client_id)


@router.get("/email-drips/templates")
async def drip_templates(_user=Depends(require_admin)):
    """Available drip templates."""
    from app.marketing.email_drips import get_templates
    return {"templates": get_templates()}


# ─── Appointment Reminders ─────────────────────────────────────────

class ReminderScheduleIn(BaseModel):
    client_id: str
    business_name: str
    customer_name: str
    customer_phone: str
    appointment_time: str
    location: str = ""
    contact: str = ""
    booking_link: str = ""


@router.post("/appointments/schedule")
async def schedule_appointment(body: ReminderScheduleIn, _user=Depends(require_admin)):
    """Schedule automated appointment reminders."""
    from app.marketing.appointment_reminders import schedule_reminders
    return await schedule_reminders(
        client_id=body.client_id,
        business_name=body.business_name,
        customer_name=body.customer_name,
        customer_phone=body.customer_phone,
        appointment_time=body.appointment_time,
        location=body.location,
        contact=body.contact,
        booking_link=body.booking_link,
    )


@router.post("/appointments/{reminder_id}/status")
async def update_appointment_status(
    reminder_id: str,
    status: str,
    _user=Depends(require_admin),
):
    """Update appointment status (confirmed/completed/no_show/cancelled)."""
    from app.marketing.appointment_reminders import mark_appointment_status
    return await mark_appointment_status(reminder_id, status)


@router.get("/appointments/list")
async def list_appointments(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """List appointment reminders."""
    from app.marketing.appointment_reminders import list_reminders
    return {"reminders": list_reminders(client_id)}


@router.get("/appointments/stats")
async def appointment_stats(
    client_id: str | None = None,
    _user=Depends(require_admin),
):
    """Appointment reminder statistics."""
    from app.marketing.appointment_reminders import get_reminder_stats
    return get_reminder_stats(client_id)


# ─── Customer Health ───────────────────────────────────────────────

class HealthScoreIn(BaseModel):
    client_id: str
    engagement_data: dict | None = None
    usage_data: dict | None = None
    payment_data: dict | None = None
    satisfaction_data: dict | None = None
    growth_data: dict | None = None


@router.post("/health/score")
async def score_customer_health(body: HealthScoreIn, _user=Depends(require_admin)):
    """Calculate and record customer health score."""
    from app.marketing.customer_health import record_health
    return await record_health(
        client_id=body.client_id,
        engagement_data=body.engagement_data,
        usage_data=body.usage_data,
        payment_data=body.payment_data,
        satisfaction_data=body.satisfaction_data,
        growth_data=body.growth_data,
    )


@router.get("/health/client/{client_id}")
async def client_health(client_id: str, _user=Depends(require_admin)):
    """Get latest health score for a client."""
    from app.marketing.customer_health import get_client_health
    health = get_client_health(client_id)
    if not health:
        raise HTTPException(404, "No health data found")
    return health


@router.get("/health/all")
async def all_health(_user=Depends(require_admin)):
    """Health scores for all clients."""
    from app.marketing.customer_health import get_all_health
    return {"health": get_all_health()}


@router.get("/health/summary")
async def health_summary(_user=Depends(require_admin)):
    """Aggregate health summary."""
    from app.marketing.customer_health import get_health_summary
    return get_health_summary()
