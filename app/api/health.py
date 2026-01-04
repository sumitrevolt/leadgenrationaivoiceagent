"""
Health and Observability API Endpoints
Production monitoring and health checks
"""
from fastapi import APIRouter, Response, status
from datetime import datetime
from typing import Dict, Any
import asyncio
import os
import sys

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Health"])

# Track startup time
_startup_time = datetime.utcnow()


def _get_uptime() -> str:
    """Get service uptime"""
    delta = datetime.utcnow() - _startup_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _get_uptime_seconds() -> float:
    """Get uptime in seconds"""
    return (datetime.utcnow() - _startup_time).total_seconds()


@router.get("/health")
async def health_check() -> Dict[str, Any]:
    """
    Basic health check endpoint
    Used by Cloud Run for liveness probes
    Returns 200 if the service is running
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
        "uptime": _get_uptime(),
    }


@router.get("/health/live")
async def liveness_check(response: Response):
    """
    Kubernetes/Cloud Run liveness probe
    Returns 200 if the process is running
    Fast and lightweight - no external dependencies checked
    """
    response.status_code = status.HTTP_200_OK
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness_check(response: Response) -> Dict[str, Any]:
    """
    Readiness check - verifies all dependencies are accessible
    Used by Cloud Run for readiness probes
    Returns 503 if any critical dependency is unhealthy
    """
    checks = {}
    overall_healthy = True
    
    # Check database
    db_healthy = await _check_database()
    checks["database"] = db_healthy
    if db_healthy["status"] == "unhealthy":
        overall_healthy = False
    
    # Check Redis
    redis_healthy = await _check_redis()
    checks["redis"] = redis_healthy
    if redis_healthy["status"] == "unhealthy":
        overall_healthy = False
    
    # Check LLM availability (degraded is ok)
    llm_status = _check_llm_config()
    checks["llm"] = llm_status
    
    # Check disk space
    disk_status = _check_disk_space()
    checks["disk"] = disk_status
    
    # Check memory
    memory_status = _check_memory()
    checks["memory"] = memory_status
    
    result = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
        "version": os.environ.get("APP_VERSION", "dev"),
    }
    
    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return result


@router.get("/health/deep")
async def deep_health_check() -> Dict[str, Any]:
    """
    Deep health check with detailed diagnostics
    Use sparingly - can be resource intensive
    """
    checks = {}
    
    # Database with query timing
    db_start = datetime.utcnow()
    db_result = await _check_database()
    db_result["latency_ms"] = (datetime.utcnow() - db_start).total_seconds() * 1000
    checks["database"] = db_result
    
    # Redis with ping timing
    redis_start = datetime.utcnow()
    redis_result = await _check_redis()
    redis_result["latency_ms"] = (datetime.utcnow() - redis_start).total_seconds() * 1000
    checks["redis"] = redis_result
    
    # LLM configuration
    checks["llm"] = _check_llm_config()
    
    # Telephony configuration
    checks["telephony"] = _check_telephony_config()
    
    # System resources
    checks["disk"] = _check_disk_space()
    checks["memory"] = _check_memory()
    checks["cpu"] = _check_cpu()
    
    # Celery workers (if applicable)
    checks["workers"] = await _check_celery_workers()
    
    all_healthy = all(
        c.get("status") in ["healthy", "ok", "configured"] 
        for c in checks.values()
    )
    
    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
        "uptime": _get_uptime(),
        "checks": checks,
    }


async def _check_database() -> Dict[str, Any]:
    """Check database connectivity"""
    try:
        from sqlalchemy import text
        from app.models.base import get_async_session
        
        async with get_async_session() as session:
            result = await session.execute(text("SELECT 1"))
            row = result.scalar()
            if row == 1:
                return {"status": "healthy"}
            return {"status": "unhealthy", "error": "Unexpected query result"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:100]}


async def _check_redis() -> Dict[str, Any]:
    """Check Redis connectivity"""
    try:
        from app.cache import get_redis_client
        
        client = await get_redis_client()
        await client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:100]}


def _check_llm_config() -> Dict[str, Any]:
    """Check LLM configuration"""
    if settings.gemini_api_key or settings.google_cloud_project_id:
        return {"status": "configured", "provider": "gemini"}
    elif settings.openai_api_key:
        return {"status": "configured", "provider": "openai"}
    elif settings.anthropic_api_key:
        return {"status": "configured", "provider": "anthropic"}
    else:
        return {"status": "degraded", "error": "No LLM configured"}


def _check_telephony_config() -> Dict[str, Any]:
    """Check telephony configuration"""
    providers = []
    if settings.twilio_account_sid and settings.twilio_auth_token:
        providers.append("twilio")
    if settings.exotel_api_key:
        providers.append("exotel")
    
    if providers:
        return {"status": "configured", "providers": providers}
    else:
        return {"status": "degraded", "error": "No telephony configured"}


def _check_disk_space() -> Dict[str, Any]:
    """Check available disk space"""
    try:
        import shutil
        total, used, free = shutil.disk_usage("/")
        free_percent = (free / total) * 100
        
        return {
            "status": "ok" if free_percent > 10 else "warning",
            "free_gb": round(free / (1024**3), 2),
            "free_percent": round(free_percent, 1),
        }
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:50]}


def _check_memory() -> Dict[str, Any]:
    """Check memory usage"""
    try:
        import psutil
        memory = psutil.virtual_memory()
        
        return {
            "status": "ok" if memory.percent < 90 else "warning",
            "used_percent": round(memory.percent, 1),
            "available_mb": round(memory.available / (1024**2), 0),
        }
    except ImportError:
        return {"status": "unknown", "error": "psutil not installed"}
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:50]}


def _check_cpu() -> Dict[str, Any]:
    """Check CPU usage"""
    try:
        import psutil
        cpu_percent = psutil.cpu_percent(interval=0.1)
        
        return {
            "status": "ok" if cpu_percent < 90 else "warning",
            "usage_percent": round(cpu_percent, 1),
            "cores": psutil.cpu_count(),
        }
    except ImportError:
        return {"status": "unknown", "error": "psutil not installed"}
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:50]}


async def _check_celery_workers() -> Dict[str, Any]:
    """Check Celery worker status"""
    try:
        from app.worker import celery_app
        
        # Get active workers
        inspect = celery_app.control.inspect()
        active = inspect.active()
        
        if active:
            worker_count = len(active)
            return {"status": "healthy", "workers": worker_count}
        else:
            return {"status": "degraded", "workers": 0}
    except Exception as e:
        return {"status": "unknown", "error": str(e)[:50]}


@router.get("/api/v1/status")
async def api_status() -> Dict[str, Any]:
    """
    Detailed API status with metrics
    """
    llm_stats = {"status": "not_initialized"}
    
    try:
        from app.llm.vertex_client import get_vertex_client
        client = get_vertex_client()
        llm_stats = client.get_usage_stats()
    except Exception:
        pass
    
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
        "python_version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    }


@router.get("/metrics")
async def prometheus_metrics():
    """
    Prometheus-compatible metrics endpoint
    Returns metrics in Prometheus text format for scraping
    """
    metrics = []
    
    # Help and type declarations for Prometheus
    metrics.append("# HELP leadgen_uptime_seconds Time since the service started")
    metrics.append("# TYPE leadgen_uptime_seconds gauge")
    uptime_seconds = _get_uptime_seconds()
    metrics.append(f'leadgen_uptime_seconds {uptime_seconds:.0f}')
    
    metrics.append("")
    metrics.append("# HELP leadgen_info Service information")
    metrics.append("# TYPE leadgen_info gauge")
    version = os.environ.get("APP_VERSION", "dev").replace('"', '\\"')
    metrics.append(f'leadgen_info{{version="{version}",env="{settings.app_env}",llm="{settings.default_llm}",tts="{settings.default_tts}"}} 1')
    
    # LLM metrics
    try:
        from app.llm.vertex_client import get_vertex_client
        client = get_vertex_client()
        stats = client.get_usage_stats()
        
        model = stats.get("model", "unknown")
        total = stats.get("total", {})
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_requests_total Total number of LLM requests")
        metrics.append("# TYPE leadgen_llm_requests_total counter")
        metrics.append(f'leadgen_llm_requests_total{{model="{model}"}} {total.get("requests", 0)}')
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_tokens_total Total tokens used")
        metrics.append("# TYPE leadgen_llm_tokens_total counter")
        metrics.append(f'leadgen_llm_tokens_total{{model="{model}"}} {total.get("tokens", 0)}')
        
        metrics.append("")
        metrics.append("# HELP leadgen_llm_cost_inr_total Total cost in INR")
        metrics.append("# TYPE leadgen_llm_cost_inr_total counter")
        metrics.append(f'leadgen_llm_cost_inr_total{{model="{model}"}} {total.get("cost_inr", 0):.4f}')
    except Exception:
        pass
    
    # Database metrics
    try:
        from sqlalchemy import text, func, select
        from app.models.base import get_async_session
        from app.models.call_log import CallLog, CallOutcome
        from app.models.lead import Lead
        from app.models.campaign import Campaign, CampaignStatus
        
        async with get_async_session() as session:
            # Total leads
            total_leads = await session.scalar(select(func.count()).select_from(Lead))
            metrics.append("")
            metrics.append("# HELP leadgen_leads_total Total number of leads in database")
            metrics.append("# TYPE leadgen_leads_total gauge")
            metrics.append(f'leadgen_leads_total {total_leads or 0}')
            
            # Total calls
            total_calls = await session.scalar(select(func.count()).select_from(CallLog))
            metrics.append("")
            metrics.append("# HELP leadgen_calls_total Total number of calls made")
            metrics.append("# TYPE leadgen_calls_total gauge")
            metrics.append(f'leadgen_calls_total {total_calls or 0}')
            
            # Active campaigns
            active_campaigns = await session.scalar(
                select(func.count()).select_from(Campaign).where(Campaign.status == CampaignStatus.RUNNING)
            )
            metrics.append("")
            metrics.append("# HELP leadgen_campaigns_active Number of active campaigns")
            metrics.append("# TYPE leadgen_campaigns_active gauge")
            metrics.append(f'leadgen_campaigns_active {active_campaigns or 0}')
            
            # Appointments booked (total)
            appointments = await session.scalar(
                select(func.count()).select_from(CallLog).where(CallLog.outcome == CallOutcome.APPOINTMENT)
            )
            metrics.append("")
            metrics.append("# HELP leadgen_appointments_total Total appointments booked")
            metrics.append("# TYPE leadgen_appointments_total counter")
            metrics.append(f'leadgen_appointments_total {appointments or 0}')
    except Exception:
        # Database metrics not available
        pass
    
    # Redis metrics
    try:
        from app.cache import get_redis_client
        redis = await get_redis_client()
        if redis and hasattr(redis, 'info'):
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
    
    # System metrics
    try:
        import psutil
        
        metrics.append("")
        metrics.append("# HELP leadgen_process_cpu_percent Process CPU usage percentage")
        metrics.append("# TYPE leadgen_process_cpu_percent gauge")
        metrics.append(f'leadgen_process_cpu_percent {psutil.cpu_percent(interval=0.1):.1f}')
        
        memory = psutil.virtual_memory()
        metrics.append("")
        metrics.append("# HELP leadgen_memory_usage_percent System memory usage percentage")
        metrics.append("# TYPE leadgen_memory_usage_percent gauge")
        metrics.append(f'leadgen_memory_usage_percent {memory.percent:.1f}')
        
        process = psutil.Process()
        metrics.append("")
        metrics.append("# HELP leadgen_process_memory_bytes Process memory usage in bytes")
        metrics.append("# TYPE leadgen_process_memory_bytes gauge")
        metrics.append(f'leadgen_process_memory_bytes {process.memory_info().rss}')
    except ImportError:
        pass
    except Exception:
        pass
    
    return Response(
        content="\n".join(metrics) + "\n",
        media_type="text/plain; charset=utf-8",
    )
