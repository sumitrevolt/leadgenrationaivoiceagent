"""Tier-1 Slice C — server-side admin JWT session revocation (Redis-backed).

Access tokens are stateless, so a plain logout cannot invalidate them. This adds two
Redis revocation mechanisms so a token can be killed before its natural expiry:

  * ``revoke_jti(jti, ttl)``         — blacklist ONE token (single-session logout /
                                       suspected-compromise of a specific token).
  * ``revoke_all_for_user(user_id)`` — bump ``authrev:user:{id}`` to now; every token
                                       with ``iat < epoch`` is then rejected
                                       (password reset, disable, role change, 2FA reset).

``is_revoked(payload, fail_closed=...)`` is called from ``get_current_user``:
  - **fail-CLOSED** for admin-tier tokens (super/admin/manager) → if Redis can't be
    reached we raise 503 rather than trust a possibly-revoked admin token.
  - **fail-OPEN** for lower tiers → a Redis blip doesn't lock everyone out.

Customer auth is a separate dependency (``require_customer``) with its own blacklist and
is intentionally untouched here.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_JTI_PREFIX = "authrev:jti:"
_USER_EPOCH_PREFIX = "authrev:user:"
# Epoch key must outlive any refresh token so a revoked user can't ride an old token.
_EPOCH_TTL = int(os.getenv("ADMIN_SESSION_REVOKE_TTL", str(30 * 24 * 3600)))  # 30d
# Default jti blacklist TTL (callers pass exact remaining token life where known).
_JTI_TTL = int(os.getenv("ADMIN_SESSION_JTI_TTL", str(24 * 3600)))  # 24h


async def _redis():
    from app.cache import get_redis_client

    return await get_redis_client()


def _iat_ts(iat: Any) -> int | None:
    """Normalize a JWT `iat` claim (unix int, float, or datetime) to unix seconds."""
    if iat is None:
        return None
    if isinstance(iat, int | float):
        return int(iat)
    if isinstance(iat, datetime):
        # JWT times are UTC; treat a naive datetime as UTC so .timestamp() isn't
        # reinterpreted in the host's local timezone.
        if iat.tzinfo is None:
            iat = iat.replace(tzinfo=timezone.utc)
        return int(iat.timestamp())
    try:
        return int(float(iat))
    except Exception:
        return None


async def revoke_jti(jti: str | None, ttl: int | None = None) -> bool:
    if not jti:
        return False
    try:
        r = await _redis()
        await r.setex(f"{_JTI_PREFIX}{jti}", int(ttl or _JTI_TTL), "1")
        return True
    except Exception as e:
        logger.warning("admin_sessions.revoke_jti failed jti=%s err=%s", str(jti)[:8], e)
        return False


async def revoke_all_for_user(user_id: str | None, reason: str = "admin_action") -> bool:
    """Invalidate every existing token for a user (epoch bump). Idempotent."""
    if not user_id:
        return False
    try:
        r = await _redis()
        await r.setex(f"{_USER_EPOCH_PREFIX}{user_id}", _EPOCH_TTL, str(int(time.time())))
        logger.info("admin_sessions.revoke_all_for_user user=%s reason=%s", user_id, reason)
        return True
    except Exception as e:
        logger.warning("admin_sessions.revoke_all_for_user failed user=%s err=%s", user_id, e)
        return False


async def is_revoked(payload: dict, *, fail_closed: bool = False) -> bool:
    """True if this access token has been revoked (jti blacklisted or iat < user epoch).

    On Redis error: raise HTTP 503 when ``fail_closed`` (high-risk admin surface), else
    return False (fail-open) so a transient cache blip doesn't lock lower-tier users out.
    """
    jti = payload.get("jti")
    sub = payload.get("sub")
    try:
        r = await _redis()
        if jti and await r.exists(f"{_JTI_PREFIX}{jti}"):
            return True
        if sub:
            epoch_raw = await r.get(f"{_USER_EPOCH_PREFIX}{sub}")
            if epoch_raw is not None:
                epoch = int(epoch_raw.decode() if isinstance(epoch_raw, bytes) else epoch_raw)
                iat_ts = _iat_ts(payload.get("iat"))
                if iat_ts is not None and iat_ts < epoch:
                    return True
        return False
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(
            "admin_sessions.is_revoked check failed sub=%s fail_closed=%s err=%s",
            sub,
            fail_closed,
            e,
        )
        if fail_closed:
            raise HTTPException(status_code=503, detail="session revocation store unavailable")
        return False
