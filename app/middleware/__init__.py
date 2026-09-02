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
from app.utils.logger import redact_url, setup_logger

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

    # Paths jo SIRF humaari apni admin UI ke andar <iframe> hote hain (kabhi
    # kisi external site se nahi) — in pe blanket DENY nahi (warna apna hi
    # iframe load nahi hota), par blanket "frame-ancestors *" bhi nahi (koi
    # external site embed na kar sake) — SAMEORIGIN + frame-ancestors 'self'.
    # ADR-104 (2026-07-15): Control Center L2 Stack graph is exactly this —
    # X-Frame-Options: DENY (the correct default for every OTHER admin page)
    # was silently blocking control_center.html's own same-origin
    # <iframe src="/app/control-center/graph">, rendering as a blank canvas
    # with no console error (the browser's frame-refusal isn't a JS
    # exception, so nothing logged) — the page itself was never broken.
    _SAME_ORIGIN_EMBEDDABLE_PREFIXES = ("/app/control-center/graph",)

    @staticmethod
    def _is_embeddable(path: str) -> bool:
        if path.startswith(SecurityHeadersMiddleware._EMBEDDABLE_PREFIXES):
            return True
        # /b/{slug}/embed (lead-capture iframe)
        return path.startswith("/b/") and path.endswith("/embed")

    @staticmethod
    def _is_same_origin_embeddable(path: str) -> bool:
        return path.startswith(SecurityHeadersMiddleware._SAME_ORIGIN_EMBEDDABLE_PREFIXES)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)

        embeddable = False
        same_origin_embeddable = False
        try:
            embeddable = self._is_embeddable(request.url.path)
            same_origin_embeddable = self._is_same_origin_embeddable(request.url.path)
        except (AttributeError, TypeError) as _e:
            logger.debug("SecurityHeadersMiddleware embeddable check failed: %s", _e)

        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        if not embeddable:
            response.headers["X-Frame-Options"] = "SAMEORIGIN" if same_origin_embeddable else "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        # CSP: dashboards/web-call pages load Chart.js etc. from jsDelivr/cdnjs and
        # Google Fonts, use inline <script>/<style>, talk to the API over
        # fetch/WebSocket, and play mic-recorded audio from blobs.
        # img-src: QR (api.qrserver.com) + AI images (pollinations) admin pages me
        # direct render hote hain.
        # PostHog (product analytics, POSTHOG_API_KEY set in prod): loader script
        # serve hota hai https://us-assets.i.posthog.com se aur events beacon
        # https://*.i.posthog.com pe jaate hain (api host = us.i.posthog.com).
        # Allowed hosts — sirf PostHog infra, koi generic wildcard nahi.
        # SIRF apni UI pages pe (non-embeddable): client-website me framed widget
        # (/b/{slug}/embed, reviews-widget) apni CSP me PostHog nahi le sakta —
        # embeddable pages ke liye _posthog_src empty rahta hai (no CSP widening).
        _posthog_src = (
            "" if embeddable else " https://*.i.posthog.com https://us-assets.i.posthog.com"
        )
        if embeddable:
            _frame = "frame-ancestors *; "
        elif same_origin_embeddable:
            _frame = "frame-ancestors 'self'; "
        else:
            _frame = ""
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            + _frame
            + "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdnjs.cloudflare.com"
            + _posthog_src
            + "; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://cdn.jsdelivr.net https://cdnjs.cloudflare.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: blob: https://api.qrserver.com https://gen.pollinations.ai "
            "https://image.pollinations.ai https://media.pollinations.ai; "
            "connect-src 'self' wss:" + _posthog_src + "; "
            "media-src 'self' blob: data:"
        )
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # Microphone stays available to same-origin pages — the browser
        # web-call demo (/app/test-call) records the caller's voice.
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(self), camera=()"

        # Dashboards, conversion funnel + SW: browser/SW stale HTML cache se bachao.
        # Landing/audit/pricing/start par stale CTA seedha paid conversion ko block karta hai.
        try:
            path = request.url.path or ""
            conversion_pages = (
                "/",
                "/index.html",
                "/audit",
                "/site-audit",
                "/demo",
                "/pricing",
                "/start",
                "/sw.js",
            )
            if request.method == "GET" and (path.startswith("/app/") or path in conversion_pages):
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

