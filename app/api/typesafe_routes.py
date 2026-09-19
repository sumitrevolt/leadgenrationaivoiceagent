"""TypeSafe Dedicated Strongly-Typed Endpoints (2026-09-19)
============================================================
Exposes validated REST API routes powered by TypeSafe System One.
Every endpoint enforces strict Pydantic v2 schemas:
- Clean type-safe request parsing and validation (HTTP 422 on a bad schema,
  raised by FastAPI before the handler body runs)
- Clean type-safe response contracts (`response_model` on every route)
- Fail-soft error handling: a downstream TypeSafe or bridge failure is logged
  server-side with a full traceback and reported to the caller as a plain
  HTTP 500 whose `detail` carries NO internal exception text.

Why no `str(e)` in the response: the detail string used to echo the raw
exception, which leaks provider error bodies, URLs, and stack context to the
client. The diagnostic value belongs in the log, not the HTTP response.
"""

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
    """Returns the operational status, credential state, and model alignment of TypeSafe.

    Reads `credential_state()`, which returns a `CredentialState` mapping — never a
    bare label. Compare against `state`, not against the mapping itself: comparing
    the whole dict to the string "PRESENT" is always False and silently reports an
    armed integration as absent.
    """
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
        services_ready=enabled,
        active_consumers_count=5 if enabled else 0,
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
    except Exception:
        logger.exception("TypeSafe lead qualification failed")
        raise HTTPException(status_code=500, detail="Lead qualification failed")


@router.post("/audit-message", response_model=ContentAuditResponse)
async def audit_content_endpoint(
    req: ContentAuditRequest,
    _user=Depends(require_admin),
) -> ContentAuditResponse:
    """Audits outbound emails or messages for spam, compliance, persuasion, and tone."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.audit_outbound_content(req)
    except Exception:
        logger.exception("TypeSafe content audit failed")
        raise HTTPException(status_code=500, detail="Content audit failed")


@router.post("/triage-reply", response_model=ReplyTriageResponse)
async def triage_reply_endpoint(
    req: ReplyTriageRequest,
    _user=Depends(require_admin),
) -> ReplyTriageResponse:
    """Classifies inbound prospect replies into structured intents and CRM actions."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.triage_reply(req)
    except Exception:
        logger.exception("TypeSafe reply triage failed")
        raise HTTPException(status_code=500, detail="Reply triage failed")


@router.post("/evaluate-call", response_model=CallEvaluationResponse)
async def evaluate_call_endpoint(
    req: CallEvaluationRequest,
    _user=Depends(require_admin),
) -> CallEvaluationResponse:
    """Evaluates telephonic call transcript/summary into CRM disposition and consent verification."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.evaluate_call(req)
    except Exception:
        logger.exception("TypeSafe call evaluation failed")
        raise HTTPException(status_code=500, detail="Call evaluation failed")


@router.post("/extract-value", response_model=ValueExtractionResponse)
async def extract_value_endpoint(
    req: ValueExtractionRequest,
    _user=Depends(require_admin),
) -> ValueExtractionResponse:
    """Selects best candidate matching field from unstructured text without hallucination."""
    try:
        bridge = get_typesafe_bridge()
        return bridge.extract_value(req)
    except Exception:
        logger.exception("TypeSafe value extraction failed")
        raise HTTPException(status_code=500, detail="Value extraction failed")
