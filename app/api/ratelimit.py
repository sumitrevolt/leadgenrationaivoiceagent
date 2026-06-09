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
    """Real client IP — proxy headers first (Caddy), warna socket peer."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    xri = request.headers.get("x-real-ip")
    if xri:
        return xri.strip()
    return request.client.host if request.client else "unknown"


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
            raise HTTPException(
                status_code=429,
                detail="Bahut zyada requests — thodi der baad try karo.",
                headers={"Retry-After": str(window_seconds)},
            )

    return _dep


__all__ = ["rate_limit"]
