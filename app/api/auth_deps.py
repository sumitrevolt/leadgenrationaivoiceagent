"""
Authentication Dependencies
Centralized authentication for all API endpoints
"""

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.base import get_async_db
from app.models.user import User, UserRole, UserStatus
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
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
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


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require admin role (admin or super_admin)"""
    if not user.can_access_admin():
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


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


# NOTE: Webhook signature verification lives in app.api.webhooks
# (verify_twilio_signature / verify_exotel_signature with real HMAC checks).
# The always-True stubs that used to live here were removed so nobody
# accidentally imports a no-op verifier.
