"""
LeadGen AI - AI Automated Marketing + Voice Agent Platform
FastAPI Main Application - PRODUCTION READY

MULTI-TIER AUTOMATED PLATFORM (marketing-first):
1. Platform finds marketing clients (Indian local businesses)
2. Clients get AI automated marketing (posts/GBP/festivals/posters/reviews/WhatsApp);
   Advanced tier adds an AI voice agent that calls their inquiries
3. Everything runs 24/7 with minimal human intervention
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, campaigns, leads, webhooks
from app.api.admin import router as admin_router
from app.api.admin_dashboard import router as admin_dashboard_router
from app.api.agents import router as agents_router
from app.api.ai import router as ai_router
from app.api.billing import router as billing_router
from app.api.customer_dashboard import router as customer_dashboard_router
from app.api.data import router as data_router
from app.api.health import router as health_router
from app.api.ml_training import router as ml_router
from app.api.platform import router as platform_router
from app.api.telephony_vobiz import router as telephony_vobiz_router
from app.api.web_call import router as web_call_router
from app.config import settings

# Frontend directory (dashboards + marketing website + PWA)
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
from app.cache import close_redis_client
from app.exceptions import setup_exception_handlers
from app.middleware import setup_middleware
from app.ml import stop_training_scheduler
from app.models.base import close_async_db, init_async_db
from app.utils.logger import setup_logger

# Setup logging
logger = setup_logger(__name__)

# Initialize Sentry for error tracking in production
if settings.sentry_dsn and settings.app_env == "production":
    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

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
            before_send_transaction=lambda event, hint: (
                None
                if event.get("transaction") in ["/health", "/health/ready", "/health/live"]
                else event
            ),
        )
        logger.info("✅ Sentry error tracking initialized")
    except ImportError:
        logger.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as e:
        logger.warning(f"Sentry initialization failed: {e}")

# ML scheduler instance (opt-in heavy; PlatformOrchestrator removed — team_scheduler handles all jobs)
ml_scheduler = None


def _log_startup_banner():
    """Display configuration banner on startup."""
    logger.info("=" * 60)
    logger.info("🤖 LEADGEN AI - AI AUTOMATED MARKETING + VOICE AGENT PLATFORM")
    logger.info("=" * 60)
    logger.info("")
    logger.info("📊 PLATFORM MODEL (marketing-first):")
    logger.info("   ├── Tier 1: Platform finds marketing clients (local businesses)")
    logger.info("   └── Tier 2: Unka AI marketing + (Advanced) voice-agent inquiry callbacks")
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
    global ml_scheduler

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

    # Keep the Alembic migration history consistent (best-effort; never blocks boot).
    # create_all() above builds the schema; this stamps/upgrades the version so future
    # migrations apply cleanly. Disable with SKIP_DB_MIGRATIONS=1.
    try:
        from app.models.migrations import run_startup_migrations

        logger.info(f"✅ DB migrations: {run_startup_migrations()}")
    except Exception as e:
        logger.warning(f"Startup migrations skipped: {e}")

    # Redis: lazy singleton — warm it up so /health/ready reflects reality.
    # Fail-open: if Redis is unreachable the cache/rate-limit layers transparently
    # fall back to in-memory. (The old "VPC connector" note was Cloud-Run-specific;
    # on the VPS, Redis is a local container at redis://redis:6379.)
    try:
        from app.cache import get_redis_client

        _redis = await get_redis_client()
        await _redis.ping()
        logger.info("✅ Redis connected")
    except Exception as e:
        logger.warning(f"Redis unavailable (in-memory fallback active): {e}")

    # ML scheduler remains opt-in (heavy). All automation handled by team_scheduler.
    logger.info("⏭️ ML scheduler disabled (opt-in)")

    # AI Staff Team automation (Arjun QA 02:30, Meera trainer 03:00, Kavya ops hourly).
    # Gated by RUN_IN_PROCESS_SCHEDULER (default ON = today's single-process behaviour).
    # When scaling to multiple web workers + a dedicated scheduler container, set this
    # to 0 on the web replicas so jobs never double-fire. See docs/PRODUCTION_CUTOVER.md.
    if os.environ.get("RUN_IN_PROCESS_SCHEDULER", "1").strip().lower() in ("1", "true", "yes"):
        try:
            from app.platform.team_scheduler import start_scheduler

            start_scheduler()
            logger.info("✅ AI Staff Team scheduler started (in-process)")
        except Exception as e:
            logger.warning(f"Team scheduler not started: {e}")
    else:
        logger.info("⏭️ In-process scheduler disabled (RUN_IN_PROCESS_SCHEDULER=0)")

    # KB embedder PRE-WARM (off-loop, background, fire-and-forget) — pehle voice
    # turn ka ~8-12s cold-load (fastembed model RAM-load) startup pe nipta do taaki
    # first call snappy ho. ⚠️ NEVER block boot / event-loop (prod-down #3: embedder
    # load loop pe = HTTP starve) — isliye run_in_executor (thread) me. Gated KB_PREWARM.
    if os.environ.get("KB_PREWARM", "1").strip().lower() in ("1", "true", "yes"):
        try:
            import asyncio as _aio

            async def _prewarm_kb() -> None:
                try:
                    from app.voice_agent.knowledge_base import _get_qdrant_embedder

                    await _aio.get_running_loop().run_in_executor(None, _get_qdrant_embedder)
                    logger.info("✅ KB embedder pre-warmed (voice first-turn fast)")
                except Exception as _e:
                    logger.warning(f"KB prewarm skipped: {_e}")

            _aio.create_task(_prewarm_kb())
        except Exception as e:
            logger.warning(f"KB prewarm not scheduled: {e}")

    logger.info("✅ Startup complete - application ready")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    if ml_scheduler:
        await stop_training_scheduler()
    await close_async_db()
    await close_redis_client()
    logger.info("✅ Graceful shutdown complete")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    description="LeadGen AI — AI Automated Marketing + Voice Agent platform for Indian businesses (posts, GBP, posters, reviews, WhatsApp; Advanced tier me AI voice agent jo inquiries ko call kare)",
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

# OpenTelemetry distributed tracing — import-safe, OFF unless ENABLE_OTEL=1.
# (Sentry + Prometheus aaj jaisa hi; yeh sirf end-to-end traces add karta.)
try:
    from app.observability_otel import setup_otel

    setup_otel(app)
except Exception as _otel_e:  # never block boot on observability wiring
    logger.warning(f"OTel wiring skipped: {_otel_e}")

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

# PostHog web-analytics snippet auto-inject (G3) — OFF by default. POSTHOG_API_KEY
# unset = har response untouched (turant passthrough). Never blocks boot.
try:
    from app.middleware.analytics_inject import PostHogInjectMiddleware

    app.add_middleware(PostHogInjectMiddleware)
except Exception as _ph_e:  # pragma: no cover
    logger.warning(f"PostHog inject middleware skipped: {_ph_e}")


# Include API routers
app.include_router(health_router)  # Health checks at root level
app.include_router(data_router, prefix="/api", tags=["Data Intelligence"])  # B2B Data Platform
app.include_router(leads.router, prefix="/api/leads", tags=["Leads"])
app.include_router(
    campaigns.router, prefix="/api", tags=["Campaigns"]
)  # router self-prefixes /campaigns
app.include_router(
    analytics.router, prefix="/api", tags=["Analytics"]
)  # router self-prefixes /analytics
app.include_router(webhooks.router, prefix="/api/webhooks", tags=["Webhooks"])
# Telephony provider callbacks (Twilio/Exotel voice + status). Routes are
# signature-verified; Sentry's FastApiIntegration auto-captures their errors.
try:
    from app.telephony.webhooks import router as telephony_webhooks_router

    app.include_router(
        telephony_webhooks_router, prefix="/api/webhooks", tags=["Telephony Webhooks"]
    )
except Exception as _e:  # pragma: no cover
    logger.warning(f"Telephony webhooks router not mounted: {_e}")
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
try:
    from app.api.booking import router as booking_router

    app.include_router(booking_router, prefix="/api")  # /api/booking/* (Calendly-lite slots+book)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Booking router not mounted: {_e}")
try:
    from app.api.customer_auth import router as customer_auth_router

    app.include_router(customer_auth_router, prefix="/api")  # /api/customer/auth/* (client login portal)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer auth router not mounted: {_e}")
try:
    from app.api.impersonation import router as impersonation_router

    app.include_router(impersonation_router, prefix="/api")  # /api/impersonate/* (super-admin login-as-customer, GATED)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Impersonation router not mounted: {_e}")
try:
    from app.api.clients import router as clients_router

    app.include_router(
        clients_router, prefix="/api"
    )  # /api/clients/* (marketing clients + auto content)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Clients router not mounted: {_e}")
try:
    from app.api.whatsapp import router as whatsapp_router

    app.include_router(whatsapp_router, prefix="/api", tags=["WhatsApp"])  # /api/wa/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"WhatsApp router not mounted: {_e}")
try:
    from app.api.minisite_builder import router as minisite_builder_router

    app.include_router(minisite_builder_router, prefix="/api")  # /api/minisite/* (mini-site builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Mini-site builder router not mounted: {_e}")
try:
    from app.api.journeys import router as journeys_router

    app.include_router(journeys_router, prefix="/api")  # /api/journeys/* (omnichannel rule engine)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Journeys router not mounted: {_e}")
try:
    from app.api.growth import router as growth_router

    app.include_router(growth_router, prefix="/api")  # /api/growth/* (lead-score, review, flows, missed-call)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Growth router not mounted: {_e}")
try:
    from app.api.activation import router as _activation_router

    # /api/activation/readiness — launch-blocker / activation-debt snapshot (F.2).
    # Admin-only, env shape-checks only (no outbound calls).
    app.include_router(_activation_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Activation router not mounted: {_e}")
try:
    from app.api.eval_gate import router as _eval_gate_router

    # /api/eval-gate/* — DeepEval close-the-loop reward signal (F.3).
    # Admin-only summary + recent-scores view for self_improve safety rail.
    app.include_router(_eval_gate_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Eval-gate router not mounted: {_e}")
try:
    from app.api.agent_memory_admin import router as _agent_memory_admin_router

    # /api/agent-memory/* — operator inspect + DPDP-compliant purge (F.4).
    # Admin-only; INERT when AGENT_MEMORY flag unset (backend itself returns []).
    app.include_router(_agent_memory_admin_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Agent-memory admin router not mounted: {_e}")
try:
    from app.api.engineer_agents import router as _engineer_agents_router

    # /api/engineer-agents/* — F.5 SRE (Pranav) + FinOps (Vidya) + Security
    # (Arnav). Admin-only score/KPI rollup; INERT when role flag unset.
    app.include_router(_engineer_agents_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Engineer-agents router not mounted: {_e}")
try:
    from app.api.customer_webhooks import router as _customer_webhooks_router

    # /api/customer/webhooks/* — H.1 customer-facing webhooks (sellable SaaS
    # feature). Customer-JWT gated; INERT when CUSTOMER_WEBHOOKS unset.
    app.include_router(_customer_webhooks_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer-webhooks router not mounted: {_e}")
try:
    from app.api.customer_totp import router as _customer_totp_router

    # /api/customer/2fa/* — H.2 customer-side TOTP 2FA. Opt-in per customer.
    # customer_auth.login flow checks is_enabled() before issuing the JWT.
    app.include_router(_customer_totp_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer-TOTP router not mounted: {_e}")
try:
    from app.api.mcp_product import router as _mcp_product_router

    # H.3 MCP-as-product + A2A Agent Card. Public discovery + metered
    # capabilities under X-LeadGen-Key. INERT when MCP_PRODUCT unset.
    app.include_router(_mcp_product_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"MCP-product router not mounted: {_e}")
try:
    from app.api.h4_admin import router as _h4_router

    # H.4 warm-DR + LiteLLM per-tenant cost rollup. Admin-only; INERT when
    # DR_REPLICA_URL / LITELLM_COSTS unset.
    app.include_router(_h4_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"H.4 router not mounted: {_e}")
try:
    from app.api import conversion as _conversion

    app.include_router(_conversion.public_router, prefix="/api")  # /api/public/widget-chat, /lead-in, /trial-status
    app.include_router(_conversion.admin_router, prefix="/api")  # /api/conversion/* (widget form builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Conversion router not mounted: {_e}")
try:
    from app.api.creative import router as creative_router

    app.include_router(creative_router, prefix="/api")  # /api/creative/* (jingle, bg-remove, multilang status)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Creative router not mounted: {_e}")
try:
    from app.api.clientcrm import router as clientcrm_router

    app.include_router(clientcrm_router, prefix="/api")  # /api/clientcrm/* (end-customer CRM, catalog, payment links)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ClientCRM router not mounted: {_e}")
try:
    from app.api.seoops import router as seoops_router

    app.include_router(seoops_router, prefix="/api")  # /api/seoops/* (rank tracker, conversations, dialer)
except Exception as _e:  # pragma: no cover
    logger.warning(f"SeoOps router not mounted: {_e}")
try:
    from app.api.engage import redirect_router as _redirect_router
    from app.api.engage import router as engage_router

    app.include_router(engage_router, prefix="/api")  # /api/engage/* (upi-qr, short-links, reviews-widget, alerts)
    app.include_router(_redirect_router)  # /r/{code} short-link redirect (NO prefix)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Engage router not mounted: {_e}")
try:
    from app.api.privacy_ops import router as privacy_ops_router

    app.include_router(privacy_ops_router, prefix="/api")  # /api/privacy/* (DPDP export/erasure)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Privacy-ops router not mounted: {_e}")
try:
    from app.api.memory_api import router as memory_router

    app.include_router(memory_router, prefix="/api")  # /api/memory/* (compounding memory, call-prep, live notes)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Memory router not mounted: {_e}")
try:
    from app.api.events import router as events_router

    app.include_router(events_router, prefix="/api")  # /api/events/stream (SSE real-time feed)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Events router not mounted: {_e}")
try:
    from app.api.brandassets import router as brandassets_router

    app.include_router(brandassets_router, prefix="/api")  # /api/brand/* (frames, card, resize, review-post, stickers)
except Exception as _e:  # pragma: no cover
    logger.warning(f"BrandAssets router not mounted: {_e}")
try:
    from app.api.clientops import router as clientops_router

    app.include_router(clientops_router, prefix="/api")  # /api/clientops/* (speed-to-lead, approvals, snapshots, routing, proposals)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ClientOps router not mounted: {_e}")
try:
    from app.api.voiceai import router as voiceai_router

    app.include_router(voiceai_router, prefix="/api")  # /api/voiceai/* (transfer, ask-AI, leaderboard)
except Exception as _e:  # pragma: no cover
    logger.warning(f"VoiceAI router not mounted: {_e}")
try:
    from app.api.voice_product import router as voice_product_router

    app.include_router(voice_product_router, prefix="/api")  # /api/voice/* (Product 2: packages, quota, lead packs — ADR-009)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Voice Product router not mounted: {_e}")
try:
    from app.api.combo_product import router as combo_product_router

    app.include_router(combo_product_router, prefix="/api")  # /api/combo/* (Product 3: AI Growth Suite combo)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Combo Product router not mounted: {_e}")
try:
    from app.api.niche_db import router as niche_db_router

    app.include_router(niche_db_router, prefix="/api")  # /api/niche/* (niche prospect database + call queue)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Niche DB router not mounted: {_e}")
try:
    from app.api.localseo import router as localseo_router

    app.include_router(localseo_router, prefix="/api")  # /api/localseo/* (geo-visibility, grid-rank, listings)
except Exception as _e:  # pragma: no cover
    logger.warning(f"LocalSEO router not mounted: {_e}")
try:
    from app.api.contentplus import router as contentplus_router

    app.include_router(contentplus_router, prefix="/api")  # /api/contentplus/* (clips, gif, avatar, service-reminders, A/B)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ContentPlus router not mounted: {_e}")
try:
    from app.api.widgets import router as widgets_router

    app.include_router(widgets_router, prefix="/api")  # /api/widgets/* (popup pack, bio-link, beacon analytics)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Widgets router not mounted: {_e}")
try:
    from app.api.lifecycle import router as lifecycle_router

    app.include_router(lifecycle_router, prefix="/api")  # /api/lifecycle/* (newsletter, winback, signature, lead-magnet)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Lifecycle router not mounted: {_e}")
try:
    from app.api.contentauto import router as contentauto_router

    app.include_router(contentauto_router, prefix="/api")  # /api/contentauto/* (repurpose, pulse, month-plan, team-report, push)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ContentAuto router not mounted: {_e}")
app.include_router(ml_router, prefix="/api", tags=["ML Training"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])
try:
    from app.api.team_access import router as team_access_router

    app.include_router(team_access_router, prefix="/api")  # /api/team-access/* (sub-admins + module grants)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Team-access router not mounted: {_e}")
app.include_router(ai_router, prefix="/api", tags=["AI"])
app.include_router(customer_dashboard_router, tags=["Customer Dashboard"])  # /api/customer/*
app.include_router(admin_dashboard_router, tags=["Admin Dashboard"])  # /api/admin/*
app.include_router(web_call_router, prefix="/api", tags=["Web Call (Test Mode)"])  # /api/web-call/*
app.include_router(
    agents_router, prefix="/api", tags=["Agents"]
)  # /api/agents/* (LangGraph supervisor)
app.include_router(
    telephony_vobiz_router, prefix="/api", tags=["Telephony"]
)  # /api/telephony/vobiz/*


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


@app.get("/app/login", tags=["Frontend"])
async def customer_login_page():
    """Customer (client) login portal — leads/calls/content for their account."""
    return FileResponse(str(FRONTEND_DIR / "login.html"))


@app.get("/app/analytics", tags=["Frontend"])
async def analytics_page():
    """Analytics dashboard — funnel, call/lead stats, revenue (Chart.js over live-stats)."""
    return FileResponse(str(FRONTEND_DIR / "analytics.html"))


@app.get("/app/agents", tags=["Frontend"])
async def agents_page():
    """Live multi-agent coordination dashboard — roster, Reflexion coordinate, debate,
    episodic memory. Calls /api/agents/* (admin token for POSTs)."""
    return FileResponse(str(FRONTEND_DIR / "agents.html"))


@app.get("/app/ops", tags=["Frontend"])
async def ops_page():
    """Ops Mission Control — automation health (dead-man), LLM observability,
    telephony readiness, flags, DLQ, weakest-funnel — sab /api/growth/infra/* se."""
    return FileResponse(str(FRONTEND_DIR / "ops.html"))


@app.get("/app/team-access", tags=["Frontend"])
async def team_access_page():
    """Team access management — sub-admins + module grants (super admin UI)."""
    return FileResponse(str(FRONTEND_DIR / "team_access.html"))


@app.get("/app/admin-login", tags=["Frontend"])
async def admin_login_page():
    """Admin login — email+password → /api/admin/auth/login → sets accessToken (unlocks
    all admin dashboards). Without this, admin pages 401 (no token)."""
    return FileResponse(str(FRONTEND_DIR / "admin_login.html"))


@app.get("/app/calendar", tags=["Frontend"])
async def calendar_page():
    """Content calendar month-view (Buffer-style) — schedule + bookings."""
    return FileResponse(str(FRONTEND_DIR / "calendar.html"))


@app.get("/app/deals", tags=["Frontend"])
async def deals_page():
    """Sales pipeline kanban (drag-drop) over /api/growth/sales/*."""
    return FileResponse(str(FRONTEND_DIR / "deals.html"))


@app.get("/app/inbox", tags=["Frontend"])
async def inbox_page():
    """Unified action inbox — hot leads, reply/review drafts, experiments."""
    return FileResponse(str(FRONTEND_DIR / "inbox.html"))


@app.get("/app/studio", tags=["Frontend"])
async def studio_page():
    """AI Studio — photo→poster (image-to-image), AI poster, template gallery."""
    return FileResponse(str(FRONTEND_DIR / "studio.html"))


@app.get("/app/onboard", tags=["Frontend"])
async def onboard_page():
    """Naya client onboarding wizard (4 steps, self-serve)."""
    return FileResponse(str(FRONTEND_DIR / "onboard.html"))


@app.get("/status", tags=["Frontend"])
async def status_page():
    """Public system status page (health/ready client-side checks)."""
    return FileResponse(str(FRONTEND_DIR / "status.html"))


@app.get("/pwa-icon-{size}.png", include_in_schema=False)
async def pwa_icon(size: int):
    """PWA icon runtime-generate (PIL) + disk cache — koi binary repo me nahi."""
    from fastapi.responses import Response as _Resp

    size = 192 if int(size) not in (192, 512) else int(size)
    icon_path = Path("data") / f"pwa_icon_{size}.png"
    try:
        if not icon_path.exists():
            from PIL import Image, ImageDraw, ImageFont

            img = Image.new("RGB", (size, size), (37, 99, 235))
            dr = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("DejaVuSans-Bold.ttf", size // 3)
            except Exception:
                font = ImageFont.load_default()
            bb = dr.textbbox((0, 0), "LG", font=font)
            dr.text(((size - bb[2] + bb[0]) / 2, (size - bb[3] + bb[1]) / 2 - bb[1]), "LG", fill="white", font=font)
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(icon_path)
        return FileResponse(str(icon_path), media_type="image/png")
    except Exception:
        return _Resp(status_code=404)


@app.get("/app/customer", tags=["Frontend"])
async def customer_dashboard_page():
    """Customer dashboard (leads, calls, final qualified leads)."""
    return FileResponse(str(FRONTEND_DIR / "customer_dashboard.html"))


@app.get("/app/admin", tags=["Frontend"])
async def admin_dashboard_page():
    """Admin dashboard (clients, agents, campaigns, revenue, health)."""
    return FileResponse(str(FRONTEND_DIR / "admin_dashboard.html"))


@app.get("/app/impersonate", tags=["Frontend"])
async def impersonate_page():
    """Super-admin 'login as customer' support tool (gated IMPERSONATION=1; audited)."""
    return FileResponse(str(FRONTEND_DIR / "impersonate.html"))


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


@app.get("/app/whatsapp", tags=["Frontend"])
async def whatsapp_page():
    """WhatsApp Cloud API panel — templates, campaigns, suppression (auto-send gated)."""
    return FileResponse(str(FRONTEND_DIR / "whatsapp.html"))


@app.get("/app/minisite-builder", tags=["Frontend"])
async def minisite_builder_page():
    """Mini-site builder — palette/layout/logo, booking calendar, reviews for /b/{slug}."""
    return FileResponse(str(FRONTEND_DIR / "minisite_builder.html"))


@app.get("/app/outreach", tags=["Frontend"])
async def outreach_page():
    """Rohan ka outreach queue — Tier-1 client prospects (WhatsApp pitch)."""
    return FileResponse(str(FRONTEND_DIR / "outreach.html"))


@app.get("/app/clients", tags=["Frontend"])
async def clients_page():
    """Clients — marketing client store + per-client auto content engine."""
    return FileResponse(str(FRONTEND_DIR / "clients.html"))


@app.get("/pricing", tags=["Frontend"])
async def pricing_page():
    """PUBLIC self-serve revenue funnel: pricing → signup → Razorpay checkout.

    Backend already built (/api/billing/plans, /billing/checkout, /billing/verify-payment,
    /api/public/signup). Payment keys unset ho to page graceful UPI/contact fallback dikhata.
    """
    return FileResponse(str(FRONTEND_DIR / "pricing.html"))


@app.get("/start", tags=["Frontend"])
async def start_alias_page():
    """CTA-friendly alias for /pricing."""
    return FileResponse(str(FRONTEND_DIR / "pricing.html"))


@app.get("/app/assistant", tags=["Frontend"])
async def assistant_page():
    """NL CRM command bar (Expedify-style 'talk to your CRM') — Hinglish NL -> action.

    Calls POST /api/ai/command (read/draft only, free-LLM intent). Auto-send nahi.
    """
    return FileResponse(str(FRONTEND_DIR / "assistant.html"))


@app.get("/app/journeys", tags=["Frontend"])
async def journeys_page():
    """Omnichannel journey/rule engine admin (Expedify-style) — event→action drafts.

    CRUD over /api/journeys/* (admin token). Engine gated JOURNEY_ENGINE=1.
    """
    return FileResponse(str(FRONTEND_DIR / "journeys.html"))


@app.get("/app/growth-tools", tags=["Frontend"])
async def growth_tools_page():
    """Growth Tools admin — UPI QR, jingle, bg-remove, multilang-9, rank tracker,
    catalog, customer CRM, short links, reviews widget, memory, lead webhook."""
    return FileResponse(str(FRONTEND_DIR / "growth_tools.html"))


@app.get("/app/command-center", tags=["Frontend"])
async def command_center_page():
    """Command Center — real-time KPIs, funnel, LLM health, staff roster, automation flags."""
    return FileResponse(str(FRONTEND_DIR / "command_center.html"))


@app.get("/app/automation", tags=["Frontend"])
async def automation_page():
    """Automation Mission Control — API-only features ka UI: harvester, prospects,
    cadence, sales-team AI, process approvals, self-improve, upgrader, drafters,
    revenue ops, research (SearXNG/ntfy), content+."""
    return FileResponse(str(FRONTEND_DIR / "automation.html"))


@app.get("/app/dashboards", tags=["Frontend"])
async def dashboards_page():
    """H.5 unified admin dashboards — single pane surfacing activation-
    readiness, engineer agents, eval-gate, agent memory, MCP keys, DR +
    LiteLLM cost, customer webhooks, Turnstile config. Auto-refresh 30s.
    Admin token from localStorage (adminToken or accessToken)."""
    return FileResponse(str(FRONTEND_DIR / "dashboards.html"))


@app.get("/app/conversations", tags=["Frontend"])
async def conversations_page():
    """Unified conversation inbox (GHL-style) — email replies + web-chat + inquiries ek thread view.

    Reads /api/seoops/conversations (admin token). Reply = DRAFT/1-click only, auto-send nahi.
    """
    return FileResponse(str(FRONTEND_DIR / "conversations.html"))


@app.get("/app/dialer", tags=["Frontend"])
async def dialer_page():
    """Human telecaller dialer mode (NeoDove-style) — lead queue, tel:/wa.me 1-click, dispositions."""
    return FileResponse(str(FRONTEND_DIR / "dialer.html"))


@app.get("/audit", tags=["Frontend"])
async def public_audit_page():
    """PUBLIC lead-magnet: FREE GBP audit funnel (questions → score → inquiry)."""
    return FileResponse(str(_website_dir / "audit.html"))


@app.get("/site-audit", tags=["Frontend"])
async def public_site_audit_page():
    """PUBLIC lead-magnet #2: website URL → AI report card (score/tips/CTA).
    POST /api/growth/tools/website-audit ko call karta (rate-limited)."""
    return FileResponse(str(_website_dir / "site-audit.html"))


@app.get("/demo", tags=["Frontend"])
async def public_demo_page():
    """PUBLIC lead-magnet: AI marketing preview — business naam → real posts/hashtags/offer
    (POST /api/public/ai-demo). Shows prospects what LeadGenAI's AI team builds for them."""
    return FileResponse(str(_website_dir / "demo.html"))


@app.get("/voice-agent", tags=["Frontend"])
async def voice_agent_product_page():
    """PUBLIC: Product 2 — AI Voice Calling Agent (standalone) landing + pricing.

    Pricing GET /api/voice/packages se (per-niche per-10-qualified-leads, ADR-009).
    Marketing product (/pricing) se ALAG page — bundle framing nahi.
    """
    return FileResponse(str(_website_dir / "voice-agent.html"))


@app.get("/compare", tags=["Frontend"])
async def public_compare_page():
    """PUBLIC: competitor comparison page (dono products ALAG sections) — SEO + conversion.

    Marketing: vs Dhanda/Predis/AdBanao/Practina/GHL. Voice: vs SquadStack/Vodex/
    Exotel/Knowlarity/CallHippo. Data June 2026 public sources; bundle framing NAHI.
    """
    return FileResponse(str(_website_dir / "compare.html"))


@app.get("/privacy", tags=["Frontend"])
async def privacy_page():
    """Privacy policy (static legal page)."""
    return FileResponse(str(_website_dir / "privacy.html"))


@app.get("/terms", tags=["Frontend"])
async def terms_page():
    """Terms of service (static legal page)."""
    return FileResponse(str(_website_dir / "terms.html"))


@app.get("/refund", tags=["Frontend"])
async def refund_page():
    """Refund policy (static legal page)."""
    return FileResponse(str(_website_dir / "refund.html"))


@app.get("/robots.txt", include_in_schema=False)
async def robots_txt():
    """SEO: robots.txt at root with explicit text/plain media type."""
    return FileResponse(str(_website_dir / "robots.txt"), media_type="text/plain")


@app.get("/indexnow-key.txt", include_in_schema=False)
async def indexnow_key_txt():
    """IndexNow key-file (Bing/Yandex ownership verify) — keyLocation isi pe point karti."""
    from fastapi.responses import PlainTextResponse

    from app.marketing import indexnow

    return PlainTextResponse(indexnow.get_key())


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    """SEO: DYNAMIC sitemap — static pages + every published /blog/{slug}.

    Programmatic SEO blog ke saare articles yahan auto-include hote hain taaki
    Google unhe crawl kare. base URL CORS origin / request host se nikalti hai.
    """
    from xml.sax.saxutils import escape as _xesc

    from fastapi.responses import Response

    # base URL (production domain pehle; warna request host)
    base = "https://leadsgenai.in"
    try:
        origins = settings.cors_origins or []
        for o in origins:
            if o and o.startswith("http") and "*" not in o:
                base = o.rstrip("/")
                break
    except Exception:
        pass

    static_paths = ["/", "/audit", "/pricing", "/voice-agent", "/compare", "/demo", "/site-audit", "/app/test-call", "/privacy", "/terms", "/refund"]
    urls: list[str] = list(static_paths)
    try:
        from app.marketing import seo_blog

        for slug in seo_blog.all_slugs():
            if slug:
                urls.append(f"/blog/{slug}")
    except Exception as e:  # blog module missing => sirf static pages
        logger.debug(f"sitemap blog slugs skipped: {e}")

    # Per-client mini-sites (/b/{slug}) — active clients hi (paused/dead skip).
    try:
        from app.marketing.clients_store import list_clients

        for c in list_clients(status="active"):
            slug = str(c.get("slug") or "").strip()
            if slug:
                urls.append(f"/b/{slug}")
    except Exception as e:  # clients_store missing => skip
        logger.debug(f"sitemap mini-site slugs skipped: {e}")

    items = "\n".join(f"  <url><loc>{_xesc(base + p)}</loc></url>" for p in urls)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{items}\n"
        "</urlset>\n"
    )
    return Response(content=xml, media_type="application/xml")


# ---------------------------------------------------------------------------
# Programmatic SEO blog — auto-published niche articles (inbound lead magnet)
# ---------------------------------------------------------------------------
_BLOG_CSS = """
:root{--indigo:#4f46e5;--violet:#7c3aed;--ink:#0f1024;--muted:#64647e;
--bg:#fff;--bg-soft:#f6f6fb;--line:#e8e8f2;--radius:16px}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
color:var(--ink);background:var(--bg);line-height:1.7;-webkit-font-smoothing:antialiased}
a{color:var(--indigo);text-decoration:none}
.wrap{max-width:760px;margin:0 auto;padding:0 20px}
header.nav{position:sticky;top:0;z-index:50;background:rgba(255,255,255,.9);
backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.nav-inner{display:flex;align-items:center;justify-content:space-between;height:64px;
max-width:760px;margin:0 auto;padding:0 20px}
.brand{display:flex;align-items:center;gap:9px;font-weight:800;font-size:1.15rem;
font-family:'Plus Jakarta Sans',system-ui,sans-serif;color:var(--ink)}
.brand .logo{width:32px;height:32px;border-radius:9px;
background:linear-gradient(135deg,var(--indigo),var(--violet));display:grid;
place-items:center;color:#fff;font-weight:800}
.btn{display:inline-flex;align-items:center;gap:8px;font-weight:600;font-size:.92rem;
padding:11px 18px;border-radius:11px;cursor:pointer;border:1.5px solid transparent}
.btn-primary{background:linear-gradient(135deg,var(--indigo),var(--violet));color:#fff;
box-shadow:0 16px 40px -18px rgba(79,70,229,.5)}
.btn-ghost{background:#fff;color:var(--ink);border-color:var(--line)}
h1,h2,h3{font-family:'Plus Jakarta Sans',system-ui,sans-serif;letter-spacing:-.02em;
line-height:1.2;color:var(--ink)}
.lead{padding:40px 0 16px}
.lead h1{font-size:clamp(1.6rem,4.5vw,2.4rem);font-weight:800;margin-bottom:10px}
.lead p.sub{color:var(--muted);font-size:1.05rem}
article h2{font-size:1.3rem;font-weight:700;margin:30px 0 10px}
article p{margin:0 0 14px;color:#23243f}
.meta{color:var(--muted);font-size:.86rem;margin-bottom:6px}
.cardlist{display:grid;gap:16px;padding:24px 0 60px}
.card{display:block;background:#fff;border:1px solid var(--line);border-radius:var(--radius);
padding:20px 22px;transition:transform .2s,box-shadow .2s,border-color .2s}
.card:hover{transform:translateY(-3px);box-shadow:0 16px 40px -22px rgba(15,16,36,.3);
border-color:#818cf8}
.card h3{font-size:1.12rem;margin-bottom:6px;color:var(--ink)}
.card p{color:var(--muted);font-size:.94rem;margin:0}
.card .tag{display:inline-block;font-size:.72rem;font-weight:600;color:var(--indigo);
background:#eef0ff;padding:3px 10px;border-radius:999px;margin-bottom:10px}
.cta-box{margin:34px 0 56px;padding:26px;border-radius:18px;
background:linear-gradient(135deg,#eef0ff,#f6f0ff);border:1px solid var(--line)}
.cta-box h3{font-size:1.2rem;margin-bottom:8px}
.cta-box p{color:var(--muted);margin-bottom:16px}
.cta-row{display:flex;gap:12px;flex-wrap:wrap}
footer{border-top:1px solid var(--line);padding:26px 0;color:var(--muted);font-size:.86rem}
.empty{padding:60px 0;text-align:center;color:var(--muted)}
"""

_BLOG_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&'
    'family=Inter:wght@400;500;600&display=swap" rel="stylesheet">'
)


def _blog_header() -> str:
    return (
        '<header class="nav"><div class="nav-inner">'
        '<a href="/" class="brand"><span class="logo">L</span>LeadGen AI</a>'
        '<a href="/audit" class="btn btn-primary">FREE Google Audit</a>'
        "</div></header>"
    )


def _blog_footer() -> str:
    return (
        '<footer><div class="wrap">© LeadGen AI — AI Marketing for Indian businesses · '
        '<a href="/">Home</a> · <a href="/blog">Blog</a> · '
        '<a href="/audit">Free Audit</a> · '
        '<a href="https://wa.me/918459012607">WhatsApp</a></div></footer>'
    )


def _cta_box() -> str:
    return (
        '<div class="cta-box"><h3>Apni marketing badhani hai?</h3>'
        "<p>2 minute me free Google audit lijiye — hum batayenge kahan kami hai aur "
        'kaise theek karein. Bilkul free.</p><div class="cta-row">'
        '<a href="/audit" class="btn btn-primary">🚀 FREE Audit nikalo</a>'
        '<a href="https://wa.me/918459012607" class="btn btn-ghost">💬 WhatsApp pe baat karo</a>'
        "</div></div>"
    )


@app.get("/blog", tags=["Frontend"], include_in_schema=False)
async def blog_index():
    """Programmatic SEO blog — sab articles ki list (newest first)."""
    from html import escape as _h

    from fastapi.responses import HTMLResponse

    articles = []
    try:
        from app.marketing import seo_blog

        articles = seo_blog.list_articles(limit=300)
    except Exception as e:
        logger.warning(f"blog index list failed: {e}")

    cards = []
    for a in articles:
        slug = _h(str(a.get("slug") or ""))
        title = _h(str(a.get("title") or slug))
        meta = _h(str(a.get("meta_description") or ""))
        niche = _h(str(a.get("niche") or "").replace("_", " ").title())
        city = _h(str(a.get("city") or ""))
        tag = f"{niche}{(' · ' + city) if city else ''}" or "Marketing"
        cards.append(
            f'<a class="card" href="/blog/{slug}">'
            f'<span class="tag">{tag}</span>'
            f"<h3>{title}</h3><p>{meta}</p></a>"
        )
    body = (
        "".join(cards)
        if cards
        else '<div class="empty">Abhi koi article publish nahi hua — jald aa raha hai!</div>'
    )

    html = (
        '<!DOCTYPE html><html lang="en-IN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>Marketing Blog — Local Business Tips (Hinglish) | LeadGen AI</title>"
        '<meta name="description" content="Local business marketing tips Hinglish me — '
        "Instagram, Google Business Profile, festival posters, WhatsApp aur reviews. "
        'Restaurant, salon, real estate aur 40+ niches ke liye free guides.">'
        f'<link rel="canonical" href="/blog">{_BLOG_FONTS}'
        f"<style>{_BLOG_CSS}</style></head><body>"
        f"{_blog_header()}"
        '<div class="wrap"><div class="lead">'
        "<h1>Marketing Blog — Local Business Growth Tips</h1>"
        '<p class="sub">Instagram, Google, festival posters, WhatsApp aur reviews — '
        "har niche ke liye free, kaam ki Hinglish guides.</p></div>"
        f'<div class="cardlist">{body}</div>'
        f"{_cta_box()}</div>{_blog_footer()}</body></html>"
    )
    return HTMLResponse(content=html)


@app.get("/blog/{slug}", tags=["Frontend"], include_in_schema=False)
async def blog_article(slug: str):
    """Ek SEO article render karo (404-safe → /blog redirect)."""
    from html import escape as _h

    from fastapi.responses import HTMLResponse, RedirectResponse

    article = None
    try:
        from app.marketing import seo_blog

        article = seo_blog.get_article(slug)
    except Exception as e:
        logger.warning(f"blog article load failed: {e}")
    if not article:
        return RedirectResponse(url="/blog", status_code=302)

    title = _h(str(article.get("title") or "Article"))
    meta = _h(str(article.get("meta_description") or ""))
    niche = _h(str(article.get("niche") or "").replace("_", " ").title())
    city = _h(str(article.get("city") or ""))
    created = _h(str(article.get("created_at") or "")[:10])
    body_html = str(article.get("html_body") or "")  # trusted: our generator, clean <h2>/<p>
    crumb = f"{niche}{(' · ' + city) if city else ''}"

    html = (
        '<!DOCTYPE html><html lang="en-IN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        f"<title>{title} | LeadGen AI</title>"
        f'<meta name="description" content="{meta}">'
        f'<link rel="canonical" href="/blog/{_h(slug)}">{_BLOG_FONTS}'
        f"<style>{_BLOG_CSS}</style></head><body>"
        f"{_blog_header()}"
        '<div class="wrap"><div class="lead">'
        f'<p class="meta">{crumb}{(" · " + created) if created else ""} · '
        '<a href="/blog">← Sab articles</a></p>'
        f"<h1>{title}</h1></div>"
        f"<article>{body_html}</article>"
        f"{_cta_box()}</div>{_blog_footer()}</body></html>"
    )
    return HTMLResponse(content=html)


# ---------------------------------------------------------------------------
# Per-client MINI WEBSITE + booking page — /b/{slug} (free deliverable)
# ---------------------------------------------------------------------------
@app.get("/b/{slug}", tags=["Frontend"], include_in_schema=False)
async def mini_site_page(slug: str):
    """Ek marketing client ka mini-site render karo (404-safe → / redirect).

    Page brand-colored hota hai + enquiry/booking form POST /api/public/inquiry
    par jata hai (hidden source_slug se lead funnel me capture). Kabhi 500 nahi.
    """
    from fastapi.responses import HTMLResponse, RedirectResponse

    client = None
    try:
        from app.marketing.clients_store import get_by_slug

        client = get_by_slug(slug)
    except Exception as e:
        logger.warning(f"mini-site lookup failed for {slug!r}: {e}")
    if not client:
        return RedirectResponse(url="/", status_code=302)

    try:
        from app.marketing.mini_site import render_site

        html = render_site(client)
    except Exception as e:  # render_site khud never-raise hai, par double-guard
        logger.warning(f"mini-site render failed for {slug!r}: {e}")
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(content=html)


@app.get("/b/{slug}/card", tags=["Frontend"], include_in_schema=False)
async def client_card_page(slug: str):
    """Digital visiting card (AdBanao-parity) — mobile-first, .vcf save-contact + QR. Kabhi 500 nahi."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    try:
        from app.marketing import business_card

        res = business_card.render_card_html(slug)
        if res.get("ok"):
            return HTMLResponse(content=res["html"])
    except Exception as e:
        logger.warning(f"card render failed for {slug!r}: {e}")
    return RedirectResponse(url="/", status_code=302)


@app.get("/b/{slug}/bio", tags=["Frontend"], include_in_schema=False)
async def client_bio_page(slug: str):
    """Bio-link page (Linktree-killer) — mobile-first, brand-colored. Kabhi 500 nahi."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    try:
        from app.marketing import bio_link

        res = bio_link.render_bio_html(slug)
        if res.get("ok"):
            return HTMLResponse(content=res["html"])
    except Exception as e:
        logger.warning(f"bio render failed for {slug!r}: {e}")
    return RedirectResponse(url="/", status_code=302)


@app.get("/b/{slug}/embed", tags=["Frontend"], include_in_schema=False)
async def mini_site_embed(slug: str):
    """Iframe-able lead-capture form for a client's OWN website (embed widget content)."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    client = None
    try:
        from app.marketing.clients_store import get_by_slug

        client = get_by_slug(slug)
    except Exception as e:
        logger.warning(f"embed lookup failed for {slug!r}: {e}")
    if not client:
        return RedirectResponse(url="/", status_code=302)
    try:
        from app.marketing.embed_widget import embed_page_html

        return HTMLResponse(content=embed_page_html(client))
    except Exception as e:
        logger.warning(f"embed render failed for {slug!r}: {e}")
        return RedirectResponse(url="/", status_code=302)


@app.get("/b/{slug}/widget.js", tags=["Frontend"], include_in_schema=False)
async def mini_site_widget_js(slug: str):
    """Floating lead-capture widget injector JS — client pastes one <script> line."""
    from fastapi.responses import Response

    js = "/* widget unavailable */"
    try:
        from app.marketing.embed_widget import widget_js

        js = widget_js(slug)
    except Exception as e:
        logger.warning(f"widget.js failed for {slug!r}: {e}")
    return Response(content=js, media_type="application/javascript")


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


