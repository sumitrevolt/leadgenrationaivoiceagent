"""
Production Middleware Stack
Rate limiting, security headers, API authentication, and request tracing
"""

import asyncio
import os
import threading
import time
import uuid
from collections.abc import Callable
from functools import wraps
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.security import APIKeyHeader, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.utils.logger import setup_logger, redact_url

logger = setup_logger(__name__)


def _real_client_ip(request: Request) -> str:
    """Real client IP — rightmost trusted proxy entry, then socket peer.

    SECURITY: use the RIGHTMOST X-Forwarded-For entry — that is the value the
    trusted proxy (Caddy/Nginx) appended = the real peer IP. The leftmost entry
    is fully client-controlled (an attacker can prepend any IP to bypass
    rate-limiting), so it MUST NEVER drive an auth/rate decision (CWE-20).
    X-Real-IP from a trusted proxy is also acceptable (single upstream hop).
    """
    xff = request.headers.get("x-forwarded-for")
    if xff:
        parts = [p.strip() for p in xff.split(",") if p.strip()]
        if parts:
            return parts[-1]  # rightmost = trusted proxy's appended value
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


# =============================================================================
# SECURITY HEADERS MIDDLEWARE
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""

    # Paths jo CLIENT websites pe iframe hote hain — in pe X-Frame-Options DENY
    # nahi lagana (warna browser embed block kar deta — lead widget + reviews
    # widget client sites pe kabhi render hi nahi hote).
    _EMBEDDABLE_PREFIXES = ("/api/engage/reviews-widget",)

    @staticmethod
    def _is_embeddable(path: str) -> bool:
        if path.startswith(SecurityHeadersMiddleware._EMBEDDABLE_PREFIXES):
            return True
        # /b/{slug}/embed (lead-capture iframe)
        return path.startswith("/b/") and path.endswith("/embed")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        embeddable = False
        try:
            embeddable = self._is_embeddable(request.url.path)
        except (AttributeError, TypeError) as _e:
            logger.debug("SecurityHeadersMiddleware embeddable check failed: %s", _e)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not embeddable:
            response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP: dashboards/web-call pages load Chart.js etc. from jsDelivr/cdnjs and
        # Google Fonts, use inline <script>/<style>, talk to the API over
        # fetch/WebSocket, and play mic-recorded audio from blobs.
        # img-src: QR (api.qrserver.com) + AI images (pollinations) admin pages me
        # direct render hote hain.
        _frame = "frame-ancestors *; " if embeddable else ""
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            + _frame
            + "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://api.qrserver.com https://gen.pollinations.ai "
            "https://image.pollinations.ai https://media.pollinations.ai; "
            "connect-src 'self' wss:; "
            "media-src 'self' blob: data:"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Microphone stays available to same-origin pages — the browser
        # web-call demo (/app/test-call) records the caller's voice.
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"

        # Dashboards, revenue funnel + SW: browser/SW stale HTML cache se bachao.
        # Pricing/start par stale CTA seedha paid conversion ko block karta hai.
        try:
            path = request.url.path or ""
            if request.method == "GET" and (
                path.startswith("/app/") or path in ("/pricing", "/start", "/sw.js")
            ):
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
                response.headers["Pragma"] = "no-cache"
        except (AttributeError, TypeError) as _e:
            logger.debug("SecurityHeadersMiddleware cache-control failed: %s", _e)

        # Remove server header
        if "server" in response.headers:
            del response.headers["server"]

        return response


# =============================================================================
# REQUEST TRACING MIDDLEWARE
# =============================================================================


class RequestTracingMiddleware(BaseHTTPMiddleware):
    """Add request tracing for observability"""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Add to request state
        request.state.request_id = request_id

        # Log request
        start_time = time.time()

        logger.info(
            "Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": redact_url(str(request.url.path) if request.url.path else ""),
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

        try:
            response = await call_next(request)

            # Calculate duration
            duration = time.time() - start_time

            # Add headers
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{duration:.3f}s"

            # Log response
            logger.info(
                "Request completed",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration_ms": int(duration * 1000),
                },
            )

            return response

        except Exception as e:
            duration = time.time() - start_time
            logger.error(
                f"Request failed: {str(e)}",
                extra={
                    "request_id": request_id,
                    "duration_ms": int(duration * 1000),
                    "error": str(e),
                },
            )
            raise


