"""Authenticated, strongly typed TypeSafe System One endpoints."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import require_admin
from app.platform.typesafe_bridge import get_typesafe_bridge
from app.platform.typesafe_integration import credential_state
from app.platform.typesafe_schemas import (
    CallEvaluationRequest,
    CallEvaluationResponse,
    ContentAuditRequest,
    ContentAuditResponse,
    LeadQualifyRequest,
    LeadQualifyResponse,
    ReplyTriageRequest,
    ReplyTriageResponse,
    TypeSafeSystemStatusResponse,
    ValueExtractionRequest,
    ValueExtractionResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/typesafe", tags=["TypeSafe Intelligence"])


@router.get("/status", response_model=TypeSafeSystemStatusResponse)
async def get_status(_user=Depends(require_admin)) -> TypeSafeSystemStatusResponse:
    """Report credential truth and consumers whose own clients are enabled."""
    bridge = get_typesafe_bridge()
    cred = credential_state()
    state = cred.get("state", "ABSENT")
    enabled = bool(cred.get("enabled", False))
    active_count = 0

    if enabled:
        services = (
            bridge.lead_scorer,
            bridge.content_qa,
            bridge.reply_triage,
            bridge.value_extractor,
            bridge.call_evaluator,
        )
        active_count += sum(
            1 for service in services if getattr(service, "client", None) and service.client.enabled
        )
        try:
            from app.platform.typesafe_executor import get_executor

            if get_executor().client.enabled:
                active_count += 1
        except Exception as exc:
            logger.debug("TypeSafe executor status probe skipped: %s", exc)
        try:
            from app.integrations.telegram_typesafe import (
                get_bot_coordinator,
                get_intent_classifier,
                get_response_validator,
            )

            telegram_consumers = (
                get_intent_classifier(),
                get_bot_coordinator(),
                get_response_validator(),
            )
            for consumer in telegram_consumers:
                client = getattr(consumer, "client", None)
                if client and client.enabled:
                    active_count += 1
        except Exception as exc:
            logger.debug("TypeSafe Telegram consumer status probe skipped: %s", exc)

    return TypeSafeSystemStatusResponse(
        enabled=enabled,
        credential_present=state == "PRESENT",
        credential_source=cred.get("source", "none"),
        fingerprint=cred.get("fingerprint") or "none",
        model=cred.get("model") or bridge.lead_scorer.client.model,
        services_ready=enabled,
        active_consumers_count=active_count,
    )


@router.post("/qualify-lead", response_model=LeadQualifyResponse)
async def qualify_lead_endpoint(
    req: LeadQualifyRequest,
    _user=Depends(require_admin),
) -> LeadQualifyResponse:
    try:
        return get_typesafe_bridge().qualify_lead(req)
    except Exception:
        logger.exception("TypeSafe lead qualification failed")
        raise HTTPException(status_code=500, detail="Lead qualification failed")


@router.post("/audit-message", response_model=ContentAuditResponse)
async def audit_content_endpoint(
    req: ContentAuditRequest,
    _user=Depends(require_admin),
) -> ContentAuditResponse:
    try:
        return get_typesafe_bridge().audit_outbound_content(req)
    except Exception:
        logger.exception("TypeSafe content audit failed")
        raise HTTPException(status_code=500, detail="Content audit failed")


@router.post("/triage-reply", response_model=ReplyTriageResponse)
async def triage_reply_endpoint(
    req: ReplyTriageRequest,
    _user=Depends(require_admin),
) -> ReplyTriageResponse:
    try:
        return get_typesafe_bridge().triage_reply(req)
    except Exception:
        logger.exception("TypeSafe reply triage failed")
        raise HTTPException(status_code=500, detail="Reply triage failed")


@router.post("/evaluate-call", response_model=CallEvaluationResponse)
async def evaluate_call_endpoint(
    req: CallEvaluationRequest,
    _user=Depends(require_admin),
) -> CallEvaluationResponse:
    try:
        return get_typesafe_bridge().evaluate_call(req)
    except Exception:
        logger.exception("TypeSafe call evaluation failed")
        raise HTTPException(status_code=500, detail="Call evaluation failed")


@router.post("/extract-value", response_model=ValueExtractionResponse)
async def extract_value_endpoint(
    req: ValueExtractionRequest,
    _user=Depends(require_admin),
) -> ValueExtractionResponse:
    try:
        return get_typesafe_bridge().extract_value(req)
    except Exception:
        logger.exception("TypeSafe value extraction failed")
        raise HTTPException(status_code=500, detail="Value extraction failed")