# Asset requests are not API calls. `app.main` mounts StaticFiles on `/`,
# `/site`, `/design-system` and `/unity`, so one dashboard page load fires
# dozens of CSS/JS/font/image requests from a single IP. Charging them to the
# same per-IP budget as API traffic is what let one legitimate operator session
# trip the flat limiter. Assets get their OWN bucket — a separate budget, not an
# exemption: flooding a static path is still capped, and `RATE_LIMIT_ASSET_MULT=1`
# collapses the asset ceiling back onto the API ceiling.
_ASSET_PATH_PREFIXES = (
    "/static/",
    "/assets/",
    "/design-system/",
    "/site/",
    "/unity/",
    "/css/",
    "/js/",
    "/img/",
    "/images/",
    "/fonts/",
)
_ASSET_SUFFIXES = (
    ".css",
    ".js",
    ".mjs",
    ".map",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".avif",
    ".woff",
    ".woff2",
    ".ttf",
    ".otf",
    ".eot",
    ".mp4",
    ".webm",
    ".wasm",
    ".br",
    ".data",
    ".webmanifest",
)


def _is_asset_path(path: str) -> bool:
    """True for static-asset paths. `/api/*` is NEVER an asset."""
    if not path or path.startswith("/api/"):
        return False
    if path.startswith(_ASSET_PATH_PREFIXES):
        return True
    return path.rsplit("/", 1)[-1].lower().endswith(_ASSET_SUFFIXES)


# Admin/Mission-Control fan-out may need a higher GET budget — NEVER a write
# bypass. Prefixes are read-ish dashboard surfaces; method gate is mandatory.
_ADMIN_READ_RELIEF_PREFIXES = (
    "/api/growth/",
    "/api/activation/",
    "/api/admin/",
)


def _is_safe_idempotent_admin_read(request: Request) -> bool:
    """True only for GET/HEAD on explicit dashboard read prefixes."""
    method = (getattr(request, "method", None) or "GET").upper()
    if method not in ("GET", "HEAD"):
        return False
    path = request.url.path if hasattr(request, "url") else ""
    path = path or ""
    return any(path.startswith(p) for p in _ADMIN_READ_RELIEF_PREFIXES)


# Human HTML page navigation gets its own higher bucket — same philosophy as the
# asset bucket: a page-load burst (multi-tab dashboard browse) must not trip the
# shared per-IP API budget, and API XHRs must not be starved by page loads.
# NEVER a write bypass — method gate is mandatory, /api/* never qualifies.
_HTML_BROWSE_PREFIXES = (
    "/app/",
    "/pricing",
    "/start",
    "/voice-agent",
)


def _is_html_navigation(request: Request) -> bool:
    """True only for GET/HEAD on the HTML page families (never /api, never writes)."""
    method = (getattr(request, "method", None) or "GET").upper()
    if method not in ("GET", "HEAD"):
        return False
    path = request.url.path if hasattr(request, "url") else ""
    path = path or ""
    if path.startswith("/api/"):
        return False
    return any(
        path == p or path.startswith(p if p.endswith("/") else p + "/")
        for p in _HTML_BROWSE_PREFIXES
    )


def _fixed_window_retry_after(window_seconds: int = 60, now: float | None = None) -> int:
    """Seconds until the CURRENT fixed window rolls over.

    ``app.cache.RateLimiter`` keys on ``int(time.time() // window_seconds)``, so
    the counter resets at the next window boundary — not ``window_seconds`` from
    the moment the caller was blocked. A hardcoded 60 told someone who tripped
    the limit at second 58 to wait a full minute for a 2-second reset, and every
    FE renders that number as a literal countdown.
    """
    if window_seconds <= 0:
        return 1
    now = time.time() if now is None else now
    remaining = window_seconds - (now % window_seconds)
    secs = int(remaining)
    if remaining > secs:
        secs += 1
    return max(1, min(secs, window_seconds))


