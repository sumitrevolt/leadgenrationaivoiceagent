"""
LeadGen AI - AI Automated Marketing + Voice Agent Platform
FastAPI Main Application - PRODUCTION READY

MULTI-TIER AUTOMATED PLATFORM (marketing-first):
1. Platform finds marketing clients (Indian local businesses)
2. Clients get AI automated marketing (posts/GBP/festivals/posters/reviews/WhatsApp);
   Advanced tier adds an AI voice agent that calls their inquiries
3. Everything runs 24/7 with minimal human intervention
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api import analytics, campaigns, leads, webhooks
from app.api.admin import router as admin_router
from app.api.admin_dashboard import router as admin_dashboard_router
from app.api.agents import router as agents_router
from app.api.ai import router as ai_router
from app.api.billing import router as billing_router
from app.api.customer_dashboard import router as customer_dashboard_router
from app.api.data import router as data_router
from app.api.dev_tasks import router as dev_tasks_router
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


def _sentry_before_send(event, hint):
    """Drop only the secondary `_IncludedRouter.path` AttributeError mask.

    2026-07-14: after a real request exception, code that touched
    ``scope['route'].path`` on a FastAPI lazy include raised
    ``AttributeError: '_IncludedRouter' object has no attribute 'path'``.
    Sentry then flooded with the mask while the original ImportError was
    buried. We drop *only* that exact secondary AttributeError when a
    chained original exists — every other event (including a bare
    IncludedRouter error with no cause) is preserved.
    """
    exc_info = hint.get("exc_info") if hint else None
    if not exc_info or len(exc_info) < 2:
        return event
    exc = exc_info[1]
    if type(exc) is not AttributeError:
        return event
    if str(exc) != "'_IncludedRouter' object has no attribute 'path'":
        return event
    # Secondary only: must wrap / follow another exception.
    if getattr(exc, "__cause__", None) is None and getattr(exc, "__context__", None) is None:
        return event
    return None


def _safe_transaction_name_from_router(scope):
    """Sentry-sdk <2.x `_transaction_name_from_router` compat: resolve lazy routes.

    FastAPI >= 0.115 stores `_IncludedRouter` wrappers in `router.routes`
    (lazy `original_router` references with `.matches` but NO `.path`).
    sentry-sdk 1.x's naive loop then crashes with
    ``AttributeError: '_IncludedRouter' object has no attribute 'path'``
    AFTER the request already failed — masking the real exception (prod
    2026-08-15: QueuePool timeout on /api/growth/social/token-health was
    reported as the secondary `_IncludedRouter` crash instead).

    Guarded drop-in keeps the same contract — first FULL match wins, return
    its `.path` — and for a lazy route, recurses into its wrapped
    `original_router.routes` to resolve the concrete route's path (bounded
    depth; missing internals degrade to None, never raise). Applied as a
    runtime monkeypatch only when the 1.x function is present (2.x fixed
    upstream; then no-op).
    """
    router = scope.get("router") if isinstance(scope, dict) else None
    if not router:
        return None

    def _first_path(routes, _depth: int) -> str | None:
        if _depth > 5 or not routes:
            return None
        for route in routes:
            if not hasattr(route, "matches"):
                continue
            try:
                match = route.matches(scope)
            except Exception:
                continue
            if getattr(match[0], "name", "") != "FULL":
                continue
            path = getattr(route, "path", None)
            if path:
                return path
            # Lazy _IncludedRouter: descend into its wrapped router's routes.
            wrapped = getattr(route, "original_router", None)
            inner = _first_path(getattr(wrapped, "routes", None) or [], _depth + 1)
            if inner:
                return inner
        return None

    return _first_path(getattr(router, "routes", None) or [], 0)


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
                # "url" avoids FastAPIIntegration reading lazy `_IncludedRouter.path`
                # (2026-07-14 Sentry flood: secondary AttributeError masked ImportError).
                FastApiIntegration(transaction_style="url"),
                SqlalchemyIntegration(),
                RedisIntegration(),
                CeleryIntegration(),
            ],
            # Don't send PII
            send_default_pii=False,
            # Attach stack traces for all log messages at ERROR level or higher
            attach_stacktrace=True,
            before_send=_sentry_before_send,
            # Filter out health check endpoints from transactions
            before_send_transaction=lambda event, hint: (
                None
                if event.get("transaction") in ["/health", "/health/ready", "/health/live"]
                else event
            ),
        )
        logger.info("✅ Sentry error tracking initialized")
        # 2026-08-15: sentry-sdk 1.x `_transaction_name_from_router` crashes on
        # FastAPI >= 0.115 lazy `_IncludedRouter` entries (no .path) AFTER a
        # request already failed → masks the real exception (prod 500 evidence).
        # Guarded drop-in (same contract) replaces it at call-time; 2.x no-op.
        try:
            import sentry_sdk.integrations.starlette as _sentry_starlette

            if hasattr(_sentry_starlette, "_transaction_name_from_router"):
                _sentry_starlette._transaction_name_from_router = _safe_transaction_name_from_router
        except Exception as _sentry_patch_err:  # pragma: no cover - defensive
            logger.warning(f"Sentry transaction-name compat patch skipped: {_sentry_patch_err}")
        # 2026-07-19: issue-level API review (Sentry webhooks / resolved-issue triage)
        # ke liye SENTRY_AUTH_TOKEN + SENTRY_ORG + SENTRY_PROJECT chahiye (DSN sirf
        # inbound event capture karta hai). Yeh teen env vars missing ho to operator
        # ko startup pe pata chalega — otherwise yeh gap silent rahta tha aur 72h
        # audit me "Sentry issue-level review unverified" dikhta tha.
        _missing_sentry_api = settings.missing_sentry_api_creds()
        if _missing_sentry_api:
            logger.warning(
                "⚠️  Sentry DSN armed (inbound events captured), par issue-level API review unavailable — "
                f"missing: {', '.join(_missing_sentry_api)}. Set these for Sentry UI issue triage via API."
            )
    except ImportError:
        logger.warning("sentry-sdk not installed, error tracking disabled")
    except Exception as e:
        logger.warning(f"Sentry initialization failed: {e}")

# ML scheduler instance (opt-in heavy; PlatformOrchestrator removed — team_scheduler handles all jobs)
ml_scheduler = None


#: APP_VERSION values that carry NO commit provenance. `latest` is the compose
#: default (`${APP_VERSION:-latest}`), the rest are library/dev defaults.
_UNVERSIONED_APP_VERSIONS = frozenset({"", "latest", "dev", "1.0.0"})


def is_unversioned_production_image(app_version: str | None, app_env: str | None) -> bool:
    """True when a PRODUCTION image carries no commit provenance. Pure/testable.

    See the ADR-097 guard in `lifespan` for why this is fail-LOUD rather than a
    cosmetic nicety: an unversioned image means prod can silently run STALE code.
    """
    if str(app_env or "").strip().lower() != "production":
        return False
    return str(app_version or "").strip().lower() in _UNVERSIONED_APP_VERSIONS


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
    logger.info("   ├── ML Auto-Learning: ENABLED")
    # ENTERPRISE PROBE (2026-07-10): bina API key ke prospecting pipeline
    # silently zero leads return karti — ab startup pe WARNING deta hai so ops
    # knows immediately when GOOGLE_MAPS_API_KEY is unset/placeholder.
    _gmaps_key = (getattr(settings, "google_maps_api_key", "") or "").strip()
    if not _gmaps_key or _gmaps_key.lower().startswith("your-"):
        logger.warning(
            "⚠️  GOOGLE_MAPS_API_KEY not set or placeholder — prospecting pipeline will return zero leads!"
        )
        try:
            from app.platform import ops_alerts

            ops_alerts._ntfy(
                "Prospecting blind — Google Maps API key missing",
                "GOOGLE_MAPS_API_KEY not configured. Lead scraping silently returns zero results.",
                tags=["warning"],
            )
        except Exception:
            pass
    else:
        # Capability status is operationally useful; secret fingerprints are not.
        logger.info("   ├── Google Maps: CONFIGURED (prospecting enabled)")
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

    # Memory-stack warm-up: resolve the tokenizer/redaction helpers HERE, at
    # process startup, not inside the first request. Measured: paying that
    # import cost inside `assemble()` blew the 250ms deadline and timed out
    # every lane, so the first agent turn silently got an empty memory block.
    # Never blocks boot — a failure only degrades to the builtin estimator and
    # is visible in /api/memory-stack/diagnostics.
    try:
        from app.platform import memory_stack as _memory_stack

        await _memory_stack.prewarm()
        logger.info("✅ Memory stack warmed (helpers resolved off the request path)")
    except Exception as e:
        logger.warning(f"Memory-stack prewarm skipped (degraded, legacy fallback): {e}")

    # ML scheduler remains opt-in (heavy). All automation handled by team_scheduler.
    logger.info("⏭️ ML scheduler disabled (opt-in)")

    # Plugin catalog bootstrap — register all governed plugin manifests at startup.
    # Additive observation layer; no runtime behaviour change.
    try:
        from app.agents.harness.plugin_catalog import bootstrap_catalog
        from app.agents.harness.plugin_manifest import get_registry

        bootstrap_catalog()
        _plugin_count = get_registry().count()
        logger.info(f"✅ Plugin catalog: {_plugin_count} manifests registered")
    except Exception as e:
        logger.warning(f"Plugin catalog bootstrap skipped: {e}")

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

                # Also warm Qdrant connection + do a throwaway search so first real call
                # doesn't pay the connection-setup + index-load cost (~6-8s on cold VPS).
                try:
                    from app.voice_agent.knowledge_base import search_knowledge_base

                    await _aio.get_running_loop().run_in_executor(
                        None,
                        lambda: search_knowledge_base("hello", niche="general", top_k=1),
                    )
                    logger.info("✅ KB Qdrant connection warmed (14s cold-start eliminated)")
                except Exception as _e:
                    logger.debug(f"KB Qdrant warm-up skip: {_e}")

            _aio.create_task(_prewarm_kb())
        except Exception as e:
            logger.warning(f"KB prewarm not scheduled: {e}")

    # Obsidian ADR + skills auto-mirror at startup (background, INERT if OBSIDIAN_SYNC unset).
    try:
        import asyncio as _aio2

        async def _obsidian_startup_mirror() -> None:
            try:
                import asyncio as _aio3
                import pathlib as _pl

                from app.platform import obsidian_sync as _obs

                _ROOT = _pl.Path(__file__).resolve().parent.parent
                # Mirror ADR decision docs → Decisions/
                for _f in sorted((_ROOT / "docs").glob("ADR*.md")):
                    await _aio3.get_running_loop().run_in_executor(
                        None,
                        lambda f=_f: _obs.write_note(
                            "Decisions",
                            f.stem.lower().replace("_", "-"),
                            f.read_text(encoding="utf-8", errors="ignore"),
                            tags=["adr", "decision"],
                        ),
                    )
                logger.info("✅ Obsidian ADR mirror done")
            except Exception as _e:
                logger.debug(f"Obsidian startup mirror skip: {_e}")

        _aio2.create_task(_obsidian_startup_mirror())
    except Exception as _obs_e:
        logger.debug("Obsidian mirror task creation skipped: %s", _obs_e)

    logger.info("✅ Startup complete - application ready")

    # Outbound call queue processor (Vobiz) — polls Redis queue and dials.
    # Gated CALL_PROCESSOR=1 (default ON when telephony provider configured).
    _call_processor_task = None
    if os.environ.get("CALL_PROCESSOR", "1").strip().lower() in ("1", "true", "yes"):
        try:
            provider = (
                (os.environ.get("TELEPHONY_PROVIDER") or settings.default_telephony or "vobiz")
                .strip()
                .lower()
            )
            if provider == "vobiz":
                from app.telephony.call_manager import CallManager

                _cm = CallManager(provider=provider)
                app.state.call_manager = _cm
                _call_processor_task = asyncio.create_task(_cm.start_call_processor())
                app.state.call_processor_task = _call_processor_task  # SP3: loop_supervisor handle
                logger.info(f"✅ Call queue processor started ({provider})")
        except Exception as e:
            logger.warning(f"Call processor not started: {e}")

    # SP3 loop-supervisor watchdog — re-spawns a dead call-processor + boot-grace
    # skip visibility (gated LOOP_SUPERVISOR; default OFF = not started, no-op).
    _supervisor_task = None
    try:
        from app.platform import loop_supervisor as _ls

        if _ls.enabled():
            _supervisor_task = asyncio.create_task(_ls.supervisor_loop(app, interval_s=120))
            logger.info("✅ loop_supervisor watchdog started")
    except Exception as _e:
        logger.warning(f"loop_supervisor not started: {_e}")

    # Post-startup critical-route sweep (API-001). A silently-guarded router import
    # failure only logs logger.warning; this surfaces a missing revenue-critical
    # route with an ERROR + ntfy so a bad deploy can't drop billing/login unnoticed.
    # ENTERPRISE FIX (2026-07-10): pehle sirf 3 hardcoded routes check hote the.
    # Ab ALL registered routers se unke routes extract karte hain — koi bhi router
    # jo import hua aur usme 0 routes hain = probable import-failure ya empty router.
    # Critical path routes (billing, auth, signup, customer, UPI) ki dedicated check
    # with ntfy alert. Non-critical missing routes logged at WARNING only.
    try:
        from app.utils.route_inspection import iter_effective_routes

        _registered = {
            getattr(r, "path", "")
            for r in iter_effective_routes(app.routes)
            if getattr(r, "path", "")
        }
        # Revenue + customer-critical paths (must never go silently missing)
        _critical = [
            "/api/billing/plans",
            "/api/customer/auth/login",
            "/api/public/signup",
            "/api/public/pay-info",
            "/api/upi/submit",
            "/api/customer/auth/me",
        ]
        _missing = [
            p for p in _critical if not any(rp == p or rp.startswith(p) for rp in _registered)
        ]
        if _missing:
            logger.error(f"❌ CRITICAL routes missing after startup: {_missing}")
            try:
                from app.platform import ops_alerts

                ops_alerts._ntfy(
                    "Critical routes missing",
                    f"Router import silently failed — missing: {', '.join(_missing)}",
                    priority="high",
                    tags=["rotating_light"],
                )
            except Exception:
                pass
        else:
            logger.info("✅ Critical route sweep OK (%d total routes)", len(_registered))

        # Total route count audit: if 0 routes registered, something is deeply wrong
        if len(_registered) == 0:
            logger.error("❌ ZERO routes registered — all router imports failed!")
        elif len(_registered) < 50:
            logger.warning(
                "⚠️ Only %d routes registered — expected 400+ — router import failures likely",
                len(_registered),
            )
    except Exception as _sweep_e:
        logger.warning(f"Critical route sweep skipped: {_sweep_e}")

    # ---------------------------------------------------------------------
    # Image-provenance guard (2026-07-14, ADR-097). Mirrors the critical-route
    # sweep above: a silent failure that only a LOUD startup check will surface.
    #
    # WHY: `docker-compose.vps.yml` tags `${APP_VERSION:-latest}`. A deploy that
    # forgets APP_VERSION silently keeps/ships an UNVERSIONED `:latest` image, so
    # /health reports version "latest" and nobody can tell what code is running.
    # That is not cosmetic: prod sat on a stale `:latest` while fixes were merged
    # to main and never reached production — `/api/voice/niches` (a paid Voice
    # Agent revenue route) returned 500 for SIX DAYS (~872 Sentry events) even
    # though the fix was in main, plus ~277 middleware loop errors and a qdrant
    # fastembed failure that all vanished the moment the image was rebuilt with a
    # real SHA. Silent drift is the single most expensive failure mode we have.
    try:
        _ver = (os.environ.get("APP_VERSION") or "").strip()
        # settings.app_env is the real field (there is NO settings.environment —
        # getattr on a wrong name would silently no-op this whole guard).
        _app_env = str(getattr(settings, "app_env", "") or "")
        _is_prod = _app_env.lower() == "production"
        if is_unversioned_production_image(_ver, _app_env):
            logger.error(
                "❌ UNVERSIONED production image (APP_VERSION=%r) — /health cannot "
                "prove which commit is running and prod may be silently STALE. "
                "Deploy with: APP_VERSION=$(git rev-parse --short HEAD) docker compose "
                "-f docker-compose.vps.yml build app",
                _ver or "<unset>",
            )
            try:
                from app.platform import ops_alerts

                ops_alerts._ntfy(
                    "Unversioned production image",
                    f"APP_VERSION={_ver or '<unset>'} — prod may be running STALE code. "
                    "Rebuild with APP_VERSION=<git sha>.",
                    priority="high",
                    tags=["rotating_light"],
                )
            except Exception:
                pass
        elif _is_prod:
            logger.info("✅ Image provenance OK (APP_VERSION=%s)", _ver)
    except Exception as _ver_e:
        logger.warning(f"Image provenance guard skipped: {_ver_e}")

    yield

    # Shutdown — owned inquiry BG work must finish (or cancel) BEFORE DB dispose.
    # Otherwise a checked-out aiosqlite session outlives the engine (SQLAlchemy #13039).
    logger.info("Shutting down application...")
    if _call_processor_task is not None:
        _call_processor_task.cancel()
        try:
            await _call_processor_task
        except asyncio.CancelledError:
            pass
    if _supervisor_task is not None:
        _supervisor_task.cancel()
        try:
            await _supervisor_task
        except asyncio.CancelledError:
            pass
    if ml_scheduler:
        await stop_training_scheduler()
    try:
        from app.platform.inquiry_hooks import drain_inquiry_bg_tasks

        await drain_inquiry_bg_tasks()
    except Exception as _drain_e:
        logger.warning(f"inquiry bg drain skipped: {_drain_e}")
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
# - Development: wildcard origins, NO credentials (safe for dev tools)
# - Production: specific origins only, credentials allowed (strict security)
if settings.app_env == "development":
    # Development: permissive for local testing (wildcard, no credentials)
    cors_config = {
        "allow_origins": ["*"],
        "allow_credentials": False,  # Browsers ignore credentials with wildcard origins
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
        "expose_headers": ["X-Request-ID", "X-Response-Time"],
    }
else:
    # Production: strict, specific origins from config
    cors_config = {
        "allow_origins": settings.cors_origins,
        "allow_credentials": True,  # Safe because origins are specific
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["*"],
        "expose_headers": ["X-Request-ID", "X-Response-Time"],
    }

app.add_middleware(CORSMiddleware, **cors_config)


# PostHog web-analytics snippet auto-inject (G3) — OFF by default. POSTHOG_API_KEY
# unset = har response untouched (turant passthrough). Never blocks boot.
try:
    from app.middleware.analytics_inject import PostHogInjectMiddleware

    app.add_middleware(PostHogInjectMiddleware)
except Exception as _ph_e:  # pragma: no cover
    logger.warning(f"PostHog inject middleware skipped: {_ph_e}")

# HTTP request/latency metrics for Prometheus (OBS-001). Pure-ASGI, fail-open,
# WebSocket-safe. ON by default in production (SLO alerts need these series);
# OFF in dev unless PROMETHEUS_HTTP_METRICS=1; explicit =0|false|off disables
# anywhere (see http_metrics.enabled()).
try:
    from app.middleware.http_metrics import HttpMetricsMiddleware
    from app.middleware.http_metrics import enabled as _http_metrics_enabled

    if _http_metrics_enabled():
        app.add_middleware(HttpMetricsMiddleware)
        logger.info("✅ HTTP metrics middleware enabled (PROMETHEUS_HTTP_METRICS)")
except Exception as _hm_e:  # pragma: no cover
    logger.warning(f"HTTP metrics middleware skipped: {_hm_e}")


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
# Telephony provider callbacks (Vobiz voice + status). Sentry's FastApiIntegration
# auto-captures their errors.
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
    from app.api.office_hq import router as office_hq_router

    app.include_router(office_hq_router, prefix="/api")  # /api/platform/office/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Office HQ router not mounted: {_e}")
try:
    from app.api.goals import router as goals_router

    app.include_router(goals_router, prefix="/api", tags=["Goals"])  # /api/goals/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Goals router not mounted: {_e}")
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
    from app.api.page_agent import router as page_agent_router

    app.include_router(
        page_agent_router, prefix="/api"
    )  # /api/page-agent/* (admin copilot LLM proxy + boot.js; PAGE_AGENT gated)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Page-agent router not mounted: {_e}")
try:
    from app.api.booking import router as booking_router

    app.include_router(booking_router, prefix="/api")  # /api/booking/* (Calendly-lite slots+book)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Booking router not mounted: {_e}")
try:
    from app.api.customer_auth import router as customer_auth_router

    app.include_router(
        customer_auth_router, prefix="/api"
    )  # /api/customer/auth/* (client login portal)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer auth router not mounted: {_e}")
try:
    from app.api.impersonation import router as impersonation_router

    app.include_router(
        impersonation_router, prefix="/api"
    )  # /api/impersonate/* (super-admin login-as-customer, GATED)
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
    from app.api.upi_payments import router as upi_payments_router

    app.include_router(
        upi_payments_router, prefix="/api", tags=["UPI Payments"]
    )  # /api/upi/* (self-serve "maine pay kiya" submit + admin queue)
except Exception as _e:  # pragma: no cover
    logger.warning(f"UPI payments router not mounted: {_e}")
try:
    from app.api.reseller import router as reseller_router

    app.include_router(
        reseller_router, prefix="/api", tags=["Reseller"]
    )  # /api/reseller/* (agency/reseller program)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Reseller router not mounted: {_e}")
try:
    from app.api.minisite_builder import router as minisite_builder_router

    app.include_router(
        minisite_builder_router, prefix="/api"
    )  # /api/minisite/* (mini-site builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Mini-site builder router not mounted: {_e}")
try:
    from app.api.journeys import router as journeys_router

    app.include_router(journeys_router, prefix="/api")  # /api/journeys/* (omnichannel rule engine)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Journeys router not mounted: {_e}")
try:
    from app.api.growth import router as growth_router

    app.include_router(
        growth_router, prefix="/api"
    )  # /api/growth/* (lead-score, review, flows, missed-call)
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
    from app.api.blueprint import router as _blueprint_router

    # /api/blueprint/* — canonical versioned architecture graph for the
    # /app/explorer Master Blueprint mode (read-only, no secrets, never-raises).
    app.include_router(_blueprint_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Blueprint router not mounted: {_e}")
try:
    from app.api.eval_gate import router as _eval_gate_router

    # /api/eval-gate/* — DeepEval close-the-loop reward signal (F.3).
    # Admin-only summary + recent-scores view for self_improve safety rail.
    app.include_router(_eval_gate_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Eval-gate router not mounted: {_e}")
try:
    from app.api.rl import router as _rl_router

    # /api/rl/* — RL flywheel (Phase 0) read-only reward-spine visibility.
    # Admin-only: graduation status + per-arm reward + dev-session feedback.
    app.include_router(_rl_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"RL router not mounted: {_e}")
try:
    from app.api.control_center import router as control_center_router

    # /api/control-center/overview — enterprise Control Center cockpit L1 (Executive).
    # Admin-only thin read-side aggregator (one call powers the whole L1 view).
    app.include_router(control_center_router, prefix="/api", tags=["Control Center"])
except Exception as _e:  # pragma: no cover
    logger.warning(f"Control Center router not mounted: {_e}")
try:
    from app.api.agent_memory_admin import router as _agent_memory_admin_router

    # /api/agent-memory/* — operator inspect + DPDP-compliant purge (F.4).
    # Admin-only; INERT when AGENT_MEMORY flag unset (backend itself returns []).
    app.include_router(_agent_memory_admin_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Agent-memory admin router not mounted: {_e}")
try:
    from app.api.workforce_memory_admin import router as _workforce_memory_admin_router

    # /api/workforce-memory/* — ADR-154 per-STAFF layered hub (TencentDB patterns).
    # Admin-only; INERT when WORKFORCE_MEMORY unset.
    app.include_router(_workforce_memory_admin_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Workforce-memory admin router not mounted: {_e}")
try:
    from app.api.memory_stack_admin import router as _memory_stack_admin_router

    # /api/memory-stack/* — 7-layer agent-memory facade (working/episodic/semantic/
    # procedural/hierarchical/prospective/shared). Admin-only; INERT when
    # MEMORY_STACK unset (assemble returns enabled:false, drain skips).
    app.include_router(_memory_stack_admin_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Memory-stack admin router not mounted: {_e}")
try:
    from app.api.engineer_agents import router as _engineer_agents_router

    # /api/engineer-agents/* — F.5 SRE (Pranav) + FinOps (Vidya) + Security
    # (Arnav). Admin-only score/KPI rollup; INERT when role flag unset.
    app.include_router(_engineer_agents_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Engineer-agents router not mounted: {_e}")
try:
    # Agent-extension batch (2026-06-24) — 14 new agent capabilities borrowed from
    # Kilo Code / OpenCode / Ruflo / Hermes-agent. All admin-gated; INERT (flags OFF
    # default). Shared prefix /api/agents-ext. code_exec + browser are super-admin +
    # flag + dep gated (inert by default).
    from app.api.agent_capacity import router as _agent_capacity_router
    from app.api.agent_governance import router as _agent_governance_router
    from app.api.agent_scale import router as _agent_scale_router
    from app.api.eng_agents import router as _eng_agents_router
    from app.api.orchestration_ext import router as _orchestration_ext_router

    for _r in (
        _eng_agents_router,
        _orchestration_ext_router,
        _agent_governance_router,
        _agent_scale_router,
        _agent_capacity_router,
    ):
        app.include_router(_r, prefix="/api/agents-ext")
except Exception as _e:  # pragma: no cover
    logger.warning(f"Agents-ext routers not mounted: {_e}")
try:
    from app.api.customer_onboard import router as _customer_onboard_router

    # S.1 POST /api/admin/customers/onboard — single-call admin onboarding
    # (profile + login + audit log) with a copy-pasteable customer dashboard
    # URL + one-time password.
    app.include_router(_customer_onboard_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer-onboard router not mounted: {_e}")
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
    from app.api.sales_autopilot_admin import router as _sales_autopilot_router

    # /api/sales-autopilot/* — Autonomous Sales Engine observability + dry-run canary.
    # Admin-only; INERT when SALES_AUTOPILOT_ENABLED unset (policy engine returns dry-run).
    app.include_router(_sales_autopilot_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Sales-autopilot admin router not mounted: {_e}")
try:
    from app.api.owner_email_canary import router as _owner_email_canary_router

    # /api/admin/owner-email-canary/* — one-shot owner-inbox live canary (super_admin).
    # Does NOT enable AUTO_EMAIL_OUTREACH. Recipient never logged in cleartext.
    app.include_router(_owner_email_canary_router)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Owner-email-canary router not mounted: {_e}")
try:
    from app.api import conversion as _conversion

    app.include_router(
        _conversion.public_router, prefix="/api"
    )  # /api/public/widget-chat, /lead-in, /trial-status
    app.include_router(
        _conversion.admin_router, prefix="/api"
    )  # /api/conversion/* (widget form builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Conversion router not mounted: {_e}")
try:
    from app.api.creative import router as creative_router

    app.include_router(
        creative_router, prefix="/api"
    )  # /api/creative/* (jingle, bg-remove, multilang status)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Creative router not mounted: {_e}")
try:
    from app.api.clientcrm import router as clientcrm_router

    app.include_router(
        clientcrm_router, prefix="/api"
    )  # /api/clientcrm/* (end-customer CRM, catalog, payment links)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ClientCRM router not mounted: {_e}")
try:
    from app.api.seoops import router as seoops_router

    app.include_router(
        seoops_router, prefix="/api"
    )  # /api/seoops/* (rank tracker, conversations, dialer)
except Exception as _e:  # pragma: no cover
    logger.warning(f"SeoOps router not mounted: {_e}")
try:
    from app.api.engage import redirect_router as _redirect_router
    from app.api.engage import router as engage_router

    app.include_router(
        engage_router, prefix="/api"
    )  # /api/engage/* (upi-qr, short-links, reviews-widget, alerts)
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

    app.include_router(
        memory_router, prefix="/api"
    )  # /api/memory/* (compounding memory, call-prep, live notes)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Memory router not mounted: {_e}")
try:
    from app.api.events import router as events_router

    app.include_router(events_router, prefix="/api")  # /api/events/stream (SSE real-time feed)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Events router not mounted: {_e}")
try:
    from app.api.brandassets import router as brandassets_router

    app.include_router(
        brandassets_router, prefix="/api"
    )  # /api/brand/* (frames, card, resize, review-post, stickers)
except Exception as _e:  # pragma: no cover
    logger.warning(f"BrandAssets router not mounted: {_e}")
try:
    from app.api.clientops import router as clientops_router

    app.include_router(
        clientops_router, prefix="/api"
    )  # /api/clientops/* (speed-to-lead, approvals, snapshots, routing, proposals)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ClientOps router not mounted: {_e}")
try:
    from app.api.voiceai import router as voiceai_router

    app.include_router(
        voiceai_router, prefix="/api"
    )  # /api/voiceai/* (transfer, ask-AI, leaderboard)
except Exception as _e:  # pragma: no cover
    logger.warning(f"VoiceAI router not mounted: {_e}")
try:
    from app.api.voice_product import router as voice_product_router

    app.include_router(
        voice_product_router, prefix="/api"
    )  # /api/voice/* (Product 2: packages, quota, lead packs — ADR-009)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Voice Product router not mounted: {_e}")
try:
    # Product-3 combo surface — GATED default-OFF (audit 2026-07-04): the public
    # /api/combo payload leaked the hidden legacy `growth` plan (name + ₹2,999)
    # and a "marketing+voice bundle" USP that contradicts the ADR-009 two-product
    # truth. No public page consumes it (admin onboard wizards hardcode tiers).
    # Re-enable with COMBO_PRODUCT=1 once an ADR settles the combo product's
    # framing. Billing plan-sync + UPI activation of existing combo plan keys are
    # module-level and stay untouched.
    if (os.environ.get("COMBO_PRODUCT", "0") or "0").strip().lower() in ("1", "true", "yes", "on"):
        from app.api.combo_product import router as combo_product_router

        app.include_router(
            combo_product_router, prefix="/api"
        )  # /api/combo/* (Product 3: AI Growth Suite combo)
    else:
        logger.info("Combo Product router NOT mounted (COMBO_PRODUCT unset — ADR-009 gate)")
except Exception as _e:  # pragma: no cover
    logger.warning(f"Combo Product router not mounted: {_e}")
try:
    from app.api.niche_db import router as niche_db_router

    app.include_router(
        niche_db_router, prefix="/api"
    )  # /api/niche/* (niche prospect database + call queue)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Niche DB router not mounted: {_e}")
try:
    from app.api.localseo import router as localseo_router

    app.include_router(
        localseo_router, prefix="/api"
    )  # /api/localseo/* (geo-visibility, grid-rank, listings)
except Exception as _e:  # pragma: no cover
    logger.warning(f"LocalSEO router not mounted: {_e}")
try:
    from app.api.contentplus import router as contentplus_router

    app.include_router(
        contentplus_router, prefix="/api"
    )  # /api/contentplus/* (clips, gif, avatar, service-reminders, A/B)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ContentPlus router not mounted: {_e}")
try:
    from app.api.widgets import router as widgets_router

    app.include_router(
        widgets_router, prefix="/api"
    )  # /api/widgets/* (popup pack, bio-link, beacon analytics)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Widgets router not mounted: {_e}")
try:
    from app.api.lifecycle import router as lifecycle_router

    app.include_router(
        lifecycle_router, prefix="/api"
    )  # /api/lifecycle/* (newsletter, winback, signature, lead-magnet)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Lifecycle router not mounted: {_e}")
try:
    from app.api.contentauto import router as contentauto_router

    app.include_router(
        contentauto_router, prefix="/api"
    )  # /api/contentauto/* (repurpose, pulse, month-plan, team-report, push)
except Exception as _e:  # pragma: no cover
    logger.warning(f"ContentAuto router not mounted: {_e}")
app.include_router(ml_router, prefix="/api", tags=["ML Training"])
app.include_router(admin_router, prefix="/api", tags=["Admin"])
try:
    from app.api.assessment import router as assessment_router

    app.include_router(
        assessment_router, prefix="/api"
    )  # /api/assessment/* (dashboard gap analysis)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Assessment router not mounted: {_e}")
try:
    from app.api.team_access import router as team_access_router

    app.include_router(
        team_access_router, prefix="/api"
    )  # /api/team-access/* (sub-admins + module grants)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Team-access router not mounted: {_e}")
app.include_router(ai_router, prefix="/api", tags=["AI"])
app.include_router(customer_dashboard_router, tags=["Customer Dashboard"])  # /api/customer/*
try:
    from app.api.customer_plugins import router as customer_plugins_router

    app.include_router(
        customer_plugins_router
    )  # /api/customer/plugins — AI capabilities for customer
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer plugins router not mounted: {_e}")
# Loop-social-13 (2026-07-11): OAuth callback stubs — /api/social/oauth/*
# Never crashes app boot; provider approval flip is env-only, no redeploy.
try:
    from app.api.social_oauth import router as social_oauth_router

    app.include_router(social_oauth_router)  # /api/social/oauth/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Social OAuth stub router not mounted: {_e}")
try:
    from app.api.customer_marketing_studio import router as customer_studio_router

    app.include_router(customer_studio_router)  # /api/customer/studio/* (AI marketing self-serve)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer marketing studio router not mounted: {_e}")
try:
    from app.api.customer_pipeline import router as customer_pipeline_router

    app.include_router(customer_pipeline_router)  # /api/customer/pipeline (lead Kanban board)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer pipeline router not mounted: {_e}")
try:
    from app.api.email_track import router as email_track_router

    app.include_router(
        email_track_router
    )  # /t/o, /t/c (public pixels) + /api/admin/email-tracking/* — NO prefix
except Exception as _e:  # pragma: no cover
    logger.warning(f"Email tracking router not mounted: {_e}")
try:
    from app.api import segments as segments_api

    app.include_router(
        segments_api.router, tags=["Segments"]
    )  # /api/segments/* (dynamic segment builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Segments router not mounted: {_e}")
try:
    from app.api.studio_media import router as studio_media_router

    app.include_router(
        studio_media_router
    )  # /api/customer/studio/* media (upload/serve image tools)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Studio media router not mounted: {_e}")
try:
    from app.api.customer_flows import router as customer_flows_router

    app.include_router(customer_flows_router)  # /api/customer/flow* (Phase 7 per-client builder)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Customer flows router not mounted: {_e}")
app.include_router(admin_dashboard_router, tags=["Admin Dashboard"])  # /api/admin/*
try:
    from app.api.system_health import router as system_health_router

    app.include_router(system_health_router)  # /api/admin/system-health-detail (B3, flag-gated)
except Exception as _e:  # pragma: no cover - never block boot
    import logging as _lg

    _lg.getLogger(__name__).warning("system_health router not mounted: %s", _e)
try:
    from app.api.call_recordings import router as call_recordings_router

    app.include_router(call_recordings_router)  # /api/admin/call-recordings/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Call recordings router not mounted: {_e}")
try:
    from app.api.web_call_admin import router as web_call_admin_router

    app.include_router(web_call_admin_router)  # /api/admin/web-calls/* (web test-call transcripts)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Web-call admin router not mounted: {_e}")
try:
    from app.api.admin_ops import router as admin_ops_router

    app.include_router(admin_ops_router)  # /api/admin/campaign/* + /api/admin/system/*
except Exception as _e:  # pragma: no cover
    logger.warning(f"Admin ops router not mounted: {_e}")
try:
    from app.api.owner_os import router as owner_os_router

    app.include_router(owner_os_router)  # /api/admin/owner-os/* — Owner Command Console
except Exception as _e:  # pragma: no cover
    logger.warning(f"Owner OS router not mounted: {_e}")
try:
    from app.api.plugin_registry import router as plugin_registry_router

    app.include_router(
        plugin_registry_router
    )  # /api/admin/plugins/* — Plugin manifest table + drift detection
except Exception as _e:  # pragma: no cover
    logger.warning(f"Plugin registry router not mounted: {_e}")
try:
    from app.api.onboard_pipeline_api import router as onboard_pipeline_router

    app.include_router(
        onboard_pipeline_router
    )  # /api/admin/onboard-pipeline/* — Onboarding factory pipeline status + metrics
except Exception as _e:  # pragma: no cover
    logger.warning(f"Onboard pipeline router not mounted: {_e}")
try:
    from app.api.onboard_wizard import router as onboard_wizard_router

    app.include_router(
        onboard_wizard_router
    )  # /api/onboard-wizard/* — business-type templates + auto-setup
except Exception as _e:  # pragma: no cover
    logger.warning(f"Onboard wizard router not mounted: {_e}")
try:
    from app.api.marketing_features import router as marketing_features_router

    app.include_router(
        marketing_features_router
    )  # /api/marketing-features/* -- Review automation, email drips, appointment reminders, customer health
except Exception as _e:  # pragma: no cover
    logger.warning("Marketing features router not mounted: " + str(_e))
try:
    from app.api.coordination_hub import router as coordination_hub_router

    app.include_router(
        coordination_hub_router
    )  # /api/admin/owner-os/coordination-hub/* — thin Owner OS projection
except Exception as _e:  # pragma: no cover
    logger.warning(f"Coordination Hub router not mounted: {_e}")
try:
    from app.api.owner_copilot import router as owner_copilot_router

    app.include_router(
        owner_copilot_router
    )  # /api/owner-copilot/* — OpenClaw Owner Copilot (flag-gated)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Owner Copilot router not mounted: {_e}")
try:
    from app.api.integration_health_api import router as integration_health_router

    app.include_router(
        integration_health_router
    )  # /api/admin/integrations/health + /api/customer/integrations/health
except Exception as _e:  # pragma: no cover
    logger.warning(f"Integration health router not mounted: {_e}")
try:
    from app.api.brain import router as brain_router

    app.include_router(brain_router)  # /api/admin/brain/* — operator second-brain search/browse
except Exception as _e:  # pragma: no cover
    logger.warning(f"Brain router not mounted: {_e}")
try:
    from app.api.okf_admin import router as okf_admin_router

    app.include_router(okf_admin_router)  # /api/admin/okf/* — ADR-119 OKF status/dry-run/ingest
except Exception as _e:  # pragma: no cover
    logger.warning(f"OKF admin router not mounted: {_e}")
try:
    from app.api.okf_public import router as okf_public_router

    app.include_router(okf_public_router)  # /okf/ — public agent-readable OKF Markdown bundle
except Exception as _e:  # pragma: no cover
    logger.warning(f"OKF public router not mounted: {_e}")
try:
    from app.api.admin_db_explorer import router as admin_db_router

    app.include_router(
        admin_db_router
    )  # /api/admin/db/* (read-only DB explorer, ADMIN_DB_EXPLORER gated)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Admin DB explorer router not mounted: {_e}")
try:
    from app.api.llm_compare import router as llm_compare_router

    app.include_router(
        llm_compare_router
    )  # /api/llm/compare/* (blind arena, LLM_COMPARE_ENABLED gated, INERT default)
except Exception as _e:  # pragma: no cover
    logger.warning(f"LLM Compare router not mounted: {_e}")
try:
    from app.api.model_cookbook import router as model_cookbook_router

    app.include_router(
        model_cookbook_router
    )  # /api/cookbook/* (niche→LLM recipes, MODEL_COOKBOOK_ENABLED gated, INERT default)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Model Cookbook router not mounted: {_e}")
try:
    from app.api.deep_research import router as deep_research_router

    app.include_router(
        deep_research_router
    )  # /api/research/deep/* (multi-step cited research, DEEP_RESEARCH_ENABLED gated, INERT default)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Deep Research router not mounted: {_e}")
try:
    from app.api.docs_ai_edit import router as docs_ai_edit_router

    app.include_router(
        docs_ai_edit_router
    )  # /api/docs/edit/* (AI writing surface, DOCS_AI_EDIT_ENABLED gated, INERT default)
except Exception as _e:  # pragma: no cover
    logger.warning(f"Docs AI-Edit router not mounted: {_e}")
app.include_router(web_call_router, prefix="/api", tags=["Web Call (Test Mode)"])  # /api/web-call/*
app.include_router(
    agents_router, prefix="/api", tags=["Agents"]
)  # /api/agents/* (LangGraph supervisor)
app.include_router(dev_tasks_router, prefix="/api")  # /api/dev-tasks/* (draft-safe control plane)
app.include_router(
    telephony_vobiz_router, prefix="/api", tags=["Telephony"]
)  # /api/telephony/vobiz/*

_dsh_runtime_configured = os.environ.get("DSH_RUNTIME_ENABLED", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
) or os.environ.get("DSH_SHADOW_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")

try:
    from app.api.dsh_internal import router as dsh_internal_router

    app.include_router(dsh_internal_router)
except Exception as _e:  # pragma: no cover
    if _dsh_runtime_configured:
        raise
    logger.warning("DSH internal router not mounted: %s", type(_e).__name__)


@app.middleware("http")
async def _dsh_internal_auth_gate(request, call_next):
    """All DSH HTTP/MCP traffic requires a live run-scoped bearer."""
    path = request.url.path or ""
    if not path.startswith("/internal/dsh"):
        return await call_next(request)
    try:
        from app.api.dsh_internal import authenticate_request

        authenticate_request(request)
    except Exception as exc:
        from fastapi import HTTPException
        from fastapi.responses import JSONResponse

        if isinstance(exc, HTTPException):
            return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
        logger.warning("DSH internal auth gate failed: %s", type(exc).__name__)
        return JSONResponse(status_code=503, content={"detail": "dsh_auth_unavailable"})
    return await call_next(request)


# ---------------------------------------------------------------------------
# MCP server — platform admin endpoints as MCP tools (Claude platform-admin)
# Optional dependency: app works fine without fastapi-mcp installed.
#
# Council 2026-06-26 SECURITY FIX: the prior mount was UNGATED — Platform/Data/
# Agents tagged routes were exposed publicly at /mcp/* (admin tools leak risk).
# Now requires EITHER:
#   - FASTAPI_MCP_TOKEN env set + clients send `Authorization: Bearer <token>`
#   - MCP_IP_ALLOWLIST env set (CSV) + request client IP must match
# When NEITHER is set in production (PROD env), the mount is REFUSED and a
# loud warning is logged. Non-production APP_ENV still mounts to allow local work.
# Arya (mcp_engineer.py) probes this gate and alerts if it ever regresses.
# ---------------------------------------------------------------------------
try:
    from fastapi_mcp import FastApiMCP

    _mcp_token = os.environ.get("FASTAPI_MCP_TOKEN", "").strip()
    _mcp_allowlist = [
        ip.strip() for ip in os.environ.get("MCP_IP_ALLOWLIST", "").split(",") if ip.strip()
    ]
    _mcp_gated = bool(_mcp_token) or bool(_mcp_allowlist)
    _mcp_is_prod = settings.app_env == "production"

    if not _mcp_gated and _mcp_is_prod:
        logger.warning(
            "🔒 MCP mount REFUSED — production requires FASTAPI_MCP_TOKEN "
            "or MCP_IP_ALLOWLIST. Set one in .env and recreate the app container. "
            "(Arya MCP-Engineer will keep alerting until this is fixed.)"
        )
    else:
        _mcp = FastApiMCP(
            app,
            name="LeadGen AI Platform",
            include_tags=["Platform", "Data Intelligence", "Agents"],
        )
        _mcp.mount()

        # Auth gate middleware — runs only for /mcp/* paths, fail-CLOSED in prod.
        @app.middleware("http")
        async def _mcp_auth_gate(request, call_next):
            path = request.url.path or ""
            if not path.startswith("/mcp"):
                return await call_next(request)
            # Allow if dev + no gate configured
            if not _mcp_gated and not _mcp_is_prod:
                return await call_next(request)
            # Bearer token check
            auth = request.headers.get("authorization", "").strip()
            if _mcp_token and auth == f"Bearer {_mcp_token}":
                return await call_next(request)
            # IP allowlist check. SECURITY: use the RIGHTMOST X-Forwarded-For entry —
            # that is the value the trusted proxy (Caddy) appended = the real peer.
            # The leftmost entry is fully client-controlled (an attacker can prepend an
            # allowlisted IP), so it must NEVER drive an auth decision.
            client_ip = (request.client.host if request.client else "") or ""
            _xff_parts = [
                p.strip()
                for p in request.headers.get("x-forwarded-for", "").split(",")
                if p.strip()
            ]
            real_ip = (_xff_parts[-1] if _xff_parts else "") or client_ip
            if _mcp_allowlist and real_ip in _mcp_allowlist:
                return await call_next(request)
            # Reject — log to Arya's auth-failure tail-file
            try:
                from app.platform import mcp_engineer as _arya

                _arya.log_auth_failure("unauthorized", ip=real_ip, path=path[:120])
            except (ImportError, AttributeError) as _arya_e:
                logger.debug("MCP auth failure log skipped: %s", _arya_e)
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=401,
                content={"detail": "MCP /mcp endpoint requires authentication"},
            )

        from app.platform.mcp_import import mcp_gate_kind

        _gate_kind = mcp_gate_kind(
            token_configured=bool(_mcp_token),
            allowlist_configured=bool(_mcp_allowlist),
        )
        logger.info(
            f"✅ MCP server mounted at /mcp (gated: {_gate_kind}, Platform/Data/Agents tools)"
        )

    if _dsh_runtime_configured:
        from app.api.dsh_internal import MCP_OPERATION_IDS

        _dsh_mcp = FastApiMCP(
            app,
            name="LeadGen DSH Internal",
            include_operations=list(MCP_OPERATION_IDS),
            headers=["authorization"],
        )
        _dsh_mcp.mount_http(mount_path="/internal/dsh/mcp")
        logger.info(
            "DSH internal MCP mounted with %d exact operations",
            len(MCP_OPERATION_IDS),
        )
except ImportError as e:
    from app.platform.mcp_import import describe_mcp_import_failure

    _mcp_log_level, _mcp_log_message = describe_mcp_import_failure(e)
    getattr(logger, _mcp_log_level)(_mcp_log_message)
    if _dsh_runtime_configured:
        raise RuntimeError("DSH runtime configured but FastAPI-MCP is unavailable") from e
except Exception as e:
    if _dsh_runtime_configured:
        raise
    logger.warning(f"MCP mount failed (non-fatal): {e}")


# ---------------------------------------------------------------------------
# Frontend serving — dashboards (web app) + marketing website + PWA
# ---------------------------------------------------------------------------
# Marketing website + PWA assets (manifest.json, sw.js, icons) served at /site
_website_dir = FRONTEND_DIR / "website"
if _website_dir.is_dir():
    app.mount("/site", StaticFiles(directory=str(_website_dir), html=True), name="website")

# Design System — shared brand tokens/styles + assets. styles.css @imports tokens/*.css.
# Every frontend page links /design-system/styles.css, so one DS export re-themes the
# whole product. Mounted here (before the catch-all "/" mount) so it takes precedence.
_ds_dir = FRONTEND_DIR / "design-system"
if _ds_dir.is_dir():
    app.mount("/design-system", StaticFiles(directory=str(_ds_dir)), name="design_system")


# Unity WebGL build artifacts (Blueprint Virtual Office). Mounted ONLY when a versioned
# build directory exists — static files are flag-independent; the gated entry point is
# /app/office?mode=3d (UNITY_VIRTUAL_OFFICE_ENABLED). Placed before the "/" catch-all.
# Unity builds with decompressionFallback=false → the .br artifacts MUST be served with
# `Content-Encoding: br` (plain StaticFiles sets Content-Type via mimetypes but omits the
# encoding header, so the loader would receive raw brotli bytes and fail).
class _PrecompressedStaticFiles(StaticFiles):
    """StaticFiles that advertises Brotli precompression for Unity WebGL `.br` artifacts.

    Only applied to 200 responses so 404/redirect bodies are never mislabelled as brotli.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        if path.endswith(".br") and getattr(response, "status_code", None) == 200:
            response.headers["Content-Encoding"] = "br"
            _vary = response.headers.get("Vary")
            response.headers["Vary"] = f"{_vary}, Accept-Encoding" if _vary else "Accept-Encoding"
            if path.endswith(".wasm.br"):
                response.headers["Content-Type"] = "application/wasm"
            elif path.endswith(".js.br"):
                response.headers["Content-Type"] = "text/javascript"
            elif path.endswith((".data.br", ".symbols.json.br", ".mem.br")):
                response.headers["Content-Type"] = "application/octet-stream"
        return response


