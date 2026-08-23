"""
Health and Observability API Endpoints
Production monitoring and health checks
"""

import asyncio
import hmac
import os
import sys
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.auth_deps import require_admin
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(tags=["Health"])

# Track startup time
_startup_time = datetime.utcnow()


async def _require_metrics_auth(request: Request) -> None:
    """Optional bearer-token gate for /metrics + /health/deep.

    ARMED only when METRICS_TOKEN is set — default unset means today's open
    behavior is UNCHANGED (internal Prometheus scraping, monitoring/prometheus.yml,
    has no auth token configured, so locking this down unconditionally would break
    it). Both endpoints return real business/operational counts with no auth, and
    whether they're reachable from outside the Docker network depends on the
    reverse-proxy config, which this audit could not verify (production audit
    2026-07-01, low-severity finding). To lock down: set METRICS_TOKEN in .env AND
    add the same value as a bearer_token in monitoring/prometheus.yml's scrape
    config for the `leadgen_app` job, so internal scraping keeps working.
    """
    token = (os.environ.get("METRICS_TOKEN") or "").strip()
    if not token:
        return  # inert until armed — zero behavior change by default
    auth_header = request.headers.get("authorization", "")
    provided = (
        auth_header[7:]
        if auth_header.lower().startswith("bearer ")
        else request.headers.get("x-metrics-token", "")
    )
    if not hmac.compare_digest((provided or "").strip(), token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _get_uptime() -> str:
    """Get service uptime"""
    delta = datetime.utcnow() - _startup_time
    hours, remainder = divmod(int(delta.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _get_uptime_seconds() -> float:
    """Get uptime in seconds"""
    return (datetime.utcnow() - _startup_time).total_seconds()


# A health body answers "what code is running RIGHT NOW, and is it well?" — a
# CACHED health body answers that about the past, which is worse than no answer:
# it looks authoritative while being wrong.
#
# Live proof (2026-07-15 admin audit): the FIRST `GET /health` from a browser
# returned a 12.7-hour-stale body advertising `version: 91e7d37`, `uptime: 13m`,
# `timestamp: 2026-07-14T12:59` — while production was actually running
# `b12d1e97` with 8h24m uptime. Nothing about the response looked stale. Only
# adding a `?cb=` query string (a different cache key) revealed the truth.
#
# Root enabler: these endpoints returned a bare dict with NO cache directives,
# and a response without Cache-Control/Expires is heuristically cacheable by
# browsers and any intermediary (RFC 9111 §4.2.2). We do not need to know WHICH
# layer cached it — `no-store` closes the whole class at the source.
#
# Why this matters beyond tidiness: CLAUDE.md designates `/health`'s `version`
# field as THE deploy-drift detector ("/health ka version field hi tumhara drift
# detector hai"). ADR-097 hardened the case where the running image's provenance
# is unknown; this is the same failure one layer out — the provenance REPORT
# itself was stale. A drift detector that can be served from cache can tell you
# the wrong SHA and let a skewed/unversioned deploy pass unnoticed.
_NO_STORE = "no-store, no-cache, must-revalidate, max-age=0"


def _mark_no_store(response: Response) -> None:
    """Forbid caching of a health/version report (see _NO_STORE rationale)."""
    response.headers["Cache-Control"] = _NO_STORE
    response.headers["Pragma"] = "no-cache"  # HTTP/1.0 + legacy proxies
    response.headers["Expires"] = "0"


@router.get("/health")
async def health_check(response: Response) -> dict[str, Any]:
    """
    Basic health check endpoint
    Used by Cloud Run for liveness probes
    Returns 200 if the service is running

    Never cached — this response carries the deployed version and is the
    documented deploy-drift detector.
    """
    _mark_no_store(response)
    result = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
        "uptime": _get_uptime(),
    }
    
    # Add DSH fields (fail-closed: default to disabled).
    try:
        from app.integrations import dsh as dsh_integration
        dsh_fields = dsh_integration.get_dsh_health_fields()
        result.update(dsh_fields)
    except Exception:
        # If DSH integration is unavailable, default to disabled.
        result.update({
            "dsh_runtime_enabled": False,
            "dsh_shadow_enabled": False,
            "dsh_allowlist": [],
        })
    
    return result


@router.get("/health/live")
async def liveness_check(response: Response):
    """
    Kubernetes/Cloud Run liveness probe
    Returns 200 if the process is running
    Fast and lightweight - no external dependencies checked
    """
    _mark_no_store(response)
    response.status_code = status.HTTP_200_OK
    return {"status": "alive"}


@router.get("/health/signup")
async def signup_health(response: Response) -> dict[str, Any]:
    """Loop 14 (2026-07-10) — signup-path targeted health probe.

    Validates the four dependencies signup actually needs (imports + JWT config
    + clients_store readable + auth JSONL writable) without creating a real
    account. Ops uptime monitors (Uptime/Gatus) can poll this instead of the
    generic /health so a broken signup surface is caught the moment it breaks —
    not after "why is nobody signing up" observation on the CRM. Returns 200 +
    per-check status when all four probes pass; 503 with per-check failure
    detail otherwise. Never raises.
    """
    _mark_no_store(response)
    checks: dict[str, Any] = {}
    overall_healthy = True

    # 1) JWT mint reachable (this is the Loop 1B `auto_login=False` root cause).
    try:
        from app.api import admin as _admin_mod

        _tok = _admin_mod.create_access_token("probe", "probe@example.com", "customer")
        checks["jwt_mint"] = {"status": "healthy" if _tok else "unhealthy"}
        if not _tok:
            overall_healthy = False
    except Exception as e:
        checks["jwt_mint"] = {"status": "unhealthy", "error": f"{type(e).__name__}: {e}"[:200]}
        overall_healthy = False

    # 2) clients_store importable + basic read (add_client reachable).
    try:
        from app.marketing import clients_store as _cs

        # Just verifies the module + function exist; no write side-effect.
        assert callable(getattr(_cs, "add_client", None)), "add_client missing"
        checks["clients_store"] = {"status": "healthy"}
    except Exception as e:
        checks["clients_store"] = {"status": "unhealthy", "error": f"{type(e).__name__}: {e}"[:200]}
        overall_healthy = False

    # 3) Customer auth store (JSONL) readable + directory writable.
    try:
        from app.api import customer_auth as _ca

        _ = _ca._read()  # returns [] on missing file — that's fine
        # Directory must be writable — check without actually writing a real row.
        _dir = os.path.dirname(_ca._STORE) or "."
        os.makedirs(_dir, exist_ok=True)
        checks["auth_store"] = {"status": "healthy" if os.access(_dir, os.W_OK) else "unhealthy"}
        if not os.access(_dir, os.W_OK):
            overall_healthy = False
    except Exception as e:
        checks["auth_store"] = {"status": "unhealthy", "error": f"{type(e).__name__}: {e}"[:200]}
        overall_healthy = False

    # 4) Automation-log service reachable (Loops 2/3B/7/8 depend on it).
    try:
        from app.platform import automation_log_service as _als

        assert callable(getattr(_als, "log_event", None)), "log_event missing"
        checks["automation_log"] = {"status": "healthy"}
    except Exception as e:
        checks["automation_log"] = {
            "status": "unhealthy",
            "error": f"{type(e).__name__}: {e}"[:200],
        }
        overall_healthy = False

    # 5) Billing usage (activate_plan) reachable — the plan provisioning path
    #    that silently fails at signup when DB/clients_store is broken.
    try:
        from app.billing import usage as _usage

        assert callable(getattr(_usage, "activate_plan", None)), "activate_plan missing"
        assert callable(getattr(_usage, "reset_usage_period", None)), "reset_usage_period missing"
        checks["billing_usage"] = {"status": "healthy"}
    except Exception as e:
        checks["billing_usage"] = {"status": "unhealthy", "error": f"{type(e).__name__}: {e}"[:200]}
        overall_healthy = False

    result = {
        "status": "healthy" if overall_healthy else "unhealthy",
        "surface": "signup",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": checks,
    }
    if not overall_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return result


@router.get("/health/ready")
async def readiness_check(response: Response) -> dict[str, Any]:
    """
    Readiness check - verifies all dependencies are accessible
    Used by Cloud Run for readiness probes
    Returns 503 if any critical dependency is unhealthy
    """
    _mark_no_store(response)
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


@router.get("/health/deep", dependencies=[Depends(_require_metrics_auth)])
async def deep_health_check() -> dict[str, Any]:
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

    all_healthy = all(c.get("status") in ["healthy", "ok", "configured"] for c in checks.values())

    return {
        "status": "healthy" if all_healthy else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "version": os.environ.get("APP_VERSION", "dev"),
        "environment": settings.app_env,
        "uptime": _get_uptime(),
        "checks": checks,
    }


async def _check_database() -> dict[str, Any]:
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


async def _check_redis() -> dict[str, Any]:
    """Check Redis connectivity"""
    try:
        from app.cache import get_redis_client

        client = await get_redis_client()
        await client.ping()
        return {"status": "healthy"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)[:100]}


def _check_llm_config() -> dict[str, Any]:
    """Check LLM configuration — report free-stack truth, not "first key found".

    Historical bug: readiness returned ``provider=gemini`` whenever
    ``GEMINI_API_KEY`` was set, even when ``GEMINI_PRIMARY`` was false and the
    live chat path used free_ai (Groq → Cerebras → Mistral…). That made
    ``/health/ready`` contradict operational truth without any provider change.

    ``provider`` = first hop of the realtime free_ai chain that has a key.
    ``providers`` = all configured free_ai provider names. Never raises.
    """
    try:
        from app.voice_agent import free_ai

        desc = free_ai.describe()
        flags = desc.get("providers") or {}
        chain = list(desc.get("llm_chain") or [])
        configured = sorted(p for p, ok in flags.items() if ok)
        primary = ""
        for entry in chain:
            name = str(entry).split(":", 1)[0].strip()
            if name and flags.get(name):
                primary = name
                break
        if not primary and configured:
            # Prefer free core over gemini/openrouter tails when chain empty.
            for prefer in ("groq", "cerebras", "mistral", "gemini", "openrouter"):
                if prefer in configured:
                    primary = prefer
                    break
            if not primary:
                primary = configured[0]
        if primary or configured:
            out: dict[str, Any] = {
                "status": "configured",
                "provider": primary or "unknown",
                "providers": configured,
            }
            if chain:
                out["llm_chain_head"] = chain[:6]
            return out
    except Exception as exc:
        logger.debug("llm readiness free_ai describe skipped: %s", exc)

    # Legacy fallback (paid-named keys only) — used if free_ai import fails.
    if settings.gemini_api_key or settings.google_cloud_project_id:
        return {"status": "configured", "provider": "gemini"}
    if settings.openai_api_key:
        return {"status": "configured", "provider": "openai"}
    if settings.anthropic_api_key:
        return {"status": "configured", "provider": "anthropic"}
    return {"status": "degraded", "error": "No LLM configured"}


def _check_telephony_config() -> dict[str, Any]:
    """Check telephony configuration"""
    providers = []
    if settings.vobiz_auth_id and settings.vobiz_auth_token:
        providers.append("vobiz")

    if providers:
        return {"status": "configured", "providers": providers}
    else:
        return {"status": "degraded", "error": "No telephony configured"}


def _check_disk_space() -> dict[str, Any]:
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


def _check_memory() -> dict[str, Any]:
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


def _check_cpu() -> dict[str, Any]:
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


async def _check_celery_workers() -> dict[str, Any]:
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


@router.get("/api/v1/status", dependencies=[Depends(require_admin)])
async def api_status() -> dict[str, Any]:
    """
    Detailed API status with metrics (admin-only).

    Leaks stack/version + LLM/TTS/STT/telephony config + llm_usage — recon for an
    attacker. Was anonymously reachable; gated 2026-07-06 (sec sweep). No repo
    consumer relied on it (the public probe is `/health`).
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


@router.get("/metrics", dependencies=[Depends(_require_metrics_auth)])
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
    metrics.append(f"leadgen_uptime_seconds {uptime_seconds:.0f}")

    metrics.append("")
    metrics.append("# HELP leadgen_info Service information")
    metrics.append("# TYPE leadgen_info gauge")
    version = os.environ.get("APP_VERSION", "dev").replace('"', '\\"')
    metrics.append(
        f'leadgen_info{{version="{version}",env="{settings.app_env}",llm="{settings.default_llm}",tts="{settings.default_tts}"}} 1'
    )

    # LLM provider health — REAL source app.platform.llm_metrics (data/llm_calls.jsonl,
    # shared across workers = multi-worker-correct). Pehle yahan legacy vertex_client
    # tha jo prod me empty rehta (audit P1-3). File read off-loop (executor) — scrape
    # event-loop block na kare. ok_rate/fallback_rate alert-ready (free providers
    # exhaust = voice/content ka #1 live bottleneck — ab visible).
    try:
        from app.platform import llm_metrics

        llm = await asyncio.get_running_loop().run_in_executor(None, llm_metrics.stats, 500)
        providers = (llm or {}).get("providers", {}) or {}

        metrics.append("")
        metrics.append(
            "# HELP leadgen_llm_provider_calls Total LLM attempts per provider (rolling window)"
        )
        metrics.append("# TYPE leadgen_llm_provider_calls gauge")
        for p, v in providers.items():
            metrics.append(
                f'leadgen_llm_provider_calls{{provider="{p}"}} {int(v.get("calls", 0) or 0)}'
            )

        metrics.append("")
        metrics.append(
            "# HELP leadgen_llm_provider_ok_rate LLM provider success rate 0-1 (rolling window)"
        )
        metrics.append("# TYPE leadgen_llm_provider_ok_rate gauge")
        for p, v in providers.items():
            metrics.append(
                f'leadgen_llm_provider_ok_rate{{provider="{p}"}} {float(v.get("ok_rate", 0) or 0):.3f}'
            )

        metrics.append("")
        metrics.append(
            "# HELP leadgen_llm_provider_avg_latency_ms LLM provider avg latency ms (successful calls)"
        )
        metrics.append("# TYPE leadgen_llm_provider_avg_latency_ms gauge")
        for p, v in providers.items():
            metrics.append(
                f'leadgen_llm_provider_avg_latency_ms{{provider="{p}"}} {float(v.get("avg_ms", 0) or 0):.1f}'
            )

        metrics.append("")
        metrics.append(
            "# HELP leadgen_llm_fallback_rate Fraction of LLM attempts that failed/fell through 0-1"
        )
        metrics.append("# TYPE leadgen_llm_fallback_rate gauge")
        metrics.append(
            f'leadgen_llm_fallback_rate {float((llm or {}).get("fallback_or_fail_rate", 0) or 0):.3f}'
        )
    except Exception:
        pass

    # Semantic LLM cache (SHARED Redis counters — multi-worker-correct, tera in-process
    # "unreliable" decision ke according). hit_rate = (exact+semantic)/lookups. Cache OFF
    # (SEMANTIC_CACHE flag) => mostly "disabled" events, hit_rate 0. Fail-open scrape.
    try:
        from app.cache import semantic_cache as _semcache

        cs = await _semcache.redis_stats()
        served = int(cs.get("exact", 0)) + int(cs.get("semantic", 0))
        looked = served + int(cs.get("miss", 0))
        hit_rate = (served / looked) if looked else 0.0

        metrics.append("")
        metrics.append("# HELP leadgen_semcache_events_total Semantic LLM cache events by kind")
        metrics.append("# TYPE leadgen_semcache_events_total counter")
        for _k in ("exact", "semantic", "miss", "error", "disabled"):
            metrics.append(f'leadgen_semcache_events_total{{kind="{_k}"}} {int(cs.get(_k, 0))}')

        metrics.append("")
        metrics.append(
            "# HELP leadgen_semcache_hit_rate Semantic cache hit rate 0-1 ((exact+semantic)/lookups)"
        )
        metrics.append("# TYPE leadgen_semcache_hit_rate gauge")
        metrics.append(f"leadgen_semcache_hit_rate {hit_rate:.3f}")
    except Exception:
        pass

    # Agent memory (gated AGENT_MEMORY) — cross-session lead/client recall usage.
    # OFF (default) => events mostly 0. Fail-open scrape (semcache jaisa pattern).
    try:
        from app.voice_agent import agent_memory as _amem

        ms = await _amem.redis_stats()
        _looked = int(ms.get("recall_hit", 0)) + int(ms.get("recall_miss", 0))
        _mrate = (int(ms.get("recall_hit", 0)) / _looked) if _looked else 0.0

        metrics.append("")
        metrics.append("# HELP leadgen_agent_memory_events_total Agent memory events by kind")
        metrics.append("# TYPE leadgen_agent_memory_events_total counter")
        for _mk in ("recall_hit", "recall_miss", "stored", "error", "disabled"):
            metrics.append(
                f'leadgen_agent_memory_events_total{{kind="{_mk}"}} {int(ms.get(_mk, 0))}'
            )

        metrics.append("")
        metrics.append(
            "# HELP leadgen_agent_memory_recall_rate Memory recall hit rate 0-1 (hit/(hit+miss))"
        )
        metrics.append("# TYPE leadgen_agent_memory_recall_rate gauge")
        metrics.append(f"leadgen_agent_memory_recall_rate {_mrate:.3f}")
    except Exception:
        pass

    # LLM budget guard (gated LLM_BUDGET_GUARD) — per-scope cost/usage governance.
    # OFF (default) => enabled=0, counters 0. Fail-open scrape.
    try:
        from app.llm import budget_guard as _bg

        bs = await _bg.redis_stats()
        metrics.append("")
        metrics.append("# HELP leadgen_llm_budget_enabled LLM budget guard active (1) or off (0)")
        metrics.append("# TYPE leadgen_llm_budget_enabled gauge")
        metrics.append(f"leadgen_llm_budget_enabled {1 if bs.get('enabled') else 0}")
        metrics.append(f"leadgen_llm_budget_hard_kill {1 if bs.get('hard_kill') else 0}")

        metrics.append("")
        metrics.append("# HELP leadgen_llm_budget_global_today Global LLM usage today (all scopes)")
        metrics.append("# TYPE leadgen_llm_budget_global_today gauge")
        metrics.append(
            f'leadgen_llm_budget_global_today{{unit="calls"}} {int(bs.get("global_calls", 0))}'
        )
        metrics.append(
            f'leadgen_llm_budget_global_today{{unit="tokens"}} {int(bs.get("global_tokens", 0))}'
        )

        metrics.append("")
        metrics.append("# HELP leadgen_llm_budget_events_total Budget guard decisions by kind")
        metrics.append("# TYPE leadgen_llm_budget_events_total counter")
        for _ek in ("allowed", "blocked", "killed", "error", "disabled"):
            metrics.append(
                f'leadgen_llm_budget_events_total{{kind="{_ek}"}} {int(bs.get("events_" + _ek, 0))}'
            )
    except Exception:
        pass

    # Database metrics — counts are cached in Redis for 60s so Prometheus scrapes
    # don't fire 4x COUNT() against the DB on every poll (cheap, scrape-safe).
    try:
        from app.cache import cache

        async def _compute_db_counts() -> dict:
            from sqlalchemy import func, select

            from app.models.base import get_async_session
            from app.models.call_log import CallLog, CallOutcome
            from app.models.campaign import Campaign, CampaignStatus
            from app.models.lead import Lead

            async with get_async_session() as session:
                total_leads = await session.scalar(select(func.count()).select_from(Lead))
                total_calls = await session.scalar(select(func.count()).select_from(CallLog))
                active_campaigns = await session.scalar(
                    select(func.count())
                    .select_from(Campaign)
                    .where(Campaign.status == CampaignStatus.RUNNING)
                )
                appointments = await session.scalar(
                    select(func.count())
                    .select_from(CallLog)
                    .where(CallLog.outcome == CallOutcome.APPOINTMENT)
                )
            return {
                "leads": int(total_leads or 0),
                "calls": int(total_calls or 0),
                "campaigns_active": int(active_campaigns or 0),
                "appointments": int(appointments or 0),
            }

        counts = await cache.get_or_set("metrics:db_counts", _compute_db_counts, ttl=60)
        counts = counts or {}

        metrics.append("")
        metrics.append("# HELP leadgen_leads_total Total number of leads in database")
        metrics.append("# TYPE leadgen_leads_total gauge")
        metrics.append(f"leadgen_leads_total {counts.get('leads', 0)}")

        metrics.append("")
        metrics.append("# HELP leadgen_calls_total Total number of calls made")
        metrics.append("# TYPE leadgen_calls_total gauge")
        metrics.append(f"leadgen_calls_total {counts.get('calls', 0)}")

        metrics.append("")
        metrics.append("# HELP leadgen_campaigns_active Number of active campaigns")
        metrics.append("# TYPE leadgen_campaigns_active gauge")
        metrics.append(f"leadgen_campaigns_active {counts.get('campaigns_active', 0)}")

        metrics.append("")
        metrics.append("# HELP leadgen_appointments_total Total appointments booked")
        metrics.append("# TYPE leadgen_appointments_total counter")
        metrics.append(f"leadgen_appointments_total {counts.get('appointments', 0)}")
    except Exception:
        # Database metrics not available
        pass

    # Redis metrics
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        if redis and hasattr(redis, "info"):
            info = await redis.info()
            metrics.append("")
            metrics.append(
                "# HELP leadgen_redis_connected_clients Number of connected Redis clients"
            )
            metrics.append("# TYPE leadgen_redis_connected_clients gauge")
            metrics.append(f'leadgen_redis_connected_clients {info.get("connected_clients", 0)}')

            metrics.append("")
            metrics.append("# HELP leadgen_redis_used_memory_bytes Redis memory usage")
            metrics.append("# TYPE leadgen_redis_used_memory_bytes gauge")
            metrics.append(f'leadgen_redis_used_memory_bytes {info.get("used_memory", 0)}')
    except Exception:
        pass

    # Celery queue depth — broker = main redis lists (shared = multi-worker-correct).
    # Backlog visibility at scale: koi queue badhti rahe = worker starve/stuck (audit
    # P1-3). InMemoryCache fallback me llen nahi → guard se skip.
    try:
        from app.cache import get_redis_client

        redis = await get_redis_client()
        if redis and hasattr(redis, "llen"):
            metrics.append("")
            metrics.append("# HELP leadgen_celery_queue_depth Pending tasks per Celery queue")
            metrics.append("# TYPE leadgen_celery_queue_depth gauge")
            for q in (
                "celery",
                "heavy",
                "scraping",
                "calling",
                "reporting",
                "sync",
                "training",
                "dlq:failed_tasks",
            ):
                try:
                    depth = await redis.llen(q)
                except Exception:
                    depth = 0
                metrics.append(f'leadgen_celery_queue_depth{{queue="{q}"}} {int(depth or 0)}')
    except Exception:
        pass

    # System metrics
    try:
        import psutil

        metrics.append("")
        metrics.append("# HELP leadgen_process_cpu_percent Process CPU usage percentage")
        metrics.append("# TYPE leadgen_process_cpu_percent gauge")
        # interval=None = non-blocking (since-last-call). interval=0.1 har /metrics
        # scrape pe 100ms event-loop block karta tha (P2). Pehla scrape 0.0, phir real.
        metrics.append(f"leadgen_process_cpu_percent {psutil.cpu_percent(interval=None):.1f}")

        memory = psutil.virtual_memory()
        metrics.append("")
        metrics.append("# HELP leadgen_memory_usage_percent System memory usage percentage")
        metrics.append("# TYPE leadgen_memory_usage_percent gauge")
        metrics.append(f"leadgen_memory_usage_percent {memory.percent:.1f}")

        process = psutil.Process()
        metrics.append("")
        metrics.append("# HELP leadgen_process_memory_bytes Process memory usage in bytes")
        metrics.append("# TYPE leadgen_process_memory_bytes gauge")
        metrics.append(f"leadgen_process_memory_bytes {process.memory_info().rss}")
    except ImportError:
        pass
    except Exception:
        pass

    # HTTP request/latency metrics (OBS-001) — makes HighHttp5xxRate +
    # HighRequestLatencyP95 alerts live. Empty unless PROMETHEUS_HTTP_METRICS=1.
    try:
        from app.middleware.http_metrics import render_http_metrics

        metrics.extend(render_http_metrics())
    except Exception:
        pass

    # Per-job metrics (W1.13) — job success/fail counts + duration.
    # Empty unless PROMETHEUS_JOB_METRICS=1.
    try:
        from app.platform.job_metrics import render_job_metrics

        metrics.extend(render_job_metrics())
    except Exception:
        pass

    return Response(
        content="\n".join(metrics) + "\n",
        media_type="text/plain; charset=utf-8",
    )
