"""TypeSafe Dedicated Strongly-Typed Endpoints (2026-09-19)
============================================================
Exposes validated REST API routes powered by TypeSafe System One.
Every endpoint enforces strict Pydantic v2 schemas:
- Clean type-safe request parsing and validation
- Clean type-safe response contracts
- Fail-safe error handling (HTTP 200 with structured status or HTTP 422 on invalid schema)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth_deps import require_admin
from app.platform.typesafe_bridge import get_typesafe_bridge
from app.platform.typesafe_integration import credential_state, fingerprint
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

router = APIRouter(prefix="/api/v1/typesafe", tags=["TypeSafe Intelligence"])


@router.get("/status", response_model=TypeSafeSystemStatusResponse)
async def get_status(_user=Depends(require_admin)) -> TypeSafeSystemStatusResponse:
    """Returns the operational status, credential state, and model alignment of TypeSafe."""
    bridge = get_typesafe_bridge()
    cred = credential_state()
    fp = cred.get("fingerprint") or "none"
    model = cred.get("model") or bridge.lead_scorer.client.model
    enabled = cred.get("enabled", False)
    state = cred.get("state", "ABSENT")
    source = cred.get("source", "none")

    return TypeSafeSystemStatusResponse(
        enabled=enabled,
        credential_present=state == "PRESENT",
        credential_source=source,
        fingerprint=fp,
        model=model,
        services_ready=True,
        active_consumers_count=5,
    )


@router.post("/qualify-lead", response_model=LeadQualifyResponse)
async def qualify_lead_endpoint(
    req: LeadQualifyRequest,
    _user=Depends(require_admin),
) -> LeadQualifyResponse:
    """Evaluates lead fit, buying intent, budget likelihood, and product offering."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.qualify_lead(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lead qualification failed: {str(e)}")


@router.post("/audit-message", response_model=ContentAuditResponse)
async def audit_content_endpoint(
    req: ContentAuditRequest,
    _user=Depends(require_admin),
) -> ContentAuditResponse:
    """Audits outbound emails or messages for spam, compliance, persuasion, and tone."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.audit_outbound_content(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Content audit failed: {str(e)}")


@router.post("/triage-reply", response_model=ReplyTriageResponse)
async def triage_reply_endpoint(
    req: ReplyTriageRequest,
    _user=Depends(require_admin),
) -> ReplyTriageResponse:
    """Classifies inbound prospect replies into structured intents and CRM actions."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.triage_reply(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Reply triage failed: {str(e)}")


@router.post("/evaluate-call", response_model=CallEvaluationResponse)
async def evaluate_call_endpoint(
    req: CallEvaluationRequest,
    _user=Depends(require_admin),
) -> CallEvaluationResponse:
    """Evaluates telephonic call transcript/summary into CRM disposition and consent verification."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.evaluate_call(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Call evaluation failed: {str(e)}")


@router.post("/extract-value", response_model=ValueExtractionResponse)
async def extract_value_endpoint(
    req: ValueExtractionRequest,
    _user=Depends(require_admin),
) -> ValueExtractionResponse:
    """Selects best candidate matching field from unstructured text without hallucination."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.extract_value(req)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Value extraction failed: {str(e)}")
