"""
AI Voice Agent - B2B Lead Generation Platform
FastAPI Main Application - PRODUCTION READY

MULTI-TIER AUTOMATED PLATFORM:
1. Platform finds B2B clients (businesses needing lead generation)
2. Clients get their own automated voice agent for lead generation
3. Everything runs 24/7 with minimal human intervention
"""
import os
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import asyncio

from app.config import settings
from app.api import leads, campaigns, analytics, webhooks
from app.api.billing import router as billing_router
from app.api.platform import router as platform_router
from app.api.ml_training import router as ml_router
from app.api.health import router as health_router
from app.api.admin import router as admin_router
from app.api.ai import router as ai_router
from app.api.data import router as data_router
from app.api.customer_dashboard import router as customer_dashboard_router
from app.api.admin_dashboard import router as admin_dashboard_router
from app.api.web_call import router as web_call_router
from app.api.agents import router as agents_router
from app.api.telephony_vobiz import router as telephony_vobiz_router
from fastapi import WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path

# Frontend directory (dashboards + marketing website + PWA)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
from app.platform.orchestrator import PlatformOrchestrator
from app.ml import get_training_scheduler, stop_training_scheduler
from app.models.base import init_async_db, close_async_db
from app.middleware import setup_middleware
from app.exceptions import setup_exception_handlers
from app.cache import close_redis_client
from app.utils.logger import setup_logger

# Setup logging
logger = setup_logger(__name__)

# Initialize Sentry for error tracking in production
if settings.sentry_dsn and settings.app_env == "production":
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration

        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env,
            release=os.environ.get("APP_VERSION", "1.0.0"),
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            profiles_sample_rate=0.1,  # 10% of sampled transactions for profiling
            integrations=[
                FastApiIntegration(transaction_style="endpoint"),
                SqlalchemyIntegration(),
                RedisIntegration(),
                CeleryIntegration(),
            ],
            # Don't send PII
            send_default_pii=False,
            # Attach stack traces for all log messages at ERROR level or higher
            attach_stacktrace=True,
            # Filter out health check endpoints from transactions
            before_send_transaction=lambda event, hint: None if event.get("transaction") in ["/health", "/health/ready", "/health/live"] else event,
        )
        logger.info("✅ Sentry error tracking initialized")
    except ImportError:
        logger.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as e:
        logger.warning(f"Sentry initialization failed: {e}")

# Platform orchestrator instance
platform_orchestrator: PlatformOrchestrator = None
ml_scheduler = None


def _log_startup_banner():
    """Display configuration banner on startup."""
    logger.info("=" * 60)
    logger.info("🤖 AI VOICE AGENT - MULTI-TIER B2B LEAD GENERATION PLATFORM")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📊 PLATFORM MODEL:")
    logger.info("   ├── Tier 1: Platform finds B2B clients (businesses needing leads)")
    logger.info("   └── Tier 2: Each client gets automated voice agent for their leads")
    logger.info("")
    logger.info("⚙️  CONFIGURATION:")
    logger.info(f"   ├── Telephony: {settings.default_telephony}")
    logger.info(f"   ├── LLM: {settings.default_llm}")
    logger.info(f"   ├── STT: {settings.default_stt}")
    logger.info(f"   ├── TTS: {settings.default_tts}")
    logger.info("   └── ML Auto-Learning: ENABLED")
    logger.info("")
    logger.info(f"🚀 AUTO-START: {'ENABLED' if settings.auto_start_platform else 'DISABLED'}")
    logger.info("🧠 ML TRAINING: Nightly at 2:00 AM, Weekly on Sunday")
    logger.info("=" * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global platform_orchestrator, ml_scheduler

    # Startup
    logger.info(f"🚀 Starting {settings.app_name}...")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Version: {os.environ.get('APP_VERSION', 'dev')}")
    _log_startup_banner()

    # Initialize database
    try:
        await init_async_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed (may not be configured): {e}")

    # DISABLED: Redis and ML scheduler for initial production startup
    # Redis requires VPC connector which is not configured yet
    logger.info("⏭️ Redis disabled - requires VPC connector for internal network access")
    logger.info("⏭️ Platform orchestrator disabled for initial deployment")
    logger.info("⏭️ ML scheduler disabled for initial deployment")

    # AI Staff Team automation (Arjun QA 02:30, Meera trainer 03:00, Kavya ops hourly)
    try:
        from app.platform.team_scheduler import start_scheduler

        start_scheduler()
        logger.info("✅ AI Staff Team scheduler started (TEAM_AUTOMATION)")
    except Exception as e:
        logger.warning(f"Team scheduler not started: {e}")

    logger.info("✅ Startup complete - application ready")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    if platform_orchestrator:
        await platform_orchestrator.stop()
    if ml_scheduler:
        await stop_training_scheduler()
    await close_async_db()
    await close_redis_client()
    logger.info("✅ Graceful shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="AI Voice Agent for B2B Lead Generation - Automated calling, qualification, and CRM integration",
    version=os.environ.get("APP_VERSION", "1.0.0"),
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,  # Disable in production
    redoc_url="/redoc" if settings.app_env != "production" else None,
)

# Configure production middleware
is_production = settings.app_env == "production"
setup_middleware(app, production=is_production)

# Configure exception handlers
setup_exception_handlers(app)

# CORS Middleware (configured based on environment)
# In production the allowed origins come from settings.cors_origins
# (CORS_ORIGINS env var, JSON list) so each deployment can set its own domains.
allowed_origins = ["*"] if settings.app_env == "development" else settings.cors_origins

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Response-Time"],
)


