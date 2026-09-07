"""
Authentication Dependencies
Centralized authentication for all API endpoints
"""

import hmac

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.base import get_async_db
from app.models.user import User, UserRole, UserStatus
from app.utils.jwt_versioning import get_jwt_manager
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
security = HTTPBearer(auto_error=False)  # auto_error=False allows optional auth

# JWT Configuration
# settings.jwt_secret_key is loaded from env/.env by pydantic-settings —
# os.environ.get() would miss values that only exist in the .env file.
JWT_SECRET = settings.jwt_secret_key
JWT_ALGORITHM = settings.jwt_algorithm


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    try:
        # SECURITY FIX (P0-5, 2026-07-19): Use JWT key manager for key versioning
        jwt_mgr = get_jwt_manager(JWT_SECRET, JWT_ALGORITHM)
        payload = jwt_mgr.decode(token)
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_db),
) -> User:
    """
    Get current authenticated user from JWT token
    Raises 401 if not authenticated
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token payload")

        # Get user from database
        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(status_code=401, detail="User not found")

        if user.status == UserStatus.SUSPENDED:
            raise HTTPException(status_code=403, detail="Account suspended")

        if user.status == UserStatus.INACTIVE:
            raise HTTPException(status_code=403, detail="Account inactive")

        # Tier-1 Slice C: server-side JWT session revocation (logout / password reset /
        # disable / role change / suspected compromise). Fail-CLOSED for admin-tier tokens
        # so a Redis blip can't let a possibly-revoked admin token through; fail-OPEN for
        # lower tiers to preserve availability. Customer auth (require_customer) is separate.
        from app.platform import admin_sessions

        _high_risk = user.role in (UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER)
        if await admin_sessions.is_revoked(payload, fail_closed=_high_risk):
            raise HTTPException(status_code=401, detail="Session has been revoked")

        return user

    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


async def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_db),
) -> User | None:
    """
    Get current user if authenticated, None otherwise
    Use for endpoints that support both authenticated and unauthenticated access
    """
    if not credentials:
        return None

    try:
        return await get_current_user(credentials, db)
    except HTTPException:
        return None


async def require_admin(request: Request, user: User = Depends(get_current_user)) -> User:
    """Admin access: super_admin/admin = full pass; manager/agent/viewer = sirf
    apne GRANTED module ke paths (rbac.MODULES, preferences JSON me grants —
    docs/ADMIN_RBAC_DESIGN.md). Unmapped path member ke liye 403 (fail-closed)."""
    if user.can_access_admin():
        return user
    try:
        from app.platform import rbac

        if rbac.member_can_access(user, request.url.path):
            return user
    except Exception:
        pass  # rbac issue = fail-closed (sirf admin+ pass)
    raise HTTPException(status_code=403, detail="Admin access required (ya module grant missing)")


# ── OPS-008: read-only ops API key ──────────────────────────────────
# Why: every day-close has been BLIND because ops truth endpoints require a JWT
# admin session and no read-only token existed. This adds a narrowly scoped key
# that unlocks REVENUE MEASUREMENT only.
#
# Invariants (do NOT loosen):
#   * Empty/unsed token  -> key path disabled entirely (fail-closed).
#   * GET only, and only for the exact (method, path) pairs below.
#   * /api/ops/hotqueue/action and every mutation are NOT in the allowlist, so
#     they always fall through to the full admin path.
#   * Constant-time comparison.
OPS_READONLY_ALLOWLIST: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/api/ops/revenue-summary"),
        ("GET", "/api/ops/hotqueue"),
    }
)


def _ops_readonly_allows(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> bool:
    """True only when a configured ops key is presented for an allowed GET path."""
    token = (getattr(settings, "ops_readonly_token", "") or "").strip()
    if not token:
        return False  # not armed => disabled (fail-closed)

    if (request.method.upper(), (request.url.path or "").rstrip("/")) not in OPS_READONLY_ALLOWLIST:
        return False

    if not credentials:
        return False
    provided = (credentials.credentials or "").strip()
    if not provided:
        return False
    return hmac.compare_digest(provided, token)


async def require_admin_or_ops_readonly(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    db: AsyncSession = Depends(get_async_db),
):
    """Admin (JWT) OR the read-only ops API key.

    Ops key is honoured ONLY for OPS_READONLY_ALLOWLIST GET endpoints; every
    other path/method falls through to the unchanged admin path. Returns the
    admin User, or None when the read-only key was used.
    """
    if _ops_readonly_allows(request, credentials):
        logger.info(f"ops-readonly key used for {request.method} {request.url.path}")
        return None
    user = await get_current_user(credentials, db)
    return await require_admin(request, user)


async def require_super_admin(user: User = Depends(get_current_user)) -> User:
    """Require super admin role"""
    if user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Super admin access required")
    return user


async def require_manager(user: User = Depends(get_current_user)) -> User:
    """Require manager, admin or super_admin role"""
    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER]
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Manager access required")
    return user


async def require_agent(user: User = Depends(get_current_user)) -> User:
    """Require at least agent role"""
    allowed_roles = [UserRole.SUPER_ADMIN, UserRole.ADMIN, UserRole.MANAGER, UserRole.AGENT]
    if user.role not in allowed_roles:
        raise HTTPException(status_code=403, detail="Agent access required")
    return user


def require_permission(permission: str):
    """
    Decorator factory for requiring specific permissions
    Usage: @router.get("/endpoint", dependencies=[Depends(require_permission("manage_campaigns"))])
    """

    async def permission_checker(user: User = Depends(get_current_user)):
        if not user.has_permission(permission):
            raise HTTPException(status_code=403, detail=f"Permission denied: {permission} required")
        return user

    return permission_checker


async def require_customer(*args, **kwargs):
    """
    Import-safe shim for require_customer (lives in app.api.customer_auth).
    Some legacy/generated code imports it from here.
    """
    from app.api.customer_auth import require_customer as _real

    return await _real(*args, **kwargs)


# NOTE: Webhook signature verification (Stripe) lives in app.api.webhooks with
# real HMAC checks. The always-True stubs that used to live here were removed
# so nobody accidentally imports a no-op verifier. (Twilio verifier removed
# 2026-07-07 — telephony provider is Vobiz-only, which doesn't sign callbacks.)