_unity_dir = FRONTEND_DIR / "office_unity"
if _unity_dir.is_dir():
    app.mount(
        "/static/office-unity",
        _PrecompressedStaticFiles(directory=str(_unity_dir)),
        name="office_unity",
    )


@app.get("/app/login", tags=["Frontend"])
async def customer_login_page():
    """Customer (client) login portal — leads/calls/content for their account."""
    return FileResponse(str(FRONTEND_DIR / "login.html"))


@app.get("/login", tags=["Frontend"], include_in_schema=False)
async def login_alias_redirect():
    """Public `/login` → canonical `/app/login` (launch UX; bare /login was 404)."""
    return RedirectResponse(url="/app/login", status_code=307)


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


@app.get("/app/brain", tags=["Frontend"])
async def brain_page():
    """Second Brain — operator search/browse over the Obsidian vault (agents' notes)."""
    return FileResponse(str(FRONTEND_DIR / "brain.html"))


@app.get("/app/admin-login", tags=["Frontend"])
async def admin_login_page():
    """Admin login — email+password → /api/admin/auth/login → sets accessToken (unlocks
    all admin dashboards). Without this, admin pages 401 (no token)."""
    return FileResponse(str(FRONTEND_DIR / "admin_login.html"))


@app.get("/app/voice-keys", tags=["Frontend"])
async def voice_keys_page():
    """Admin: paste free Gemini API keys → validate → activate the voice brain's
    Gemini pool (no SSH / .env / restart). Posts to /api/admin/voice/gemini-keys."""
    return FileResponse(str(FRONTEND_DIR / "voice_keys.html"))


