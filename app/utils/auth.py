"""
JWT Authentication Service
Production-ready authentication with JWT tokens
"""
import secrets
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Tuple
from jose import JWTError, jwt
from fastapi import HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Security
security = HTTPBearer()


class TokenPayload(BaseModel):
    """JWT token payload"""
    sub: str  # user_id
    email: str
    role: str
    exp: datetime
    iat: datetime
    jti: str  # unique token id


class TokenPair(BaseModel):
    """Access and refresh token pair"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


def create_access_token(
    user_id: str,
    email: str,
    role: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT access token
    
    Args:
        user_id: User's unique ID
        email: User's email
        role: User's role
        expires_delta: Custom expiration time
        
    Returns:
        Encoded JWT token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_access_token_expire_minutes)
    
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": secrets.token_urlsafe(16),
        "type": "access"
    }
    
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Create JWT refresh token
    
    Args:
        user_id: User's unique ID
        expires_delta: Custom expiration time
        
    Returns:
        Encoded JWT refresh token
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(days=settings.jwt_refresh_token_expire_days)
    
    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": datetime.utcnow(),
        "jti": secrets.token_urlsafe(16),
        "type": "refresh"
    }
    
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_token_pair(
    user_id: str,
    email: str,
    role: str
) -> TokenPair:
    """
    Create access and refresh token pair
    
    Args:
        user_id: User's unique ID
        email: User's email
        role: User's role
        
    Returns:
        TokenPair with both tokens
    """
    access_token = create_access_token(user_id, email, role)
    refresh_token = create_refresh_token(user_id)
    
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60
    )


def verify_token(token: str, token_type: str = "access") -> Optional[dict]:
    """
    Verify and decode JWT token
    
    Args:
        token: JWT token string
        token_type: Expected token type (access/refresh)
        
    Returns:
        Decoded payload or None if invalid
    """
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm]
        )
        
        # Verify token type
        if payload.get("type") != token_type:
            logger.warning(f"Token type mismatch: expected {token_type}, got {payload.get('type')}")
            return None
        
        # Verify expiration
        exp = payload.get("exp")
        if exp and datetime.utcfromtimestamp(exp) < datetime.utcnow():
            logger.warning("Token expired")
            return None
        
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None


def refresh_access_token(refresh_token: str, email: str, role: str) -> Optional[str]:
    """
    Create new access token from refresh token
    
    Args:
        refresh_token: Valid refresh token
        email: User's email
        role: User's role
        
    Returns:
        New access token or None if refresh token invalid
    """
    payload = verify_token(refresh_token, token_type="refresh")
    if not payload:
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        return None
    
    return create_access_token(user_id, email, role)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> str:
    """
    FastAPI dependency to get current user ID from token
    
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return payload.get("sub")


async def get_current_user_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    """
    FastAPI dependency to get full token payload
    
    Raises:
        HTTPException: If token is invalid
    """
    token = credentials.credentials
    payload = verify_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return payload


def require_role(*allowed_roles: str):
    """
    Dependency factory to require specific roles
    
    Usage:
        @router.get("/admin-only")
        async def admin_route(user = Depends(require_role("super_admin", "admin"))):
            ...
    """
    async def role_checker(payload: dict = Depends(get_current_user_payload)) -> dict:
        user_role = payload.get("role")
        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user_role}' not authorized for this action"
            )
        return payload
    
    return role_checker


def hash_password(password: str, salt: Optional[str] = None) -> Tuple[str, str]:
    """
    Hash password with salt using SHA-256
    
    Args:
        password: Plain text password
        salt: Optional salt (generated if not provided)
        
    Returns:
        Tuple of (hash, salt)
    """
    if salt is None:
        salt = secrets.token_hex(32)
    
    combined = f"{password}{salt}".encode('utf-8')
    password_hash = hashlib.sha256(combined).hexdigest()
    
    return password_hash, salt


def verify_password(password: str, stored_hash: str, salt: str) -> bool:
    """
    Verify password against stored hash
    
    Args:
        password: Plain text password to verify
        stored_hash: Stored password hash
        salt: Salt used for hashing
        
    Returns:
        True if password matches
    """
    computed_hash, _ = hash_password(password, salt)
    return secrets.compare_digest(computed_hash, stored_hash)


def generate_api_key() -> str:
    """Generate a secure API key for clients"""
    return f"ak_{secrets.token_urlsafe(32)}"


def generate_verification_token() -> str:
    """Generate email verification token"""
    return secrets.token_urlsafe(32)


def generate_password_reset_token() -> str:
    """Generate password reset token"""
    return secrets.token_urlsafe(32)


# Rate limiting helper
class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: dict = {}  # {ip: [(timestamp, count)]}
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed"""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        # Clean old entries
        if identifier in self.requests:
            self.requests[identifier] = [
                (ts, count) for ts, count in self.requests[identifier]
                if ts > window_start
            ]
        
        # Count requests in window
        request_count = sum(
            count for _, count in self.requests.get(identifier, [])
        )
        
        if request_count >= self.max_requests:
            return False
        
        # Record request
        if identifier not in self.requests:
            self.requests[identifier] = []
        self.requests[identifier].append((now, 1))
        
        return True
    
    def get_remaining(self, identifier: str) -> int:
        """Get remaining requests for identifier"""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window_seconds)
        
        if identifier not in self.requests:
            return self.max_requests
        
        request_count = sum(
            count for ts, count in self.requests[identifier]
            if ts > window_start
        )
        
        return max(0, self.max_requests - request_count)


# Global rate limiter
rate_limiter = RateLimiter(
    max_requests=settings.rate_limit_per_minute,
    window_seconds=60
)


async def check_rate_limit(request: Request):
    """FastAPI dependency to check rate limit"""
    client_ip = request.client.host if request.client else "unknown"
    
    if not rate_limiter.is_allowed(client_ip):
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again later.",
            headers={
                "Retry-After": "60",
                "X-RateLimit-Remaining": "0"
            }
        )
    
    return True
