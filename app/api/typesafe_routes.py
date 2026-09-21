"""
TypeSafe API Routes
===================
FastAPI routes for TypeSafe decision endpoints.
Provides HTTP API for all TypeSafe decisions.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/typesafe", tags=["TypeSafe Decisions"])


# Request/Response Models
class LeadQualifyRequest(BaseModel):
    id: str
    company: str
    industry: str
    company_size: int
    budget_signal: int
    engagement_score: int
    fit_score: int
    urgency: str = "medium"


class CampaignOptimizeRequest(BaseModel):
    id: str
    name: str
    status: str
    impressions: int
    clicks: int
    conversions: int
    spend: float
    ctr: float
    conversion_rate: float
    roi: float
    days_running: int


class TaskRouteRequest(BaseModel):
    task_id: str
    type: str
    priority: str
    domain: str
    complexity: str = "medium"
    urgency: str = "normal"


class TelegramClassifyRequest(BaseModel):
    message_id: str
    text: str
    sender: str
    is_owner: bool = False


class CallRouteRequest(BaseModel):
    call_id: str
    lead_id: str
    lead_score: int
    priority: str
    campaign_type: str
    lead_industry: str
    lead_company_size: int


class SourceEvaluateRequest(BaseModel):
    name: str
    type: str
    reliability_score: int
    cost_per_lead: float
    average_lead_quality: int
    success_rate: float


class DedupeRequest(BaseModel):
    lead1_id: str
    lead1_company: str
    lead1_phone: str
    lead1_email: str
    lead1_city: str
    lead2_id: str
    lead2_company: str
    lead2_phone: str
    lead2_email: str
    lead2_city: str


class DecisionResponse(BaseModel):
    success: bool
    decision_id: str
    model: str
    result: dict[str, Any]
    confidence: float
    latency_ms: float
    timestamp: str
    source: str


class TypeSafeStatus(BaseModel):
    enabled: bool
    model: str
    pool_size: int
    credential_state: dict[str, Any]
    keys_provisioned: int


# In-memory cache for demonstration (use Redis in production)
_decision_cache: dict[str, dict] = {}


@router.get("/status", response_model=TypeSafeStatus)
async def get_typesafe_status():
    """Get TypeSafe gateway status."""
    try:
        from app.platform.typesafe_integration import get_typesafe_client
        from app.platform.key_manager import get_key_manager

        client = get_typesafe_client()
        km = get_key_manager()

        slots = km.get_all_slots()
        keys_provisioned = sum(1 for s in slots.values() if s.get("state") == "PRESENT")

        return TypeSafeStatus(
            enabled=client.enabled,
            model=client.model,
            pool_size=client.pool_size,
            credential_state=client.credential_state(),
            keys_provisioned=keys_provisioned,
        )
    except Exception as e:
        logger.error(f"Failed to get TypeSafe status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/lead", response_model=DecisionResponse)
async def decide_lead(request: LeadQualifyRequest):
    """Qualify a lead using TypeSafe."""
    try:
        from app.platform.typesafe_middleware import get_middleware

        middleware = get_middleware()
        decision = middleware.qualify_lead(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Lead qualification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/campaign", response_model=DecisionResponse)
async def decide_campaign(request: CampaignOptimizeRequest):
    """Optimize a campaign using TypeSafe."""
    try:
        from app.platform.typesafe_middleware import get_middleware

        middleware = get_middleware()
        decision = middleware.optimize_campaign(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Campaign optimization failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/task", response_model=DecisionResponse)
async def decide_task(request: TaskRouteRequest):
    """Route a task using TypeSafe."""
    try:
        from app.platform.typesafe_middleware import get_middleware

        middleware = get_middleware()
        decision = middleware.route_task(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Task routing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/telegram", response_model=DecisionResponse)
async def decide_telegram(request: TelegramClassifyRequest):
    """Classify a Telegram message using TypeSafe."""
    try:
        from app.platform.typesafe_middleware import get_middleware

        middleware = get_middleware()
        decision = middleware.classify_telegram_message(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Telegram classification failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/call", response_model=DecisionResponse)
async def decide_call(request: CallRouteRequest):
    """Route a call using TypeSafe."""
    try:
        from app.platform.typesafe_telephony import get_telephony

        telephony = get_telephony()
        decision = telephony.route_call(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Call routing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/source", response_model=DecisionResponse)
async def decide_source(request: SourceEvaluateRequest):
    """Evaluate lead source quality using TypeSafe."""
    try:
        from app.platform.typesafe_scraper import get_scraper

        scraper = get_scraper()
        decision = scraper.evaluate_source_quality(request.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Source evaluation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decide/dedup", response_model=DecisionResponse)
async def decide_dedup(request: DedupeRequest):
    """Decide deduplication using TypeSafe."""
    try:
        from app.platform.typesafe_scraper import get_scraper

        scraper = get_scraper()
        decision = scraper.decide_deduplication(request.lead1.dict(), request.lead2.dict())

        return DecisionResponse(
            success=True,
            decision_id=decision.decision_id,
            model=decision.model,
            result=decision.result,
            confidence=decision.confidence,
            latency_ms=decision.latency_ms,
            timestamp=decision.timestamp,
            source=decision.source,
        )
    except Exception as e:
        logger.error(f"Deduplication decision failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/{decision_id}")
async def get_decision(decision_id: str):
    """Get a specific decision by ID."""
    try:
        from pathlib import Path

        # Search through all decision logs
        log_dirs = [
            Path("data"),
            Path("data/revenue"),
            Path("data/typesafe"),
        ]

        for log_dir in log_dirs:
            if log_dir.exists():
                for log_file in log_dir.glob("*.jsonl"):
                    with open(log_file, "r", encoding="utf-8") as f:
                        for line in f:
                            try:
                                entry = json.loads(line.strip())
                                if entry.get("decision_id") == decision_id:
                                    return {"found": True, "decision": entry}
                            except json.JSONDecodeError:
                                continue

        return {"found": False, "decision_id": decision_id}
    except Exception as e:
        logger.error(f"Failed to get decision: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/decisions/stats")
async def get_decision_stats(
    limit: int = Query(100, ge=1, le=1000),
    hours: int = Query(24, ge=1, le=720),
):
    """Get decision statistics."""
    try:
        from datetime import datetime, timedelta
        from pathlib import Path
        import json

        cutoff = datetime.now() - timedelta(hours=hours)
        stats = {
            "total_decisions": 0,
            "typesafe_decisions": 0,
            "heuristic_decisions": 0,
            "avg_latency_ms": 0,
            "avg_confidence": 0,
            "by_type": {},
            "by_model": {},
        }

        log_files = list(Path("data").glob("*.jsonl"))
        total_latency = 0
        total_confidence = 0

        for log_file in log_files:
            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        entry_time = datetime.fromisoformat(entry.get("timestamp", "").replace("Z", "+00:00"))
                        if entry_time >= cutoff:
                            stats["total_decisions"] += 1
                            if entry.get("source") == "typesafe":
                                stats["typesafe_decisions"] += 1
                            else:
                                stats["heuristic_decisions"] += 1

                            latency = entry.get("latency_ms", 0)
                            confidence = entry.get("confidence", 0)
                            total_latency += latency
                            total_confidence += confidence

                            dec_type = entry.get("decision_type", "unknown")
                            stats["by_type"][dec_type] = stats["by_type"].get(dec_type, 0) + 1

                            model = entry.get("model", "unknown")
                            stats["by_model"][model] = stats["by_model"].get(model, 0) + 1
                    except (json.JSONDecodeError, ValueError):
                        continue

        if stats["total_decisions"] > 0:
            stats["avg_latency_ms"] = total_latency / stats["total_decisions"]
            stats["avg_confidence"] = total_confidence / stats["total_decisions"]

        return stats
    except Exception as e:
        logger.error(f"Failed to get decision stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cache/clear")
async def clear_decision_cache():
    """Clear decision cache."""
    try:
        from app.platform.typesafe_middleware import clear_decision_cache
        clear_decision_cache()
        return {"success": True, "message": "Decision cache cleared"}
    except Exception as e:
        logger.error(f"Failed to clear cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))