# Include API routers
app.include_router(health_router)  # Health checks at root level
app.include_router(data_router, prefix="/api", tags=["Data Intelligence"])  # B2B Data Platform
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(campaigns.router, prefix="/api", tags=["Campaigns"])  # router self-prefixes /campaigns
app.include_router(analytics.router, prefix="/api", tags=["Analytics"])  # router self-prefixes /analytics
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(billing_router, prefix="/api", tags=["Billing"])
app.include_router(platform_router, prefix="/api", tags=["Platform"])

# AI Staff Team (roster + activity + manual runs) and Marketing (Isha)
try:
    from app.api.team import router as team_router

    app.include_router(team_router, prefix="/api")  # /api/platform/team/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Team router not mounted: {_e}")
try:
    from app.api.marketing import router as marketing_router

    app.include_router(marketing_router, prefix="/api", tags=["Marketing"])  # /api/marketing/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Marketing router not mounted: {_e}")
try:
    from app.api.public_site import router as public_site_router

    app.include_router(public_site_router, prefix="/api")  # /api/public/* (website inquiry form)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Public site router not mounted: {_e}")
app.include_router(ml_router, prefix="/api", tags=["ML Training"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])
app.include_router(ai_router, prefix="/api", tags=["AI"])
app.include_router(customer_dashboard_router, tags=["Customer Dashboard"])  # /api/customer/*
app.include_router(admin_dashboard_router, tags=["Admin Dashboard"])        # /api/admin/*
app.include_router(web_call_router, prefix="/api", tags=["Web Call (Test Mode)"])  # /api/web-call/*
app.include_router(agents_router, prefix="/api", tags=["Agents"])  # /api/agents/* (LangGraph supervisor)
app.include_router(telephony_vobiz_router, prefix="/api", tags=["Telephony"])  # /api/telephony/vobiz/*


# ---------------------------------------------------------------------------
# MCP server — platform admin endpoints as MCP tools (Claude platform-admin)
# Optional dependency: app works fine without fastapi-mcp installed.
# ---------------------------------------------------------------------------
try:
    from fastapi_mcp import FastApiMCP

    _mcp = FastApiMCP(
        app,
        name="LeadGen AI Platform",
        include_tags=["Platform", "Data Intelligence", "Agents"],
    )
    _mcp.mount()
    logger.info("✅ MCP server mounted at /mcp (Platform/Data/Agents tools)")
except ImportError:
    logger.info("fastapi-mcp not installed — MCP exposure disabled")
