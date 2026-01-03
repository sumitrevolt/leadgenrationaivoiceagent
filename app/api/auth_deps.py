"""
Authentication Dependencies
Centralized authentication for all API endpoints
"""
from typing import Optional
from datetime import datetime
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from jose import jwt, JWTError
import os

from app.models.user import User, UserRole, UserStatus
from app.models.base import get_async_db
from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
security = HTTPBearer(auto_error=False)  # auto_error=False allows optional auth

# JWT Configuration
JWT_SECRET = os.environ.get("JWT_SECRET_KEY", settings.secret_key)
JWT_ALGORITHM = "HS256"


def decode_token(token: str) -> dict:
    """Decode and validate JWT token"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_async_db)
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
        result = await db.execute(
            select(User).where(User.id == user_id)
        )
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
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: AsyncSession = Depends(get_async_db)
) -> Optional[User]:
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
            raise HTTPException(
                status_code=403, 
                detail=f"Permission denied: {permission} required"
            )
        return user
    return permission_checker


# Webhook authentication (for external services like Twilio)
async def verify_twilio_signature(request_data: dict, signature: str) -> bool:
    """Verify Twilio webhook signature"""
    # In production, implement proper Twilio signature verification
    # https://www.twilio.com/docs/usage/security#validating-requests
    import hmac
    import hashlib
    
    auth_token = os.environ.get("TWILIO_AUTH_TOKEN", "")
    if not auth_token:
        logger.warning("TWILIO_AUTH_TOKEN not set, skipping signature verification")
        return True  # Allow in development
    
    # Implement actual verification here
    return True


async def verify_exotel_signature(request_data: dict, signature: str) -> bool:
    """Verify Exotel webhook signature"""
    # Implement Exotel signature verification
    api_key = os.environ.get("EXOTEL_API_KEY", "")
    if not api_key:
        logger.warning("EXOTEL_API_KEY not set, skipping signature verification")
        return True  # Allow in development
    
    return True
