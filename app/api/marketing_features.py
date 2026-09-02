"""Marketing Features API — reviews, drips, reminders, health, forms, proposals.

Mounts under /api/marketing-features with admin auth. FORM_BUILDER and
PROPOSAL_BUILDER stay INERT (503) until the matching env flag is 1.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/api/marketing-features", tags=["Marketing Features"])


def _flag_on(name: str) -> bool:
    return (os.getenv(name, "0") or "0").strip().lower() in ("1", "true", "yes", "on")


def _require_env_flag(name: str) -> Callable[[], None]:
    def _dep() -> None:
        if not _flag_on(name):
            raise HTTPException(status_code=503, detail=f"{name} disabled ({name}=0).")

    return _dep


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


# ─── Form/Survey Builder ─────────────────────────────────────────


class FormCreateIn(BaseModel):
    client_id: str
    name: str
    steps: list[dict]
    description: str = ""
    settings: dict | None = None


class FormTemplateIn(BaseModel):
    client_id: str
    template_id: str
    customizations: dict | None = None


class FormResponseIn(BaseModel):
    form_id: str
    client_id: str
    answers: dict
    submitter_name: str = ""
    submitter_phone: str = ""
    submitter_email: str = ""


@router.post("/forms/create", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))])
async def create_form_endpoint(body: FormCreateIn, _user=Depends(require_admin)):
    """Create a new form/survey."""
    from app.marketing.form_builder import create_form

    return await create_form(
        client_id=body.client_id,
        name=body.name,
        steps=body.steps,
        description=body.description,
        settings=body.settings,
    )


@router.post(
    "/forms/create-from-template", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))]
)
async def create_form_from_template(body: FormTemplateIn, _user=Depends(require_admin)):
    """Create a form from a pre-built template."""
    from app.marketing.form_builder import create_from_template

    return await create_from_template(
        client_id=body.client_id,
        template_id=body.template_id,
        customizations=body.customizations,
    )


@router.post("/forms/submit", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))])
async def submit_form(body: FormResponseIn, _user=Depends(require_admin)):
    """Submit a form response."""
    from app.marketing.form_builder import submit_response

    return await submit_response(
        form_id=body.form_id,
        client_id=body.client_id,
        answers=body.answers,
        submitter_name=body.submitter_name,
        submitter_phone=body.submitter_phone,
        submitter_email=body.submitter_email,
    )


@router.get("/forms/list", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))])
async def list_forms_endpoint(client_id: str | None = None, _user=Depends(require_admin)):
    """List forms."""
    from app.marketing.form_builder import list_forms

    return {"forms": list_forms(client_id)}


@router.get("/forms/stats", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))])
async def form_stats(client_id: str | None = None, _user=Depends(require_admin)):
    """Form statistics."""
    from app.marketing.form_builder import get_form_stats

    return get_form_stats(client_id)


@router.get("/forms/templates", dependencies=[Depends(_require_env_flag("FORM_BUILDER"))])
async def form_templates(_user=Depends(require_admin)):
    """Available form templates."""
    from app.marketing.form_builder import get_templates

    return {"templates": get_templates()}


# ─── Proposal/Quote Builder ───────────────────────────────────────


class ProposalGenIn(BaseModel):
    client_id: str
    business_name: str
    client_name: str
    template_id: str = "marketing_starter"
    custom_sections: list[dict] | None = None
    custom_pricing: str = ""
    validity_days: int = 30


@router.post("/proposals/generate", dependencies=[Depends(_require_env_flag("PROPOSAL_BUILDER"))])
async def generate_proposal_endpoint(body: ProposalGenIn, _user=Depends(require_admin)):
    """Generate a proposal from template."""
    from app.marketing.proposal_builder import generate_proposal

    return await generate_proposal(
        client_id=body.client_id,
        business_name=body.business_name,
        client_name=body.client_name,
        template_id=body.template_id,
        custom_sections=body.custom_sections,
        custom_pricing=body.custom_pricing,
        validity_days=body.validity_days,
    )


@router.post(
    "/proposals/{proposal_id}/status", dependencies=[Depends(_require_env_flag("PROPOSAL_BUILDER"))]
)
async def update_proposal_status(proposal_id: str, status: str, _user=Depends(require_admin)):
    """Update proposal status (draft/sent/accepted/expired/declined)."""
    from app.marketing.proposal_builder import update_proposal_status

    return await update_proposal_status(proposal_id, status)


@router.get("/proposals/list", dependencies=[Depends(_require_env_flag("PROPOSAL_BUILDER"))])
async def list_proposals_endpoint(client_id: str | None = None, _user=Depends(require_admin)):
    """List proposals."""
    from app.marketing.proposal_builder import list_proposals

    return {"proposals": list_proposals(client_id)}


@router.get("/proposals/stats", dependencies=[Depends(_require_env_flag("PROPOSAL_BUILDER"))])
async def proposal_stats(client_id: str | None = None, _user=Depends(require_admin)):
    """Proposal statistics."""
    from app.marketing.proposal_builder import get_proposal_stats

    return get_proposal_stats(client_id)


@router.get("/proposals/templates", dependencies=[Depends(_require_env_flag("PROPOSAL_BUILDER"))])
async def proposal_templates(_user=Depends(require_admin)):
    """Available proposal templates."""
    from app.marketing.proposal_builder import get_templates

    return {"templates": get_templates()}
