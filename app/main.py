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
from app.api.platform import router as platform_router
from app.api.ml_training import router as ml_router
from app.api.health import router as health_router
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global platform_orchestrator, ml_scheduler
    
    # Startup
    logger.info(f"🚀 Starting {settings.app_name}...")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Version: {os.environ.get('APP_VERSION', 'dev')}")
    
    # Initialize database
    try:
        await init_async_db()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.warning(f"Database init failed (may not be configured): {e}")
    
    # Initialize Redis
    try:
        from app.cache import get_redis_client
        await get_redis_client()
        logger.info("✅ Redis initialized")
    except Exception as e:
        logger.warning(f"Redis init failed (using in-memory fallback): {e}")
    
    # AUTO-START: Platform automation (runs 24/7)
    if settings.auto_start_platform and settings.app_env == "production":
        platform_orchestrator = PlatformOrchestrator()
        asyncio.create_task(platform_orchestrator.start())
        logger.info("🤖 Platform orchestrator started - Full automation enabled")
    elif settings.auto_start_platform:
        logger.info("🔧 Platform auto-start disabled in non-production environment")
    
    # AUTO-START: ML Training Scheduler
    try:
        ml_scheduler = await get_training_scheduler()
        logger.info("🧠 ML Training Scheduler started - Auto-learning enabled")
    except Exception as e:
        logger.warning(f"ML Scheduler failed to start: {e}")
    
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
allowed_origins = ["*"] if settings.app_env == "development" else [
    "https://leadgenai.com",
    "https://app.leadgenai.com",
    "https://dashboard.leadgenai.com",
]

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
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(campaigns.router, prefix="/api/campaigns", tags=["Campaigns"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
app.include_router(platform_router, prefix="/api", tags=["Platform"])
app.include_router(ml_router, prefix="/api", tags=["ML Training"])


@app.get("/")
async def root():
    """Root endpoint - Platform status"""
    global platform_orchestrator
    
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": "1.0.0",
        "platform": {
            "running": platform_orchestrator.is_running if platform_orchestrator else False,
            "mode": "FULL_AUTO" if settings.auto_start_platform else "MANUAL"
        },
        "message": "🤖 Multi-Tier B2B Lead Generation Platform is running! 📞"
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


# Startup event to display configuration
@app.on_event("startup")
async def startup_event():
    logger.info("=" * 60)
    logger.info("🤖 AI VOICE AGENT - MULTI-TIER B2B LEAD GENERATION PLATFORM")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📊 PLATFORM MODEL:")
    logger.info("   ├── Tier 1: Platform finds B2B clients (businesses needing leads)")
    logger.info("   └── Tier 2: Each client gets automated voice agent for their leads")
    logger.info("")
    logger.info(f"⚙️  CONFIGURATION:")
    logger.info(f"   ├── Telephony: {settings.default_telephony}")
    logger.info(f"   ├── LLM: {settings.default_llm}")
    logger.info(f"   ├── STT: {settings.default_stt}")
    logger.info(f"   ├── TTS: {settings.default_tts}")
    logger.info(f"   └── ML Auto-Learning: ENABLED")
    logger.info("")
    logger.info(f"🚀 AUTO-START: {'ENABLED' if settings.auto_start_platform else 'DISABLED'}")
    logger.info(f"🧠 ML TRAINING: Nightly at 2:00 AM, Weekly on Sunday")
    logger.info("=" * 60)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
