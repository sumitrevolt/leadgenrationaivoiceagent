"""Lightweight per-IP rate-limit dependency (reuses app.cache.RateLimiter).

Kyun: AI/LLM aur public inbound endpoints pe koi auth nahi tha → ek script
spam karke free-LLM cost/abuse kar sakti thi. Yeh dependency per-IP sliding
window se requests cap karti hai.

Design:
- **FAIL-OPEN**: limiter/Redis error ho to request BLOCK nahi hoti (legit
  traffic kabhi na ruke) — sirf abuse rokna hai, availability todna nahi.
- Caddy reverse-proxy ke peeche real client IP `X-Forwarded-For`/`X-Real-IP`
  se aata hai (warna sab 127.0.0.1 share karte = ek saath limit).
- Redis ho to distributed; warna RateLimiter ka in-memory fallback.

Use:
    from app.api.ratelimit import rate_limit
    router = APIRouter(dependencies=[Depends(rate_limit("ai", 30, 60))])
    # ya per-route:
    @router.post("/x", dependencies=[Depends(rate_limit("tools", 20, 60))])
"""

from __future__ import annotations

from fastapi import HTTPException, Request

from app.cache import RateLimiter
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _client_ip(request: Request) -> str:
    """Canonical trusted client IP — MUST match ``app.middleware._real_client_ip``.

    SECURITY: rightmost X-Forwarded-For only. Leftmost is client-spoofable
    (CWE-20). Lazy import avoids any future circular import with middleware.
    """
    from app.middleware import _real_client_ip

    return _real_client_ip(request)


def rate_limit(prefix: str, max_requests: int = 30, window_seconds: int = 60):
    """FastAPI dependency factory — per-IP rate limit for a route/router.

    Args:
        prefix: bucket name (alag endpoints ka alag budget, e.g. "ai", "tools").
        max_requests: window me allowed requests per IP.
        window_seconds: window length.

    429 raise hoti hai jab IP limit cross kare. Limiter error = fail-open.
    """
    limiter = RateLimiter(
        prefix=f"rl:{prefix}", max_requests=max_requests, window_seconds=window_seconds
    )

    async def _dep(request: Request) -> None:
        try:
            ident = _client_ip(request)
            allowed, _remaining = await limiter.is_allowed(ident)
        except Exception as exc:  # pragma: no cover - defensive fail-open
            logger.debug("rate_limit fail-open (%s): %s", prefix, exc)
            return
        if not allowed:
            # Loop 16 (2026-07-10): structured 429 detail (Loop 6 pattern) so any
            # FE can render a countdown / distinguish "rate_limited" from other
            # 4xx across every endpoint that uses this dep. Backward-compat: a
            # `message` field preserves the human string old callers displayed.
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": "Bahut zyada requests — thodi der baad try karo.",
                    "retry_after": int(window_seconds),
                    "scope": prefix,
                },
                headers={"Retry-After": str(window_seconds)},
            )

    return _dep


# --------------------------------------------------------------------------- #
# Tier-aware rate limiting (R1#1) — per client-tier budget. Higher tiers = more
# headroom. Tier resolve hota hai: request.state.tenant (server-derived) → default
# "free" — client-supplied header REMOVED 2026-07-01 (self-report spoofing risk,
# see _client_tier docstring). Base limit ko tier-multiplier se scale karte.
# FAIL-OPEN, additive (existing rate_limit untouched). Routes opt-in karein:
#   dependencies=[Depends(tier_rate_limit("ai", base_max=20, window=60))]
# --------------------------------------------------------------------------- #
_TIER_MULT: dict[str, float] = {
    "free": 1.0,
    "trial": 1.0,
    "starter": 2.0,
    "growth": 4.0,
    "advanced": 8.0,
    "voice": 8.0,
    "admin": 20.0,
}


def _client_tier(request: Request) -> str:
    """Requester ka tier — server-derived tenant state only, never 'free'.

    A client-supplied X-Client-Tier header was previously trusted here (checked
    before the tenant state) — any caller could self-report "admin" for a 20x
    rate-limit budget. Header is never set anywhere in this codebase (grepped),
    so there was no legitimate internal use to preserve. Removed entirely
    (production audit 2026-07-01, security batch 4). Never-raise.
    """
    try:
        tenant = getattr(request.state, "tenant", None)
        if tenant:
            t = str(
                (tenant.get("plan") if isinstance(tenant, dict) else getattr(tenant, "plan", ""))
                or ""
            ).lower()
            for key in _TIER_MULT:
                if key in t:
                    return key
    except Exception:
        pass
    return "free"


def tier_rate_limit(prefix: str, base_max: int = 20, window_seconds: int = 60):
    """Tier-scaled per-IP rate limit. base_max = free-tier budget; higher tiers
    proportionally zyada. Alag tier = alag bucket (taaki ek tier dusre ko na affect kare)."""

    async def _dep(request: Request) -> None:
        try:
            tier = _client_tier(request)
            cap = max(1, int(base_max * _TIER_MULT.get(tier, 1.0)))
            limiter = RateLimiter(
                prefix=f"rl:{prefix}:{tier}", max_requests=cap, window_seconds=window_seconds
            )
            ident = _client_ip(request)
            allowed, _rem = await limiter.is_allowed(ident)
        except Exception as exc:  # defensive fail-open
            logger.debug("tier_rate_limit fail-open (%s): %s", prefix, exc)
            return
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limited",
                    "message": "Bahut zyada requests — thodi der baad try karo (ya plan upgrade).",
                    "retry_after": int(window_seconds),
                    "scope": prefix,
                    "tier": tier,
                },
                headers={"Retry-After": str(window_seconds)},
            )

    return _dep


__all__ = ["rate_limit", "tier_rate_limit"]
