"""
Health and Observability API Endpoints
Production monitoring and health checks
"""
from fastapi import APIRouter, Response
from datetime import datetime
from typing import Dict, Any
import asyncio
import os

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint
    Used by Cloud Run for liveness probes
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
    }


@router.get("/health/ready")
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness check - verifies all dependencies are accessible
    Used by Cloud Run for readiness probes
    """
    checks = {}
    overall_healthy = True
    
    # Check database
    try:
        from sqlalchemy import text
        from app.models.base import async_session
        
        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = {"status": "healthy"}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)[:100]}
        overall_healthy = False
    
    # Check Redis
    try:
        import redis.asyncio as aioredis
        
        redis_client = aioredis.from_url(settings.redis_url)
        await redis_client.ping()
        await redis_client.close()
        checks["redis"] = {"status": "healthy"}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)[:100]}
        overall_healthy = False
    
    # Check LLM availability
    try:
        if settings.gemini_api_key or settings.google_cloud_project_id:
            checks["llm"] = {"status": "healthy", "provider": "gemini"}
        elif settings.openai_api_key:
            checks["llm"] = {"status": "healthy", "provider": "openai"}
        else:
            checks["llm"] = {"status": "degraded", "error": "No LLM configured"}
    except Exception as e:
        checks["llm"] = {"status": "unhealthy", "error": str(e)[:100]}
    
    status = "healthy" if overall_healthy else "unhealthy"
    
    return {
        "status": status,
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }


@router.get("/health/live")
async def liveness_check():
    """
    Simple liveness check
    Returns 200 if the process is running
    """
    return Response(status_code=200, content="OK")


@router.get("/api/v1/status")
async def api_status() -> Dict[str, Any]:
    """
    Detailed API status with metrics
    """
    from app.llm.vertex_client import get_vertex_client
    
    # Get LLM usage stats
    try:
        client = get_vertex_client()
        llm_stats = client.get_usage_stats()
    except Exception:
        llm_stats = {"status": "not_initialized"}
    
    return {
        "status": "operational",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
        "configuration": {
            "default_llm": settings.default_llm,
            "default_tts": settings.default_tts,
            "default_stt": settings.default_stt,
            "default_telephony": settings.default_telephony,
            "max_concurrent_calls": settings.max_concurrent_calls,
        },
        "llm_usage": llm_stats,
        "uptime": _get_uptime(),
    }


# Track startup time
_startup_time = datetime.utcnow()

def _get_uptime() -> str:
    """Get service uptime"""
    delta = datetime.utcnow() - _startup_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint
    Returns metrics in Prometheus text format for scraping
    """
    from app.llm.vertex_client import get_vertex_client
    
    metrics = []
    
    # Help and type declarations for Prometheus
    metrics.append("# HELP leadgen_uptime_seconds Time since the service started")
    metrics.append("# TYPE leadgen_uptime_seconds gauge")
    uptime_seconds = (datetime.utcnow() - _startup_time).total_seconds()
    metrics.append(f'leadgen_uptime_seconds {uptime_seconds:.0f}')
    
    metrics.append("")
    metrics.append("# HELP leadgen_info Service information")
    metrics.append("# TYPE leadgen_info gauge")
    metrics.append(f'leadgen_info{{version="{os.environ.get("APP_VERSION", "dev")}",env="{settings.app_env}",llm="{settings.default_llm}",tts="{settings.default_tts}"}} 1')
    
    # LLM metrics
    try:
        client = get_vertex_client()
        stats = client.get_usage_stats()
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_requests_total Total number of LLM requests")
        metrics.append("# TYPE leadgen_llm_requests_total counter")
        metrics.append(f'leadgen_llm_requests_total{{model="{stats.get("model", "unknown")}"}} {stats.get("total", {}).get("requests", 0)}')
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_tokens_total Total tokens used")
        metrics.append("# TYPE leadgen_llm_tokens_total counter")
        metrics.append(f'leadgen_llm_tokens_total{{model="{stats.get("model", "unknown")}"}} {stats.get("total", {}).get("tokens", 0)}')
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_cost_inr_total Total cost in INR")
        metrics.append("# TYPE leadgen_llm_cost_inr_total counter")
        metrics.append(f'leadgen_llm_cost_inr_total{{model="{stats.get("model", "unknown")}"}} {stats.get("total", {}).get("cost_inr", 0):.4f}')
    except Exception:
        pass
    
    # Database metrics
    try:
        from sqlalchemy import text, func
        from app.models.base import async_session
        from app.models.call_log import CallLog, CallOutcome
        from app.models.lead import Lead
        from app.models.campaign import Campaign, CampaignStatus
        
        session_factory = async_session()
        if session_factory:
            async with session_factory() as session:
                # Total leads
                total_leads = await session.scalar(func.count(Lead.id))
                metrics.append("")
                metrics.append("# HELP leadgen_leads_total Total number of leads in database")
                metrics.append("# TYPE leadgen_leads_total gauge")
                metrics.append(f'leadgen_leads_total {total_leads or 0}')
                
                # Total calls
                total_calls = await session.scalar(func.count(CallLog.id))
                metrics.append("")
                metrics.append("# HELP leadgen_calls_total Total number of calls made")
                metrics.append("# TYPE leadgen_calls_total gauge")
                metrics.append(f'leadgen_calls_total {total_calls or 0}')
                
                # Active campaigns
                active_campaigns = await session.scalar(
                    func.count(Campaign.id).filter(Campaign.status == CampaignStatus.RUNNING)
                )
                metrics.append("")
                metrics.append("# HELP leadgen_campaigns_active Number of active campaigns")
                metrics.append("# TYPE leadgen_campaigns_active gauge")
                metrics.append(f'leadgen_campaigns_active {active_campaigns or 0}')
                
                # Appointments booked (total)
                appointments = await session.scalar(
                    func.count(CallLog.id).filter(CallLog.outcome == CallOutcome.APPOINTMENT)
                )
                metrics.append("")
                metrics.append("# HELP leadgen_appointments_total Total appointments booked")
                metrics.append("# TYPE leadgen_appointments_total counter")
                metrics.append(f'leadgen_appointments_total {appointments or 0}')
    except Exception as e:
        # Database metrics not available
        pass
    
    # Redis metrics
    try:
        from app.cache import get_redis_client
        redis = await get_redis_client()
        if redis:
            info = await redis.info()
            metrics.append("")
            metrics.append("# HELP leadgen_redis_connected_clients Number of connected Redis clients")
            metrics.append("# TYPE leadgen_redis_connected_clients gauge")
            metrics.append(f'leadgen_redis_connected_clients {info.get("connected_clients", 0)}')
            
            metrics.append("")
            metrics.append("# HELP leadgen_redis_used_memory_bytes Redis memory usage")
            metrics.append("# TYPE leadgen_redis_used_memory_bytes gauge")
            metrics.append(f'leadgen_redis_used_memory_bytes {info.get("used_memory", 0)}')
    except Exception:
        pass
    
    return Response(
        content="\n".join(metrics) + "\n",
        media_type="text/plain; charset=utf-8",
    )
