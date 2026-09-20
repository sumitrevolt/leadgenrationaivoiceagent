"""
LeadGen AI — Telegram Bot & TypeSafe Management API
===================================================
REST API endpoints for:
- Bot health and connectivity
- Live orchestrator and task ledger status
- TypeSafe System One message classification and routing
- Response validation and quality scoring
- Bot-to-bot handoff coordination
- Webhook update processing with owner authentication and deduplication
- Audit logging
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.integrations.telegram_bot import get_telegram_bot, is_telegram_ready
from app.integrations.telegram_typesafe import (
    get_bot_coordinator,
    get_intent_classifier,
    get_response_validator,
)
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/telegram/bot", tags=["Telegram Bot"])


# --------------------------------------------------------------------------- #
# Request / Response Schemas
# --------------------------------------------------------------------------- #


class HealthResponse(BaseModel):
    configured: bool
    initialized: bool
    bot_username: str | None = None
    bot_id: int | None = None
    bot_name: str | None = None
    typesafe_enabled: bool
    typesafe_model: str
    orchestrator_connected: bool
    owner_usernames: list[str]


class ClassifyRequest(BaseModel):
    message: str
    user_id: str
    is_owner: bool = False


class ClassifyResponse(BaseModel):
    success: bool
    intent: str
    priority: str
    is_actionable: bool
    confidence: float
    model: str | None = None
    latency_sec: float | None = None
    error: str | None = None


class RouteRequest(BaseModel):
    message: str
    user_id: str
    is_owner: bool = False


class RouteResponse(BaseModel):
    success: bool
    handler: str
    confidence: float
    model: str | None = None
    latency_sec: float | None = None
    error: str | None = None


class ValidateRequest(BaseModel):
    response_text: str
    intent: str
    context: dict[str, Any] = Field(default_factory=dict)


class ValidateResponse(BaseModel):
    success: bool
    quality: str
    appropriate: bool
    complete: bool
    quality_score: float
    model: str | None = None
    error: str | None = None


class HandoffRequest(BaseModel):
    from_bot: str
    to_bot: str
    task_objective: str
    context: dict[str, Any] = Field(default_factory=dict)


class HandoffResponse(BaseModel):
    success: bool
    should_handoff: bool
    priority: str
    reason: str | None = None
    error: str | None = None


class SetWebhookRequest(BaseModel):
    url: str


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.get("/health", response_model=HealthResponse)
async def get_health() -> HealthResponse:
    """Get Telegram bot and TypeSafe health status."""
    bot = get_telegram_bot()
    info = bot.get_info()
    return HealthResponse(**info)


@router.get("/status")
async def get_status() -> dict[str, Any]:
    """Get live orchestrator, bot fleet, and task ledger status."""
    bot = get_telegram_bot()
    text, intent, bot_handler = bot._cmd_status()
    orch = bot._get_orchestrator()
    all_tasks = orch.store.all_tasks()

    counts: dict[str, int] = {}
    for t in all_tasks:
        st = t.status.value if hasattr(t.status, "value") else str(t.status)
        counts[st] = counts.get(st, 0) + 1

    return {
        "status": "online",
        "bot_info": bot.get_info(),
        "summary_markdown": text,
        "task_counts": counts,
        "total_tasks": len(all_tasks),
        "active_leases": orch.governor.active_leases_count,
        "kill_switch_active": orch.is_kill_switch_active(),
    }


@router.post("/classify", response_model=ClassifyResponse)
async def classify_message(request: ClassifyRequest) -> ClassifyResponse:
    """Classify incoming message intent using TypeSafe System One (jev-latest)."""
    classifier = get_intent_classifier()
    res = classifier.classify_intent(
        message_text=request.message,
        user_id=request.user_id,
        is_owner=request.is_owner,
    )
    return ClassifyResponse(
        success=res.get("success", False),
        intent=res.get("intent", "other"),
        priority=res.get("priority", "medium"),
        is_actionable=res.get("is_actionable", False),
        confidence=res.get("confidence", 0.5),
        model=res.get("model"),
        latency_sec=res.get("latency_sec"),
        error=res.get("error"),
    )


@router.post("/route", response_model=RouteResponse)
async def route_message(request: RouteRequest) -> RouteResponse:
    """Route message to one of the 9 Hermes supervisory bots using TypeSafe."""
    coordinator = get_bot_coordinator()
    res = coordinator.route_to_hermes_bot(
        message_text=request.message,
        user_id=request.user_id,
        is_owner=request.is_owner,
    )
    return RouteResponse(
        success=res.get("success", False),
        handler=res.get("handler", "pilot"),
        confidence=res.get("confidence", 0.5),
        model=res.get("model"),
        latency_sec=res.get("latency_sec"),
        error=res.get("error"),
    )


@router.post("/validate", response_model=ValidateResponse)
async def validate_response(request: ValidateRequest) -> ValidateResponse:
    """Validate bot response quality and safety using TypeSafe."""
    validator = get_response_validator()
    res = validator.validate_response(
        response_text=request.response_text,
        intent=request.intent,
        context=request.context,
    )
    return ValidateResponse(
        success=res.get("success", False),
        quality=res.get("quality", "adequate"),
        appropriate=res.get("appropriate", True),
        complete=res.get("complete", True),
        quality_score=res.get("quality_score", 2.0),
        model=res.get("model"),
        error=res.get("error"),
    )


@router.post("/handoff", response_model=HandoffResponse)
async def coordinate_handoff(request: HandoffRequest) -> HandoffResponse:
    """Evaluate and coordinate bot-to-bot handoff."""
    coordinator = get_bot_coordinator()
    res = coordinator.route_to_hermes_bot(
        message_text=request.task_objective,
        user_id="system",
        is_owner=True,
    )
    suggested_bot = res.get("handler", request.to_bot)
    should_handoff = suggested_bot != request.from_bot

    return HandoffResponse(
        success=True,
        should_handoff=should_handoff,
        priority="high" if should_handoff else "medium",
        reason=f"TypeSafe assigned '{suggested_bot}' as optimal handler for this objective",
    )


@router.post("/webhook")
async def handle_webhook(request: Request) -> dict[str, Any]:
    """Process incoming Telegram update with authentication and deduplication."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON update")

    bot = get_telegram_bot()
    result = bot.process_update(body, send_reply=True)
    return {
        "ok": result.success,
        "intent": result.intent,
        "is_owner": result.is_owner,
        "routed_bot": result.routed_bot,
        "deduplicated": result.deduplicated,
        "error": result.error,
    }


@router.get("/audit/logs")
async def get_audit_logs(limit: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    """Get recent Telegram audit log entries."""
    log_path = Path("data/telegram/audit.jsonl")
    if not log_path.exists():
        return {"logs": [], "total": 0, "limit": limit}

    entries = []
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    entries.append(json.loads(line))
    except Exception as e:
        logger.warning("[telegram_bot_api] Failed to read audit log: %s", e)

    sliced = entries[-limit:]
    return {
        "logs": sliced,
        "total": len(entries),
        "limit": limit,
    }


@router.post("/set-webhook")
async def set_webhook(payload: SetWebhookRequest) -> dict[str, Any]:
    """Set Telegram webhook URL."""
    bot = get_telegram_bot()
    if not bot.token:
        raise HTTPException(status_code=503, detail="Telegram bot token unconfigured")

    import requests

    url = f"https://api.telegram.org/bot{bot.token}/setWebhook"
    try:
        resp = requests.post(url, json={"url": payload.url}, timeout=10)
        data = resp.json() if resp.status_code == 200 else {"ok": False, "error": resp.text}
        return {"ok": data.get("ok", False), "result": data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