@app.websocket("/ws/exotel-voicebot")
async def exotel_voicebot_ws(websocket: WebSocket):
    """Exotel AgentStream Voicebot applet — bidirectional voice stream.

    Applet URL: wss://leadsgenai.in/ws/exotel-voicebot?sample-rate=16000
    Optional custom params (Exotel max 3): niche / client_name / client_id.
    """
    try:
        from app.voice_agent.exotel_stream import ExotelVoicebotSession

        qp = websocket.query_params
        sr_raw = qp.get("sample-rate") or qp.get("sample_rate") or "8000"
        try:
            sr = int(sr_raw)
        except (TypeError, ValueError):
            sr = 8000
        session = ExotelVoicebotSession(
            websocket,
            sample_rate=sr,
            niche=qp.get("niche") or "general",
            client_name=qp.get("client_name") or "LeadGen AI",
            client_id=qp.get("client_id"),
        )
        await session.handle()
    except Exception as e:
        logger.warning(f"Exotel voicebot stream error: {e}")
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
    return JSONResponse(
        {
            "name": "LeadGen AI",
            "short_name": "LeadGen AI",
            "start_url": "/site/",
            "display": "standalone",
            "background_color": "#4f46e5",
            "theme_color": "#4f46e5",
            "description": "AI Automated Marketing + Voice Agent for Indian businesses",
            "icons": [
                {"src": "/site/icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
                {"src": "/site/icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            ],
        }
    )


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
            ],
        },
        "message": "🚀 B2B Intelligence Platform - Data that drives revenue!",
    }


@app.get("/health")
async def health_check():
    """Detailed health check"""
    global ml_scheduler

    return {
        "status": "healthy",
        "platform": {
            "orchestrator": "team_scheduler",
            "auto_mode": settings.auto_start_platform,
        },
        "ml": {
            "scheduler": "running" if ml_scheduler and ml_scheduler.is_running else "stopped",
            "auto_learning": "enabled",
        },
        "services": {
            "api": "operational",
            "database": "check_required",
            "redis": "check_required",
            "telephony": "check_required",
        },
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

    # reload sirf development me — prod me galti se `python app/main.py` chale to
    # auto-reload (file-watch overhead + double-load) na ho (audit P2).
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=settings.is_development)