except Exception as e:
    logger.warning(f"MCP mount failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Frontend serving — dashboards (web app) + marketing website + PWA
# ---------------------------------------------------------------------------
# Marketing website + PWA assets (manifest.json, sw.js, icons) served at /site
_website_dir = FRONTEND_DIR / "website"
if _website_dir.is_dir():
    app.mount("/site", StaticFiles(directory=str(_website_dir), html=True), name="website")


@app.get("/app/customer", tags=["Frontend"])
async def customer_dashboard_page():
    """Customer dashboard (leads, calls, final qualified leads)."""
    return FileResponse(str(FRONTEND_DIR / "customer_dashboard.html"))


@app.get("/app/admin", tags=["Frontend"])
async def admin_dashboard_page():
    """Admin dashboard (clients, agents, campaigns, revenue, health)."""
    return FileResponse(str(FRONTEND_DIR / "admin_dashboard.html"))


@app.get("/app/test-call", tags=["Frontend"])
async def web_call_test_page():
    """Browser web-call test mode — talk to the bot, no real phone call."""
    return FileResponse(str(FRONTEND_DIR / "web_call.html"))


@app.get("/app/team", tags=["Frontend"])
async def team_dashboard_page():
    """AI Staff / Team dashboard (roster, live activity, manual runs)."""
    return FileResponse(str(FRONTEND_DIR / "team_dashboard.html"))


@app.get("/app/marketing", tags=["Frontend"])
async def marketing_page():
    """AI Marketing (Isha) — social posts, content calendar, GBP tips."""
    return FileResponse(str(FRONTEND_DIR / "marketing.html"))


@app.websocket("/telephony/twilio/media-stream")
async def twilio_media_stream(websocket: WebSocket):
    """Twilio Media Streams websocket → live audio bridge to the voice pipeline."""
    try:
        from app.telephony.media_stream import TwilioMediaStreamBridge
        bridge = TwilioMediaStreamBridge()
        await bridge.handle(websocket)
    except Exception as e:
        logger.warning(f"Media-stream bridge error: {e}")
        try:
            await websocket.close()
        except Exception:
            pass


@app.get("/manifest.json", tags=["Frontend"])
async def pwa_manifest():
    """PWA manifest at root scope so the app is installable (inline fallback if file missing)."""
    mf = _website_dir / "manifest.json"
    if mf.is_file():
        return FileResponse(str(mf))
    return JSONResponse({
        "name": "LeadGen AI", "short_name": "LeadGen AI",
        "start_url": "/site/", "display": "standalone",
        "background_color": "#4f46e5", "theme_color": "#4f46e5",
        "description": "AI Voice Agent for B2B Lead Generation",
        "icons": [
            {"src": "/site/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/site/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    })


@app.get("/sw.js", tags=["Frontend"])
async def pwa_service_worker():
    """PWA service worker at root scope for offline caching."""
    sw = _website_dir / "sw.js"
    if sw.is_file():
        return FileResponse(str(sw))
    from fastapi.responses import Response
    return Response("/* no service worker */", media_type="application/javascript")


@app.get("/api/status")
async def api_status():
    """Platform status (JSON) — root ab marketing website serve karta hai."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "platform": {
            "type": "B2B Intelligence Platform",
            "features": [
                "Company Search API",
                "Data Enrichment",
                "Market Reports",
                "Lead Scoring",
            ]
        },
        "message": "🚀 B2B Intelligence Platform - Data that drives revenue!"
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    global platform_orchestrator, ml_scheduler

    return {
        "status": "healthy",
        "platform": {
            "orchestrator": "running" if (platform_orchestrator and platform_orchestrator.is_running) else "stopped",
            "auto_mode": settings.auto_start_platform
        },
        "ml": {
            "scheduler": "running" if ml_scheduler and ml_scheduler.is_running else "stopped",
            "auto_learning": "enabled"
        },
        "services": {
            "api": "operational",
            "database": "check_required",
            "redis": "check_required",
            "telephony": "check_required"
        }
    }


# ---------------------------------------------------------------------------
# Root website mount — LAST so all API/app routes match first; everything
# else (/, /styles.css, /images/...) serves the marketing site (html=True
# makes "/" return index.html). /site mount upar bhi rehta hai (old links).
# ---------------------------------------------------------------------------
if _website_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_website_dir), html=True), name="root_website")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