def _rate_limit_429(*, retry_after: int, scope: str, limit: int | None = None) -> JSONResponse:
    """Uniform 429 body — same contract as ``app.api.ratelimit`` (Loop 6/16).

    ``detail`` must be a dict: every FE 429 handler does
    ``typeof j.detail === "object" ? j.detail : {}`` (login.html, pricing.html,
    customer_dashboard.html), so a bare string silently drops the countdown and
    the scope. The top-level ``retry_after`` is kept for older callers.
    """
    headers = {"Retry-After": str(retry_after)}
    if limit is not None:
        headers["X-RateLimit-Limit"] = str(limit)
        headers["X-RateLimit-Remaining"] = "0"
    return JSONResponse(
        status_code=429,
        content={
            "detail": {
                "error": "rate_limited",
                "message": "Rate limit exceeded. Please slow down.",
                "retry_after": retry_after,
                "scope": scope,
            },
            "retry_after": retry_after,
        },
        headers=headers,
    )


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Production-ready rate limiter using Redis
    Falls back to in-memory if Redis is unavailable

    Policy (2026-07-30 — platform-blocker 429 lane; P1 harden):
    - Flat anon/customer API budget stays (abuse shield).
    - Static assets use a SEPARATE higher bucket (not an exemption).
    - Human HTML page navigation (GET/HEAD on /app/*, /pricing, /start,
      /voice-agent) uses its own higher bucket — multi-tab dashboard browsing
      bursts must not trip the shared API budget (2026-08-02 429 burst).
    - Valid admin/super_admin bearer gets a raised ceiling ONLY on explicit
      safe idempotent dashboard GET/HEAD paths — writes stay on default rpm.
    - Auth credential routes stay under this global limiter (no prefix bypass);
      route ``rate_limit`` deps remain defense-in-depth with the SAME trusted IP.
    - Only WebSocket upgrades + narrow realtime web-call WS/stream prefixes skip;
      telephony provider actions (test-call/stream-call) remain globally limited.
    """

    # Exact health/probe paths — never burn operator budget on liveness.
    _SKIP_EXACT = frozenset({"/health", "/health/live", "/health/ready", "/metrics", "/status"})
    # Narrow realtime allowlist only — NOT /api/telephony/* (outbound actions).
    _SKIP_PREFIXES = (
        "/ws",
        "/api/web-call/ws",
        "/api/web-call/stream",
        "/robots.txt",
        "/sitemap.xml",
    )

    def __init__(
        self,
        app: FastAPI,
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
    ):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self._limiters: dict = {}
        self._fallback_counts: dict = {}  # Fallback for when Redis unavailable

    def _should_skip(self, request: Request) -> bool:
        if request.headers.get("upgrade", "").lower() == "websocket":
            return True
        path = request.url.path or ""
        if path in self._SKIP_EXACT:
            return True
        if any(
            path == p or path.startswith(p if p.endswith("/") else p + "/")
            for p in self._SKIP_PREFIXES
        ):
            return True
        return False

    def _admin_rpm_from_bearer(self, request: Request) -> int | None:
        """Valid admin/super_admin JWT → raised READ ceiling (still capped).

        Only consulted for safe GET/HEAD dashboard paths via ``_bucket_for``.
        Default 600 rpm (~10 req/s); override via RATE_LIMIT_ADMIN_RPM.
        Invalid/missing token → None (anon/default budget).
        """
        auth = (request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            import jwt

            from app.api.admin import JWT_ALGORITHM, JWT_SECRET

            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                return None
            role = str(payload.get("role") or "").lower()
            if role not in ("admin", "super_admin"):
                return None
        except (ImportError, AttributeError, KeyError) as _e:
            logger.debug("RateLimitMiddleware admin bearer parse skipped: %s", _e)
            return None
        except Exception as _e:
            logger.debug("RateLimitMiddleware admin bearer parse error: %s", _e)
            return None
        try:
            return max(1, int(os.environ.get("RATE_LIMIT_ADMIN_RPM", "600")))
        except ValueError:
            return 600

    def _ceiling_for(self, bucket: str) -> int:
        """Per-minute ceiling for a bucket. Read at call time so a runtime
        change to `requests_per_minute` keeps the asset ceiling proportional."""
        if bucket == "api_admin":
            try:
                return max(1, int(os.environ.get("RATE_LIMIT_ADMIN_RPM", "600")))
            except ValueError:
                return 600
        if bucket == "html":
            try:
                mult = int(os.environ.get("RATE_LIMIT_HTML_MULT", "10"))
            except ValueError:
                mult = 10
            return self.requests_per_minute * max(1, mult)
        if bucket != "asset":
            return self.requests_per_minute
        try:
            mult = int(os.environ.get("RATE_LIMIT_ASSET_MULT", "5"))
        except ValueError:
            mult = 5
        return self.requests_per_minute * max(1, mult)

    def _bucket_for(self, request: Request) -> tuple[str, int]:
        path = request.url.path or ""
        if _is_asset_path(path):
            return "asset", self._ceiling_for("asset")
        # Human HTML navigation burst (multi-tab browse) — separate higher bucket.
        if _is_html_navigation(request):
            return "html", self._ceiling_for("html")
        # Higher admin budget is GET/HEAD dashboard relief only — never writes.
        if _is_safe_idempotent_admin_read(request):
            admin_rpm = self._admin_rpm_from_bearer(request)
            if admin_rpm is not None:
                return "api_admin", admin_rpm
        return "api", self._ceiling_for("api")

    async def _get_limiter(self, bucket: str = "api"):
        """Get or create the Redis rate limiter for a bucket."""
        ceiling = self._ceiling_for(bucket)
        existing = self._limiters.get(bucket)
        if existing is not None:
            # Keep cached limiter's cap in sync with runtime ceiling knobs.
            try:
                existing.max_requests = ceiling
            except AttributeError:
                pass
            return existing
        try:
            from app.cache import RateLimiter

            limiter = RateLimiter(
                prefix=f"ratelimit:{bucket}",
                max_requests=ceiling,
                window_seconds=60,
            )
            self._limiters[bucket] = limiter
            return limiter
        except Exception as e:
            logger.warning(f"Could not initialize Redis rate limiter: {e}")
            return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if self._should_skip(request):
            return await call_next(request)

        client_ip = _real_client_ip(request)
        bucket, ceiling = self._bucket_for(request)

        # Try Redis rate limiter first. Only the limiter call is guarded — a
        # downstream failure inside call_next used to be caught here too, which
        # dropped through to the in-memory fallback and ran the SAME request a
        # second time. On a POST that is a silent duplicate write.
        limiter = await self._get_limiter(bucket)
        allowed, remaining, limiter_ok = True, 0, False
        if limiter:
            try:
                allowed, remaining = await limiter.is_allowed(client_ip)
                limiter_ok = True
            except Exception as e:
                logger.warning(f"Redis rate limiter failed, using fallback: {e}")

        if limiter_ok:
            if not allowed:
                logger.warning(f"Rate limit exceeded for {client_ip} (bucket={bucket})")
                return _rate_limit_429(
                    retry_after=_fixed_window_retry_after(60),
                    scope=f"global_ip_{bucket}",
                    limit=ceiling,
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(ceiling)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            return response

        # Fallback to in-memory rate limiting
        current_minute = int(time.time() / 60)
        key = f"{bucket}:{client_ip}:{current_minute}"

        if key not in self._fallback_counts:
            self._fallback_counts[key] = 0

        self._fallback_counts[key] += 1

        if self._fallback_counts[key] > ceiling:
            logger.warning(f"Rate limit exceeded for {client_ip} (fallback, bucket={bucket})")
            return _rate_limit_429(
                retry_after=_fixed_window_retry_after(60),
                scope=f"global_ip_{bucket}",
                limit=ceiling,
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
        "/status",
        "/robots.txt",
        "/sitemap.xml",
    )
    # No broad auth/telephony skip — provider actions + credential writes stay limited.
    _APP_HTML_PREFIX = "/app/"

    def _should_skip(self, path: str) -> bool:
        if any(path == p or path.startswith(p + "/") for p in self._SKIP):
            return True
        # Plan limits = API abuse guard; static /app/* HTML pages never 429 here.
        if path.startswith(self._APP_HTML_PREFIX):
            return True
        return False

    def _rpm_from_bearer(self, request: Request) -> int | None:
        """Valid admin JWT → elevated tier ONLY for safe GET/HEAD dashboard reads."""
        auth = (request.headers.get("authorization") or "").strip()
        if not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        try:
            import jwt

            from app.api.admin import JWT_ALGORITHM, JWT_SECRET

            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") != "access":
                return None
            role = str(payload.get("role") or "").lower()
            if role in ("admin", "super_admin"):
                if not _is_safe_idempotent_admin_read(request):
                    return None  # writes / non-allowlisted → plan/default rpm
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
            # Same fixed-minute window as the flat limiter, so the same real
            # reset applies — and the same uniform detail dict every FE parses.
            retry_after = _fixed_window_retry_after(60)
            return JSONResponse(
                status_code=429,
                content={
                    "detail": {
                        "error": "rate_limited",
                        "message": (
                            f"Plan rate limit ({rpm} req/min) exceeded. "
                            "Upgrade plan for higher limits."
                        ),
                        "retry_after": retry_after,
                        "scope": "plan_tier",
                        "limit_rpm": rpm,
                        "plan": plan or "anon",
                    },
                    "limit_rpm": rpm,
                    "plan": plan or "anon",
                    "retry_after": retry_after,
                },
                headers={
                    "Retry-After": str(retry_after),
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
        # to the raw path when no route matched (404s etc.). Never touch `.path`
        # on a FastAPI `_IncludedRouter` (AttributeError masks the real failure
        # in Sentry — 2026-07-14).
        try:
            route = request.scope.get("route")
            if route is not None:
                tmpl = getattr(route, "path_format", None)
                if tmpl:
                    return str(tmpl)
                # Some Starlette routes expose `.path`; lazy include wrappers do not.
                if type(route).__name__ != "_IncludedRouter":
                    plain = getattr(route, "path", None)
                    if plain:
                        return str(plain)
        except Exception as _e:
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

    # Tenant context REMOVED 2026-08-01 (enterprise-audit fix): TenantContextMiddleware
    # client-supplied `X-Tenant-ID` header ko request.state.tenant_id me daal raha tha
    # bina kisi validation/consumption ke (write-only trust-by-header landmine) — future
    # code isko scoping ke liye use karta to instant cross-tenant hole ban jata. Real
    # tenant scoping per-route JWT `client_id` + store-layer ownership checks hai.
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