@app.get("/app/calendar", tags=["Frontend"])
async def calendar_page():
    """Content calendar month-view (Buffer-style) — schedule + bookings."""
    return FileResponse(str(FRONTEND_DIR / "calendar.html"))


@app.get("/app/deals", tags=["Frontend"])
async def deals_page():
    """Sales pipeline kanban (drag-drop) over /api/growth/sales/*."""
    return FileResponse(str(FRONTEND_DIR / "deals.html"))


@app.get("/app/customer/pipeline", tags=["Frontend"])
async def customer_pipeline_page():
    """Customer lead Pipeline Kanban — drag-drop board of this client's own leads by status."""
    return FileResponse(str(FRONTEND_DIR / "customer_pipeline.html"))


@app.get("/app/segments", tags=["Frontend"])
async def segments_page():
    """Dynamic condition-based segment builder (Mautic parity) over /api/segments/*."""
    return FileResponse(str(FRONTEND_DIR / "segments.html"))


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
    return FileResponse(
        str(FRONTEND_DIR / "onboard.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/status", tags=["Frontend"])
async def status_page():
    """Public system status page (health/ready client-side checks)."""
    return FileResponse(str(FRONTEND_DIR / "status.html"))


@app.get("/pwa-icon-{size}.png", include_in_schema=False)
async def pwa_icon(size: int):
    """PWA icon runtime-generate (PIL) + disk cache — koi binary repo me nahi."""
    from fastapi.responses import Response as _Resp

    size = 192 if int(size) not in (192, 512) else int(size)
    # Use absolute path anchored to repo root — reliable in any working directory
    icon_path = Path(__file__).resolve().parent.parent / "data" / f"pwa_icon_{size}.png"
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
            dr.text(
                ((size - bb[2] + bb[0]) / 2, (size - bb[3] + bb[1]) / 2 - bb[1]),
                "LG",
                fill="white",
                font=font,
            )
            icon_path.parent.mkdir(parents=True, exist_ok=True)
            img.save(icon_path)
        return FileResponse(str(icon_path), media_type="image/png")
    except OSError as _e:
        logger.debug("pwa_icon render failed: %s", _e)
        return _Resp(status_code=404)


@app.get("/app/customer", tags=["Frontend"])
async def customer_dashboard_page():
    """Customer dashboard — combo (both products: leads, calls, content, posters).
    Marketing-only / voice-only clients are auto-routed to their product page by JS."""
    return FileResponse(str(FRONTEND_DIR / "customer_dashboard.html"))


@app.get("/app/plugins", tags=["Frontend"])
async def customer_plugins_page():
    """Customer-facing AI capabilities page — shows active features for their account."""
    return FileResponse(str(FRONTEND_DIR / "customer_plugins.html"))


@app.get("/app/customer/marketing", tags=["Frontend"])
async def customer_marketing_page():
    """AI Marketing customer dashboard — content, approvals, website tools (voice sections hidden)."""
    return FileResponse(str(FRONTEND_DIR / "customer_dashboard.html"))


@app.get("/app/customer/flows", tags=["Frontend"])
async def customer_flows_page():
    """Phase 7: per-client flow builder (draft-only, gated FLOW_RUNNER_CUSTOMER)."""
    return FileResponse(str(FRONTEND_DIR / "customer_flows.html"))


@app.get("/app/customer/voice", tags=["Frontend"])
async def customer_voice_page():
    """AI Voice Agent customer dashboard — leads, calls, transcripts, routing (marketing sections hidden)."""
    return FileResponse(str(FRONTEND_DIR / "customer_dashboard.html"))


@app.get("/app/admin", tags=["Frontend"])
async def admin_dashboard_page():
    """Admin dashboard (clients, agents, campaigns, revenue, health)."""
    return FileResponse(
        str(FRONTEND_DIR / "admin_dashboard.html"),
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache"},
    )


@app.get("/app/admin/db", tags=["Frontend"])
async def admin_db_explorer_page():
    """Read-only DB explorer (super-admin; ADMIN_DB_EXPLORER gated). Browse any
    Postgres table + CSV export, sensitive columns redacted. Studio-jaisa, OUR DB pe."""
    return FileResponse(str(FRONTEND_DIR / "admin_db.html"))


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


@app.get("/app/owner", tags=["Frontend"])
async def owner_os_page():
    """Owner Operating System — command console, agent registry, approvals, kill switches."""
    return FileResponse(str(FRONTEND_DIR / "owner_os.html"))


@app.get("/app/office", tags=["Frontend"])
async def office_map_page(mode: str | None = None):
    """Virtual office map — all AI staff grouped into rooms, live status + activity.

    mode=3d + UNITY_VIRTUAL_OFFICE_ENABLED=1 → Unity Blueprint Office shell
    (office_blueprint.html). Warna HAMESHA existing 2D Phaser map — flag OFF ya
    mode=map par zero behavior change (INERT default). Docs:
    docs/UNITY_VIRTUAL_OFFICE_ARCHITECTURE.md §2.
    """
    if mode == "3d" and os.getenv("UNITY_VIRTUAL_OFFICE_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        _shell = FRONTEND_DIR / "office_blueprint.html"
        if _shell.is_file():
            return FileResponse(str(_shell))
    return FileResponse(str(FRONTEND_DIR / "office_map.html"))


@app.get("/app/customer/office", tags=["Frontend"])
async def customer_office_page(mode: str | None = None):
    """Customer Blueprint Office shell (Milestone E).

    mode=3d + UNITY_CUSTOMER_OFFICE_ENABLED=1 → office_customer_blueprint.html
    (tenant-scoped shell; data sirf /api/customer/* se). Flag OFF ya koi aur mode →
    existing customer dashboard pe redirect (safe default, fully INERT).
    Docs: docs/UNITY_VIRTUAL_OFFICE_ARCHITECTURE.md §2.
    """
    if mode == "3d" and os.getenv("UNITY_CUSTOMER_OFFICE_ENABLED", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        _shell = FRONTEND_DIR / "office_customer_blueprint.html"
        if _shell.is_file():
            return FileResponse(str(_shell))
    return RedirectResponse("/app/customer", status_code=307)


# 2026-07-19: customer-dashboard views are hash-based (#view-billing etc), so the
# natural path-style deep links customers type/bookmark (/app/customer/billing)
# were a hard 404 (reported bug). STATIC aliases only — a /app/customer/{view}
# catch-all would shadow future sibling routes (first-route-wins, §7 landmine).
# The dashboard's product-redirect script preserves location.hash, so these land
# on the right per-product page with the right view open.
def _register_customer_view_aliases() -> None:
    view_names = ("billing", "leads", "reports", "calendar", "support", "delivery", "setup")

    def _make(view: str):
        async def _alias():
            return RedirectResponse(f"/app/customer#view-{view}", status_code=307)

        _alias.__name__ = f"customer_view_alias_{view}"
        _alias.__doc__ = f"Path-style alias -> /app/customer#view-{view} (hash view engine)."
        return _alias

    for _view in view_names:
        app.get(f"/app/customer/{_view}", tags=["Frontend"])(_make(_view))


# 2026-08-02: legacy top-level page aliases people type/bookmark straight from a
# browser were hard 404s (/admin, /voice, /dashboard, /app/dashboard). Static
# GET-only 307s to the canonical pages — mirrors _register_customer_view_aliases.
# Keep this list exclusive: /admin and /voice are ALSO API router prefixes, but
# those live under /api/*, so these exact top-level paths are safe to own.
def _register_legacy_alias_redirects() -> None:
    _aliases = {
        "/admin": "/app/admin",
        "/voice": "/voice-agent",
        "/dashboard": "/app/customer",
        "/app/dashboard": "/app/customer",
    }

    for _src, _dst in _aliases.items():
        app.get(_src, tags=["Frontend"])(_make_redirect(_src, _dst))


def _make_redirect(src: str, dst: str):
    async def _legacy_alias():
        return RedirectResponse(dst, status_code=307)

    _legacy_alias.__name__ = f"legacy_alias_{src.strip('/').replace('/', '_')}"
    _legacy_alias.__doc__ = f"Legacy alias {src} -> {dst} (canonical page)."
    return _legacy_alias


_register_legacy_alias_redirects()


_register_customer_view_aliases()


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
    """PUBLIC self-serve revenue funnel: pricing → signup → manual UPI checkout.

    Backend already built (/api/billing/plans, /api/public/signup).
    Payments via manual UPI only (Stripe removed 2026-07-10, Razorpay removed 2026-06-18).
    """
    return FileResponse(str(FRONTEND_DIR / "pricing.html"))


@app.get("/start", tags=["Frontend"])
async def start_alias_page():
    """CTA-friendly alias for /pricing."""
    return FileResponse(str(FRONTEND_DIR / "pricing.html"))


@app.get("/reseller", tags=["Frontend"])
async def reseller_page():
    """PUBLIC reseller/agency program — apply form posts to /api/reseller/apply."""
    return FileResponse(str(FRONTEND_DIR / "reseller.html"))


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
    """MERGED→DELETED 2026-07-07 (ADR-034): the old Ops Command Center duplicated
    /app/control-center + /app/ops (LLM health, staff roster, automation flags).
    Route kept as a permanent redirect so old bookmarks/links still land on the
    canonical ops cockpit; command_center.html deleted. Merge-before-delete per
    user mandate."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/app/control-center", status_code=307)


@app.get("/app/delivery-command-center", tags=["Frontend"])
async def delivery_command_center_page():
    """Customer Delivery OS admin front door — total/paying/stuck/receiving-value/
    failed-automation customers, pending approvals, revenue. Business-outcome view;
    distinct from /app/command-center (infra/ops KPI cockpit)."""
    return FileResponse(str(FRONTEND_DIR / "delivery_command_center.html"))


@app.get("/app/dev-control", tags=["Frontend"])
async def dev_control_page():
    """Claude-managed engineering control-plane admin cockpit (dev-task ledger,
    model catalog, deploy-approval gate). Draft-safe: the /api/dev-tasks endpoints
    return 503 unless DEV_ORCHESTRATOR=1, so this page shows a dormant banner
    until the operator enables the feature."""
    return FileResponse(str(FRONTEND_DIR / "dev_control.html"))


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


@app.get("/app/agent-tools", tags=["Frontend"])
async def agent_tools_page():
    """Agent Tools admin cockpit — UI for the 17 /api/agents-ext capabilities
    (Kilo/OpenCode/Ruflo/Hermes): codebase-search, diagnostics, code-review, recall,
    trajectories, consensus, permissions, hooks, custom-agents, capacity, checkpoints,
    batch, code-exec, browser. Admin token from localStorage; super-admin gates honored."""
    return FileResponse(str(FRONTEND_DIR / "agent_tools.html"))


@app.get("/app/conversations", tags=["Frontend"])
async def conversations_page():
    """Unified conversation inbox (GHL-style) — email replies + web-chat + inquiries ek thread view.

    Reads /api/seoops/conversations (admin token). Reply = DRAFT/1-click only, auto-send nahi.
    """
    return FileResponse(str(FRONTEND_DIR / "conversations.html"))


@app.get("/app/affiliates", tags=["Frontend"])
async def affiliates_page():
    """Affiliate/referral admin panel — stats, per-affiliate conversions, ek-tap
    shareable kit (link + WhatsApp text). Reads /api/affiliate/stats (admin token)."""
    return FileResponse(str(FRONTEND_DIR / "affiliates.html"))


@app.get("/app/dialer", tags=["Frontend"])
async def dialer_page():
    """Human telecaller dialer mode (NeoDove-style) — lead queue, tel:/wa.me 1-click, dispositions."""
    return FileResponse(str(FRONTEND_DIR / "dialer.html"))


@app.get("/app/battlecard", tags=["Frontend"])
async def battlecard_page():
    """Internal sales battlecard — LeadGen AI vs Dhanda / AdBanao / MyOperator /
    Vodex.ai / GoHighLevel. Static competitive-intel asset (comparison matrix +
    talk tracks + landmine questions). Admin/sales internal; no API/secrets."""
    return FileResponse(str(FRONTEND_DIR / "battlecard.html"))


@app.get("/app/explorer", tags=["Frontend"])
async def architecture_explorer_page():
    """Interactive architecture + automation flow explorer (graph, builder, IST schedule)."""
    return FileResponse(str(FRONTEND_DIR / "explorer.html"))


@app.get("/app/coordination", tags=["Frontend"])
async def coordination_hub_page():
    """Multi-tool Coordination Hub — Bolt/Cursor/MonkeyCode/OpenCode + Buzz desktop
    notifications ek jagah: live tool sessions, git activity, event + buzz feed."""
    return FileResponse(str(FRONTEND_DIR / "coordination_hub.html"))


@app.get("/app/control-center", tags=["Frontend"])
async def control_center_page():
    """Enterprise AI Control Center — 4-level ops cockpit (L1 Executive live)."""
    return FileResponse(str(FRONTEND_DIR / "control_center.html"))


@app.api_route(
    "/app/control-center/graph",
    methods=["GET", "HEAD"],
    tags=["Frontend"],
    name="control_center_graph_page",
    # GET+HEAD on one registration share one unique_id -> FastAPI "Duplicate
    # Operation ID" warning at /openapi.json build. HTML page needs no schema
    # entry; route registration (app.routes) is unaffected.
    include_in_schema=False,
)
async def control_center_graph_page():
    """Control Center L2 — Sigma.js + ELK WebGL architecture graph (iframe-embedded).

    HEAD is explicit: some probes issue HEAD and a GET-only registration
    returned FastAPI 404 JSON while GET was fine — iframe uses GET, but HEAD
    404 confused operators during L2 blank-canvas triage.
    """
    return FileResponse(str(FRONTEND_DIR / "control_center_graph.html"))


@app.get("/audit", tags=["Frontend"])
async def public_audit_page():
    """PUBLIC lead-magnet: FREE GBP audit funnel (questions → score → inquiry)."""
    return FileResponse(str(_website_dir / "audit.html"))


@app.get("/site-audit", tags=["Frontend"])
async def public_site_audit_page():
    """PUBLIC lead-magnet #2: website URL → AI report card (score/tips/CTA).
    POST /api/growth/tools/website-audit ko call karta (rate-limited)."""
    return FileResponse(str(_website_dir / "site-audit.html"))


@app.get("/geo-check", tags=["Frontend"])
async def public_geo_check_page():
    """PUBLIC lead-magnet #3: AI-search GEO visibility (ChatGPT-style probes).
    POST /api/localseo/geo-check ko call karta (rate-limited 5/min)."""
    return FileResponse(str(_website_dir / "geo-check.html"))


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


def _seo_base_url() -> str:
    """Public base URL — production CORS origin pehle, warna default domain."""
    base = "https://leadsgenai.in"
    try:
        for o in settings.cors_origins or []:
            if o and o.startswith("http") and "*" not in o:
                return o.rstrip("/")
    except (AttributeError, TypeError):
        pass
    return base


@app.get("/llms.txt", include_in_schema=False)
async def llms_txt():
    """AI-discovery file (llmstxt.org) — identity + key links for AI search/agents.

    Claude/Perplexity/ChatGPT-search read this to cite the site. Generated live
    so links use the correct base URL. Never raises (builder has fallback).
    """
    from fastapi.responses import PlainTextResponse

    from app.marketing.ai_discovery import build_llms_txt

    return PlainTextResponse(
        build_llms_txt(_seo_base_url()), media_type="text/plain; charset=utf-8"
    )


@app.get("/pricing.md", include_in_schema=False)
async def pricing_md():
    """Machine-readable pricing for AI buying-agents — generated LIVE from the
    billing source of truth (packages.py + voice_packages.py), so it never drifts.
    """
    from fastapi.responses import PlainTextResponse

    from app.marketing.ai_discovery import build_pricing_md

    return PlainTextResponse(
        build_pricing_md(_seo_base_url()), media_type="text/markdown; charset=utf-8"
    )


@app.get("/sitemap.xml", include_in_schema=False)
async def sitemap_xml():
    """SEO: DYNAMIC sitemap — static pages + every published /blog/{slug}.

    Programmatic SEO blog ke saare articles yahan auto-include hote hain taaki
    Google unhe crawl kare. base URL CORS origin / request host se nikalti hai.
    Enriched with <lastmod>, <changefreq>, <priority> via sitemap_builder.
    """
    from fastapi.responses import Response

    # base URL (production domain pehle; warna request host)
    base = "https://leadsgenai.in"
    try:
        origins = settings.cors_origins or []
        for o in origins:
            if o and o.startswith("http") and "*" not in o:
                base = o.rstrip("/")
                break
    except (AttributeError, TypeError):
        pass

    try:
        from app.api.sitemap_builder import build_sitemap_xml

        xml = await build_sitemap_xml(base)
    except Exception as e:
        # Fallback to bare <loc>-only sitemap if builder unavailable
        logger.warning(f"sitemap_builder failed, using fallback: {e}")
        from xml.sax.saxutils import escape as _xesc

        static_paths = [
            "/",
            "/audit",
            "/pricing",
            "/start",
            "/voice-agent",
            "/compare",
            "/demo",
            "/site-audit",
            "/geo-check",
            "/blog",
            "/app/test-call",
            "/privacy",
            "/terms",
            "/refund",
        ]
        urls: list[str] = list(static_paths)
        try:
            from app.marketing import seo_blog

            for slug in seo_blog.all_slugs():
                if slug:
                    urls.append(f"/blog/{slug}")
        except (ImportError, AttributeError) as _e:
            logger.debug("sitemap seo_blog slugs failed: %s", _e)
        try:
            from app.marketing.clients_store import list_clients

            for c in list_clients(status="active"):
                slug = str(c.get("slug") or "").strip()
                if slug:
                    urls.append(f"/b/{slug}")
        except (ImportError, AttributeError) as _e:
            logger.debug("sitemap clients_store failed: %s", _e)
        _SITEMAP_NICHES = [
            "real-estate",
            "solar",
            "coaching",
            "dental",
            "insurance",
            "home-loans",
            "interior-design",
            "restaurant",
        ]
        _SITEMAP_CITIES = ["india", "mumbai", "delhi", "bangalore"]
        for _n in _SITEMAP_NICHES:
            for _c in _SITEMAP_CITIES:
                urls.append(f"/for/{_n}-in-{_c}")
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
from app.main_helpers import (  # noqa: F401  (re-exported for blog routes)
    _BLOG_CSS,
    _BLOG_FONTS,
    _blog_footer,
    _blog_header,
    _cta_box,
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
        # slug already html-escaped via _h() above — safe to embed in href
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
    return HTMLResponse(content=html, headers={"X-Content-Type-Options": "nosniff"})


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
    import re as _re

    _raw_body = str(article.get("html_body") or "")
    # Strip all tags except a safe allowlist — prevents XSS if DB content is
    # ever poisoned (CWE-79/80). Allowlist: structural + text formatting only.
    _ALLOWED = r"<(/?(h[1-6]|p|ul|ol|li|blockquote|strong|em|b|i|br|hr))(\s[^>]*)?>|<!--.*?-->"
    body_html = _re.sub(
        r"<[^>]+>",
        lambda m: m.group(0) if _re.fullmatch(_ALLOWED, m.group(0), _re.I | _re.S) else "",
        _raw_body,
    )
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
    return HTMLResponse(content=html, headers={"X-Content-Type-Options": "nosniff"})


# ---------------------------------------------------------------------------
# Niche × City SEO landing pages — /for/{niche}-in-{city}
# ---------------------------------------------------------------------------
_NICHE_LABELS: dict[str, str] = {
    "real-estate": "Real Estate",
    "solar": "Solar",
    "coaching": "Coaching",
    "dental": "Dental",
    "insurance": "Insurance",
    "home-loans": "Home Loans",
    "interior-design": "Interior Design",
    "restaurant": "Restaurant",
    "gym": "Gym & Fitness",
    "hospital": "Hospital & Clinic",
    "study-abroad": "Study Abroad",
    "ca-firm": "CA / Accounting Firm",
    "travel": "Travel Agency",
    "beauty": "Beauty Parlour",
    "school": "School",
}
_NICHE_HOOKS_WEB: dict[str, str] = {
    "real-estate": "property listings aur buyer leads",
    "solar": "homeowner inquiries aur site-visit bookings",
    "coaching": "student admissions aur free-demo attendance",
    "dental": "new patient appointments",
    "insurance": "warm local leads aur policy renewals",
    "home-loans": "qualified home-loan applicants",
    "interior-design": "design consultation requests",
    "restaurant": "repeat customers aur online orders",
    "gym": "membership sign-ups aur trial bookings",
    "hospital": "new patient inquiries",
    "study-abroad": "student consultations",
    "ca-firm": "tax-season leads aur referrals",
    "travel": "package inquiries aur bookings",
    "beauty": "appointment bookings aur repeat clients",
    "school": "admissions inquiries",
}


@app.get("/for/{slug}", tags=["Frontend"], include_in_schema=False)
async def niche_landing(slug: str):
    """SEO niche×city landing page — /for/real-estate-in-mumbai etc."""
    from html import escape as _h

    from fastapi.responses import HTMLResponse

    # parse niche + city from slug e.g. "real-estate-in-mumbai"
    parts = slug.lower().split("-in-", 1)
    niche_slug = parts[0].strip()
    city_raw = parts[1].strip() if len(parts) > 1 else "india"
    city = city_raw.replace("-", " ").title()
    niche_label = _NICHE_LABELS.get(niche_slug, niche_slug.replace("-", " ").title())
    hook = _NICHE_HOOKS_WEB.get(niche_slug, "naye customers aur qualified leads")
    city_phrase = f"in {city}" if city.lower() != "india" else "across India"

    title = f"AI Marketing for {niche_label} {city_phrase} — LeadsGenAI"
    desc = (
        f"Automate {hook} for your {niche_label} business {city_phrase}. "
        "AI-powered marketing + lead generation starting ₹1,999/month."
    )
    # Validate slug contains only safe URL chars — prevents injecting quotes/tags
    # into canonical href and JSON-LD (CWE-79/80 via path parameter).
    import re as _re_slug

    if not _re_slug.match(r"^[a-z0-9\-]{1,120}$", slug.lower()):
        from fastapi.responses import HTMLResponse as _HR

        return _HR(content="<h1>Not Found</h1>", status_code=404)
    # Absolute + lowercase-normalized: a raw/relative canonical would let mixed-case
    # slug variants (e.g. /for/Dental-in-Mumbai) each self-canonicalize, splitting
    # ranking signal across duplicates instead of consolidating onto one URL.
    canonical = f"https://leadsgenai.in/for/{_h(slug.lower())}"

    html = (
        '<!DOCTYPE html><html lang="en-IN"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_h(title)}</title>"
        f'<meta name="description" content="{_h(desc)}">'
        f'<link rel="canonical" href="{canonical}">'
        f'<meta property="og:title" content="{_h(title)}">'
        f'<meta property="og:description" content="{_h(desc)}">'
        '<script type="application/ld+json">{"@context":"https://schema.org","@type":"WebPage",'
        f'"name":"{_h(title)}","description":"{_h(desc)}","url":"{canonical}"}}'
        "</script>"
        "<style>body{font-family:system-ui,sans-serif;margin:0;color:#1a1a2e}"
        ".hero{background:linear-gradient(135deg,#4f46e5,#7c3aed);color:#fff;padding:72px 24px;text-align:center}"
        ".hero h1{font-size:2rem;margin:0 0 16px;line-height:1.25}"
        ".hero p{font-size:1.1rem;opacity:.9;max-width:600px;margin:0 auto 28px}"
        ".btn{display:inline-block;background:#fff;color:#4f46e5;padding:14px 28px;border-radius:8px;"
        "font-weight:700;text-decoration:none;margin:6px}"
        ".btn.sec{background:transparent;color:#fff;border:2px solid rgba(255,255,255,.6)}"
        ".features{max-width:800px;margin:56px auto;padding:0 24px}"
        ".features h2{color:#1a1a2e;margin-bottom:24px}"
        ".feat{background:#f8f9ff;border-left:4px solid #4f46e5;padding:16px 20px;margin:12px 0;border-radius:0 8px 8px 0}"
        ".cta{background:#faf5ff;text-align:center;padding:56px 24px}"
        ".cta h2{color:#4f46e5;margin-bottom:8px}"
        ".cta a{display:inline-block;background:#4f46e5;color:#fff;padding:14px 32px;border-radius:8px;"
        "font-weight:700;text-decoration:none;margin-top:16px}"
        "footer{text-align:center;padding:24px;color:#888;font-size:.85rem}"
        "</style></head><body>"
        f'<div class="hero"><h1>{_h(niche_label)} business ke liye<br>AI Marketing {_h(city_phrase)}</h1>'
        f"<p>Automate {_h(hook)} — bina extra manpower ke.</p>"
        '<a href="/audit" class="btn">Free Audit lo</a>'
        '<a href="/pricing" class="btn sec">Pricing dekho</a></div>'
        f'<div class="features"><h2>Hum {_h(niche_label)} businesses ke liye kya karte hain</h2>'
        f'<div class="feat"><b>AI Lead Generation</b> — Google Maps se fresh {_h(niche_label)} prospects auto-scraped roz.</div>'
        f'<div class="feat"><b>Personalized Outreach</b> — Hinglish cold emails + follow-ups automatically, daily cap ke saath.</div>'
        f'<div class="feat"><b>Google Profile Audit</b> — Rating, reviews, aur visibility gaps identify karo — free.</div>'
        f'<div class="feat"><b>AI Content Pack</b> — Weekly posters, captions, aur SEO content — {_h(niche_label)}-specific.</div>'
        '<div class="feat"><b>Advanced: AI Voice Agent</b> — Inbound callback aur lead qualification automatically (₹5,999/mo).</div>'
        "</div>"
        f'<div class="cta"><h2>Shuru karo aaj hi</h2>'
        f"<p>{_h(niche_label)} {_h(city_phrase)} — Starter plan sirf ₹1,999/mahina.</p>"
        '<a href="/start">Abhi Start Karo →</a></div>'
        '<footer>© LeadsGenAI · <a href="/privacy">Privacy</a> · <a href="/terms">Terms</a></footer>'
        "</body></html>"
    )
    return HTMLResponse(content=html, headers={"X-Content-Type-Options": "nosniff"})


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
    # P2 #20: honest ROI ke liye site view record karo (best-effort, never blocks page).
    try:
        from app.marketing import customer_delivery

        customer_delivery.record_site_view(str(client.get("id") or ""))
    except Exception:
        pass
    return HTMLResponse(content=html)


@app.get("/b/{slug}/blog", tags=["Frontend"], include_in_schema=False)
async def client_blog_index(slug: str):
    """Per-client blog (programmatic SEO) — customer ke generate kiye posts, live + indexable."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    try:
        from app.marketing import client_blog
        from app.marketing.clients_store import get_by_slug

        client = get_by_slug(slug)
        if not client:
            return RedirectResponse(url="/", status_code=302)
        return HTMLResponse(content=client_blog.render_index(client, slug))
    except Exception as e:
        logger.warning(f"blog index failed for {slug!r}: {e}")
        return RedirectResponse(url="/", status_code=302)


@app.get("/b/{slug}/blog/{post_slug}", tags=["Frontend"], include_in_schema=False)
async def client_blog_post(slug: str, post_slug: str):
    """Ek blog post page — branded, indexable."""
    from fastapi.responses import HTMLResponse, RedirectResponse

    try:
        from app.marketing import client_blog
        from app.marketing.clients_store import get_by_slug

        client = get_by_slug(slug)
        if not client:
            return RedirectResponse(url="/", status_code=302)
        post = client_blog.get_post(str(client.get("id") or ""), post_slug)
        if not post:
            return RedirectResponse(url=f"/b/{slug}/blog", status_code=302)
        return HTMLResponse(content=client_blog.render_post(client, slug, post))
    except Exception as e:
        logger.warning(f"blog post failed for {slug!r}/{post_slug!r}: {e}")
        return RedirectResponse(url="/", status_code=302)


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


@app.get("/manifest.json", tags=["Frontend"])
async def pwa_manifest():
    """PWA manifest at root scope so the app is installable (inline fallback if file missing)."""
    mf = _website_dir / "manifest.json"
    if mf.is_file():
        return FileResponse(str(mf))
    return JSONResponse(
        {
            "name": "LeadsGen AI",
            "short_name": "LeadsGen AI",
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


@app.get("/health/platform", operation_id="platform_detailed_health", tags=["Health"])
async def platform_detailed_health():
    """Detailed platform/ML health.

    NOTE: `/health` (liveness, `environment:production`) is served by
    `app.api.health` (mounted first at module load) — this richer view lives
    at a distinct path so it stays reachable and avoids the duplicate-route /
    OpenAPI operation-id collision (audit 2026-06-21)."""
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
    # Intentional dev entrypoint bind; production runs containerized uvicorn.
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # nosec B104 - intentional dev bind
        port=8000,
        reload=settings.is_development,
    )
