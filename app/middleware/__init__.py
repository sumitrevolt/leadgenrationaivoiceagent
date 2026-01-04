"""
Production Middleware Stack
Rate limiting, security headers, API authentication, and request tracing
"""
import time
import uuid
from typing import Callable, Optional
from functools import wraps

from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.security import APIKeyHeader, HTTPBearer
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# SECURITY HEADERS MIDDLEWARE
# =============================================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
        
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
            f"Request started",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "client_ip": request.client.host if request.client else "unknown",
            }
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
                f"Request completed",
                extra={
                    "request_id": request_id,
                    "status_code": response.status_code,
                    "duration_ms": int(duration * 1000),
                }
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
                }
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
        
        client_ip = request.client.host if request.client else "unknown"
        
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
            old_keys = [
                k for k in self._fallback_counts.keys()
                if int(k.split(":")[1]) < current_minute - 5
            ]
            for k in old_keys:
                del self._fallback_counts[k]
        
        return await call_next(request)


# =============================================================================
# API KEY AUTHENTICATION
# =============================================================================

API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: Optional[str] = Depends(API_KEY_HEADER)) -> Optional[dict]:
    """
    Verify API key and return client info
    """
    if not api_key:
        return None
    
    # In production, lookup API key in database
    # For now, check against configured keys
    if api_key == settings.secret_key:
        return {"client": "admin", "permissions": ["all"]}
    
    # Could also check tenant API keys here
    # from app.models.client import Client
    # client = await get_client_by_api_key(api_key)
    
    return None


def require_api_key(permissions: list = None):
    """
    Decorator to require API key authentication
    """
    async def dependency(
        request: Request,
        client: Optional[dict] = Depends(verify_api_key)
    ):
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
# SETUP ALL MIDDLEWARE
# =============================================================================

def setup_middleware(app: FastAPI, production: bool = False):
    """
    Configure all middleware for the application
    Order matters: last added = first executed
    """
    
    # Compression (applied last, so compressed first)
    add_gzip_middleware(app)
    
    # Tenant context
    app.add_middleware(TenantContextMiddleware)
    
    # Rate limiting
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
    
    logger.info(f"? Middleware stack configured (production={production})")