# =============================================================================
# RATE LIMITING MIDDLEWARE
# =============================================================================


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Production-ready rate limiter using Redis
    Falls back to in-memory if Redis is unavailable
    """

    def __init__(
        self,
        app: FastAPI,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._redis_limiter = None
        self._fallback_counts: dict = {}  # Fallback for when Redis unavailable

    async def _get_limiter(self):
        """Get or create Redis rate limiter"""
        if self._redis_limiter is None:
            try:
                from app.cache import RateLimiter

                self._redis_limiter = RateLimiter(
                    prefix="ratelimit:api",
                    max_requests=self.requests_per_minute,
                    window_seconds=60,
                )
            except Exception as e:
                logger.warning(f"Could not initialize Redis rate limiter: {e}")
        return self._redis_limiter

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip rate limiting for health checks and metrics
        skip_paths = ["/health", "/health/live", "/health/ready", "/metrics"]
        if request.url.path in skip_paths:
            return await call_next(request)

        client_ip = _real_client_ip(request)

        # Try Redis rate limiter first
        limiter = await self._get_limiter()
        if limiter:
            try:
                allowed, remaining = await limiter.is_allowed(client_ip)

                if not allowed:
                    logger.warning(f"Rate limit exceeded for {client_ip}")
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "Rate limit exceeded. Please slow down.",
                            "retry_after": 60,
                        },
                        headers={
                            "Retry-After": "60",
                            "X-RateLimit-Limit": str(self.requests_per_minute),
                            "X-RateLimit-Remaining": "0",
                        },
                    )

                # Process request and add rate limit headers
                response = await call_next(request)
                response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
                response.headers["X-RateLimit-Remaining"] = str(remaining)
                return response

            except Exception as e:
                logger.warning(f"Redis rate limiter failed, using fallback: {e}")

        # Fallback to in-memory rate limiting
        current_minute = int(time.time() / 60)
        key = f"{client_ip}:{current_minute}"

        if key not in self._fallback_counts:
            self._fallback_counts[key] = 0

        self._fallback_counts[key] += 1

        if self._fallback_counts[key] > self.requests_per_minute:
            logger.warning(f"Rate limit exceeded for {client_ip} (fallback)")
            return JSONResponse(
                status_code=429,
                content={
                    "detail": "Rate limit exceeded. Please slow down.",
                    "retry_after": 60,
                },
                headers={"Retry-After": "60"},
            )

        # Cleanup old entries periodically
        if len(self._fallback_counts) > 10000:
            # minute is the LAST colon-segment; rsplit (not split) so IPv6 client_ips
            # (which contain colons) don't make int() raise ValueError -> 500 storm.
            old_keys = [
                k
                for k in self._fallback_counts.keys()
                if k.rsplit(":", 1)[-1].isdigit() and int(k.rsplit(":", 1)[-1]) < current_minute - 5
            ]
            for k in old_keys:
                del self._fallback_counts[k]

        return await call_next(request)


# =============================================================================
# API KEY AUTHENTICATION
# =============================================================================

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Depends(API_KEY_HEADER)) -> dict | None:
    """
    Verify API key and return client info
    """
    if not api_key:
        return None

    import hmac
    # Use a dedicated API key env var — NEVER compare against secret_key
    # (session-signing key). Use hmac.compare_digest to prevent timing attacks.
    _admin_api_key = os.environ.get("ADMIN_API_KEY", "").strip()
    if _admin_api_key and hmac.compare_digest(api_key, _admin_api_key):
        return {"client": "admin", "permissions": ["all"]}

    return None


def require_api_key(permissions: list = None):
    """
    Decorator to require API key authentication
    """

    async def dependency(request: Request, client: dict | None = Depends(verify_api_key)):
        if not client:
            raise HTTPException(
                status_code=401,
                detail="Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

        if permissions:
            client_permissions = client.get("permissions", [])
            if "all" not in client_permissions:
                if not any(p in client_permissions for p in permissions):
                    raise HTTPException(
                        status_code=403,
                        detail="Insufficient permissions",
                    )

        request.state.client = client
        return client

    return Depends(dependency)


# =============================================================================
# TENANT CONTEXT MIDDLEWARE
# =============================================================================


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    Extract and validate tenant context from request
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract tenant ID from header or subdomain
        tenant_id = request.headers.get("X-Tenant-ID")

        if not tenant_id and "subdomain" in request.url.netloc:
            # Extract from subdomain if applicable
            subdomain = request.url.netloc.split(".")[0]
            tenant_id = subdomain

        # Store in request state
        request.state.tenant_id = tenant_id

        return await call_next(request)


# =============================================================================
# COMPRESSION MIDDLEWARE
# =============================================================================


def add_gzip_middleware(app: FastAPI):
    """Add gzip compression for responses"""
    from starlette.middleware.gzip import GZipMiddleware

    app.add_middleware(GZipMiddleware, minimum_size=1000)


# =============================================================================
# REQUEST GUARD MIDDLEWARE — per-request timeout (504) + load-shed (503)
# =============================================================================

# Per-worker in-flight counter (worker apne event-loop ko khud protect kare — yeh
# granularity sahi hai, distributed nahi chahiye).
_INFLIGHT = 0


class RequestGuardMiddleware(BaseHTTPMiddleware):
    """Inbound reliability guard (audit): per-request hard TIMEOUT (slow handler worker ko
    indefinitely hold na kare → 504, upstream-proxy 504 se pehle) + LOAD-SHED (per-worker
    in-flight cap → 503 + Retry-After; overload-collapse se bachao, mid-flight cut nahi).

    GATED `REQUEST_GUARD=1` (default OFF = zero change). Long/streaming/ws paths SKIP
    (warna voice/LLM/SSE cut ho jate). FAIL-OPEN: koi bhi guard-error pe normal process
    (legit traffic kabhi na ruke). Tunables: REQUEST_TIMEOUT_S, REQUEST_MAX_INFLIGHT,
    REQUEST_GUARD_SKIP (comma paths)."""

    def __init__(self, app: FastAPI):
        super().__init__(app)
        self.timeout_s = float(os.environ.get("REQUEST_TIMEOUT_S", "55") or 55)
        self.max_inflight = int(os.environ.get("REQUEST_MAX_INFLIGHT", "200") or 200)
        _default_skip = (
            "/ws,/health,/metrics,/api/web-call,/api/voiceai,/agents/coordinate,"
            "/api/agents/run,/api/ml,/api/ai"
        )
        self.skip = tuple(
            p.strip()
            for p in os.environ.get("REQUEST_GUARD_SKIP", _default_skip).split(",")
            if p.strip()
        )

    def _skip(self, path: str) -> bool:
        return path.startswith(self.skip) or "stream" in path

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        global _INFLIGHT
        try:
            path = request.url.path
            if self._skip(path):
                return await call_next(request)
            # LOAD-SHED: per-worker in-flight cap (overload pe naye ko 503, running ko cut nahi)
            if _INFLIGHT >= self.max_inflight:
                logger.warning("RequestGuard load-shed 503 (in-flight=%d) %s", _INFLIGHT, path)
                return JSONResponse(
                    status_code=503,
                    content={"detail": "Server busy — thodi der baad try karo."},
                    headers={"Retry-After": "5"},
                )
            _INFLIGHT += 1
            try:
                return await asyncio.wait_for(call_next(request), timeout=self.timeout_s)
            except asyncio.TimeoutError:
                logger.warning("RequestGuard timeout 504 (%.0fs) %s", self.timeout_s, path)
                return JSONResponse(
                    status_code=504,
                    content={"detail": "Request timed out — phir se try karo."},
                    headers={"Retry-After": "5"},
                )
            finally:
                _INFLIGHT -= 1
        except Exception as e:  # fail-open — guard kabhi legit request na rok de
            logger.debug("RequestGuard fail-open: %s", e)
            return await call_next(request)


# =============================================================================
# PLAN-TIER AWARE RATE LIMITING  (genuinely additive — existing limiter is flat
# per-IP only, not plan-aware. SaaS standard: Starter 60rpm < Growth 200rpm <
# Advanced 500rpm. FAIL-OPEN: plan lookup fails → generous fallback, no block.
# GATED: PLAN_RATE_LIMIT=1 env var (default OFF — zero behaviour change).
# =============================================================================

_PLAN_LIMITS: dict[str, int] = {
    # Marketing tiers (packages.py)
    "starter": 60,
    "growth": 200,
    "advanced": 500,
    # Voice tiers (voice_packages.py)
    "vstarter": 60,
    "vgrowth": 200,
    "vpro": 500,
    # Combo tiers
    "combo_starter": 100,
    "combo_growth": 300,
    "combo_advanced": 600,
    # Admin / internal
    "admin": 9999,
    "internal": 9999,
}
_DEFAULT_RPM_AUTHED = 100
_DEFAULT_RPM_ANON = 60  # was 20 — admin SPA logout ke baad login page block na ho


def _plan_prefix(plan: str | None) -> str:
    if not plan:
        return ""
    p = str(plan).lower().strip()
    for prefix in sorted(_PLAN_LIMITS, key=len, reverse=True):
        if p.startswith(prefix):
            return prefix
    return ""


def _rpm_for_plan(plan: str | None, client_id: str | None) -> int:
    prefix = _plan_prefix(plan)
    if prefix:
        return _PLAN_LIMITS.get(prefix, _DEFAULT_RPM_AUTHED)
    return _DEFAULT_RPM_AUTHED if client_id else _DEFAULT_RPM_ANON


class PlanTierRateLimitMiddleware(BaseHTTPMiddleware):
    """Plan-aware rate limiter (per-plan RPM, not flat per-IP).

    Identity resolution:
      1. request.state.tenant (TenantBrandingMiddleware) → slug → DB plan
      2. X-Client-ID header → plan lookup
      3. IP fallback (anon limit)

    Completely FAIL-OPEN. GATED: PLAN_RATE_LIMIT=1 (default OFF).
    """

    _SKIP = (
        "/health",
        "/metrics",
        "/ws",
        "/api/web-call/ws",
        "/api/web-call/stream",
        "/api/telephony/",
        "/api/voiceai",
        "/status",
        "/robots.txt",
        "/sitemap.xml",
    )
    # Auth + login surfaces — never block HTML login or credential POST (brute-force
    # has dedicated rate_limit deps on those routes).
    _AUTH_SKIP = (
        "/api/admin/auth/",
        "/api/customer/auth/",
        "/api/team-access/auth/",
    )
    _APP_HTML_PREFIX = "/app/"

    def _should_skip(self, path: str) -> bool:
        if any(path == p or path.startswith(p + "/") for p in self._SKIP):
            return True
        if path.startswith(self._AUTH_SKIP):
            return True
        # Plan limits = API abuse guard; static /app/* HTML pages never 429 here.
        if path.startswith(self._APP_HTML_PREFIX):
            return True
        return False

    def _rpm_from_bearer(self, request: Request) -> int | None:
        """Valid admin JWT → internal tier (logout se pehle dashboard burst safe)."""
        auth = (request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            import jwt
            from jwt.exceptions import PyJWTError

            from app.api.admin import JWT_ALGORITHM, JWT_SECRET

            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                return None
            role = str(payload.get("role") or "").lower()
            if role in ("admin", "super_admin"):
                return _PLAN_LIMITS["admin"]
            if role == "customer":
                return _DEFAULT_RPM_AUTHED
        except (ImportError, AttributeError, KeyError) as _e:
            logger.debug("PlanTierRateLimit bearer JWT decode skipped: %s", _e)
            return None
        except Exception as _e:
            logger.debug("PlanTierRateLimit bearer parse error: %s", _e)
            return None
        return None

    async def _resolve_plan(self, request: Request) -> tuple[str | None, str | None]:
        try:
            tenant = getattr(request.state, "tenant", None)
            if isinstance(tenant, dict) and tenant.get("slug"):
                from app.marketing.clients_store import get_by_slug

                c = get_by_slug(tenant["slug"])
                if c:
                    return str(c.get("id", tenant["slug"])), str(c.get("plan") or "")
            cid = request.headers.get("X-Client-ID", "").strip()
            if cid:
                from app.marketing.clients_store import get_client

                c = get_client(cid)
                return cid, str((c or {}).get("plan") or "")
        except (ImportError, AttributeError) as _e:
            logger.debug("PlanTierRateLimit plan store unavailable: %s", _e)
        except Exception as _e:
            logger.debug("PlanTierRateLimit plan resolve error: %s", _e)
        return None, None

    async def _redis_check(self, key: str, limit: int) -> tuple[bool, int]:
        try:
            from app.cache import get_redis_client

            r = await get_redis_client()
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, 62)
            count = int((await pipe.execute())[0])
            return (count <= limit, max(0, limit - count))
        except Exception as _e:
            logger.debug("PlanTierRateLimit redis check fail-open: %s", _e)
            return (True, limit)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if os.environ.get("PLAN_RATE_LIMIT", "0") not in ("1", "true", "yes"):
            return await call_next(request)
        # BaseHTTPMiddleware cannot handle WebSocket upgrades — skip all WS.
        if request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)
        path = request.url.path
        if self._should_skip(path):
            return await call_next(request)
        # Non-API assets (/, /audit, /blog, /b/, frontend static) — skip plan tier.
        if not path.startswith("/api/"):
            return await call_next(request)
        try:
            bearer_rpm = self._rpm_from_bearer(request)
        except Exception as _e:
            logger.debug("PlanTierRateLimit bearer parse failed: %s", _e)
            bearer_rpm = None
        try:
            client_id, plan = await self._resolve_plan(request)
        except Exception as _e:
            logger.debug("PlanTierRateLimit plan resolve failed: %s", _e)
            client_id, plan = None, None
        rpm = bearer_rpm if bearer_rpm is not None else _rpm_for_plan(plan, client_id)
        identity = client_id or _real_client_ip(request)
        minute = int(time.time() / 60)
        key = f"plantier:{identity}:{minute}"
        allowed, remaining = await self._redis_check(key, rpm)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "detail": f"Plan rate limit ({rpm} req/min) exceeded. Upgrade plan for higher limits.",
                    "limit_rpm": rpm,
                    "plan": plan or "anon",
                    "retry_after": 60,
                },
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(rpm),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Plan": str(plan or "anon"),
                },
            )
        try:
            response = await call_next(request)
        except Exception as _e:
            logger.error("PlanTierRateLimit call_next failed: %s", _e)
            raise
        response.headers["X-RateLimit-Limit"] = str(rpm)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Plan"] = str(plan or "anon")
        return response


# =============================================================================
# ROUTE-HIT COUNTER MIDDLEWARE — "unused API" telemetry (Redis HINCRBY per path)
# =============================================================================


# Retain fire-and-forget increment tasks so the event loop doesn't GC them mid-run
# (an un-referenced create_task() can be collected before it executes → low-traffic
# routes would lose hits = the exact false "dead route" signal this feature avoids).
_ROUTE_HIT_TASKS: set = set()
_route_hit_sync_client = None
_route_hit_sync_lock = threading.Lock()


def _route_hit_hincrby(key: str, path: str) -> None:
    """Increment telemetry with a process-local, thread-safe Redis client.

    The shared async cache pool is bound to the event loop that created it.
    Route-hit tasks may run on another uvicorn loop, so this best-effort counter
    deliberately uses redis-py's synchronous pool inside ``asyncio.to_thread``.
    """
    global _route_hit_sync_client
    if _route_hit_sync_client is None:
        with _route_hit_sync_lock:
            if _route_hit_sync_client is None:
                import redis

                _route_hit_sync_client = redis.Redis.from_url(
                    str(settings.redis_url),
                    socket_connect_timeout=2,
                    socket_timeout=2,
                    decode_responses=True,
                )
    _route_hit_sync_client.hincrby(key, path, 1)


class RouteHitMiddleware(BaseHTTPMiddleware):
    """Best-effort per-route hit counter for the "unused API / dead route" view.

    Increments a Redis hash `route_hits:{YYYYMMDD}` (UTC) keyed by the request's
    ROUTE TEMPLATE (e.g. `/api/b/{slug}` not `/api/b/acme`) so per-id/per-slug
    routes don't blow up cardinality. The route template only exists in
    `request.scope["route"]` AFTER routing, so we read it AFTER call_next and
    fire-and-forget the increment — ZERO added latency, response unchanged.

    GATED `ROUTE_HIT_COUNTER=1` (default OFF): only registered in the stack at
    boot when the flag is on, so OFF = the middleware isn't even present (zero
    overhead). FAIL-SILENT: any error (redis down, no route) → skip, never raise.
    BaseHTTPMiddleware doesn't dispatch WebSocket scopes → voice/WS untouched.
    """

    @staticmethod
    def _route_path(request: Request) -> str:
        # Route template (path_format) is populated only AFTER routing. Fall back
        # to the raw path when no route matched (404s etc.).
        try:
            route = request.scope.get("route")
            tmpl = getattr(route, "path_format", None)
            if tmpl:
                return str(tmpl)
        except (KeyError, AttributeError, TypeError) as _e:
            logger.debug("RouteHitMiddleware route template lookup failed: %s", _e)
        try:
            return request.url.path
        except (AttributeError, TypeError) as _e:
            logger.debug("RouteHitMiddleware url.path lookup failed: %s", _e)
            return "unknown"

    @staticmethod
    async def _record(path: str) -> None:
        """Fire-and-forget Redis HINCRBY. Swallows ALL errors (best-effort)."""
        try:
            day = time.strftime("%Y%m%d", time.gmtime())
            await asyncio.to_thread(_route_hit_hincrby, f"route_hits:{day}", path)
        except Exception as _e:
            # Telemetry is explicitly fail-silent: it must never leak a task
            # exception or affect the customer response when Redis is degraded.
            logger.debug("RouteHitMiddleware redis record failed: %s", _e)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        try:
            path = self._route_path(request)
            task = asyncio.create_task(self._record(path))
            _ROUTE_HIT_TASKS.add(task)
            task.add_done_callback(_ROUTE_HIT_TASKS.discard)
        except (RuntimeError, AttributeError, TypeError) as _e:
            logger.debug("RouteHitMiddleware task create failed: %s", _e)
        return response


# =============================================================================
# SETUP ALL MIDDLEWARE
# =============================================================================


def setup_middleware(app: FastAPI, production: bool = False):
    """
    Configure all middleware for the application
    Order matters: last added = first executed
    """

    # Compression DISABLED (2026-06-17): GZipMiddleware innermost tha, isliye compressed
    # body ko ek outer middleware text-process karke corrupt kar raha tha (gzip byte 0x8b strip),
    # jisse Caddy ko "gzip: invalid header" milta tha aur SAARE HTML pages empty serve hote the.
    # Plain serve karo (correct). Client-side compression Caddy `encode` se add ki ja sakti hai.
    # add_gzip_middleware(app)

    # Tenant context
    app.add_middleware(TenantContextMiddleware)

    # Reseller white-label branding (fail-open: attaches request.state.tenant).
    try:
        from app.middleware.tenant import TenantBrandingMiddleware

        app.add_middleware(TenantBrandingMiddleware)
    except ImportError:
        pass
    except Exception as _e:
        logger.warning("TenantBrandingMiddleware not loaded: %s", _e)

    # Plan-tier aware rate limiting (GATED: PLAN_RATE_LIMIT=1, default OFF).
    # Run BEFORE flat IP limiter so plan limits apply first.
    app.add_middleware(PlanTierRateLimitMiddleware)

    # Flat IP rate limiting (baseline protection regardless of plan)
    if production:
        app.add_middleware(
            RateLimitMiddleware,
            requests_per_minute=100,
            requests_per_hour=2000,
        )

    # Request tracing
    app.add_middleware(RequestTracingMiddleware)

    # Security headers (applied first, so last in chain)
    app.add_middleware(SecurityHeadersMiddleware)

    # Request guard (per-request timeout + load-shed) — GATED `REQUEST_GUARD=1`, default OFF
    if os.environ.get("REQUEST_GUARD", "0").strip().lower() in ("1", "true", "yes"):
        app.add_middleware(RequestGuardMiddleware)
        logger.info(
            "✅ RequestGuard enabled (timeout=%ss, max_inflight=%s)",
            os.environ.get("REQUEST_TIMEOUT_S", "55"),
            os.environ.get("REQUEST_MAX_INFLIGHT", "200"),
        )

    # Route-hit counter ("unused API" telemetry) — GATED `ROUTE_HIT_COUNTER=1`,
    # default OFF. Only added to the stack when on at boot → zero overhead off.
    if os.getenv("ROUTE_HIT_COUNTER", "").strip().lower() in ("1", "true", "yes", "on"):
        app.add_middleware(RouteHitMiddleware)
        logger.info("✅ RouteHitCounter enabled (route_hits: daily-key HINCRBY)")

    logger.info(f"✅ Middleware stack configured (production={production})")
