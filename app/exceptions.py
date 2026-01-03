"""
Exception Handlers and Custom Exceptions
Centralized error handling for the platform
"""
from typing import Optional, Any, Dict
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
import traceback

from app.config import settings
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================

class LeadGenException(Exception):
    """Base exception for the platform"""
    
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class ValidationException(LeadGenException):
    """Validation error"""
    
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(
            message=message,
            code="VALIDATION_ERROR",
            status_code=422,
            details={"field": field} if field else {},
        )


class AuthenticationException(LeadGenException):
    """Authentication error"""
    
    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            status_code=401,
        )


class AuthorizationException(LeadGenException):
    """Authorization error"""
    
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message=message,
            code="AUTHORIZATION_ERROR",
            status_code=403,
        )


class ResourceNotFoundException(LeadGenException):
    """Resource not found"""
    
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            message=f"{resource} not found: {identifier}",
            code="NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": identifier},
        )


class RateLimitException(LeadGenException):
    """Rate limit exceeded"""
    
    def __init__(self, retry_after: int = 60):
        super().__init__(
            message="Rate limit exceeded. Please try again later.",
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details={"retry_after": retry_after},
        )


class TelephonyException(LeadGenException):
    """Telephony provider error"""
    
    def __init__(self, message: str, provider: str):
        super().__init__(
            message=message,
            code="TELEPHONY_ERROR",
            status_code=502,
            details={"provider": provider},
        )


class LLMException(LeadGenException):
    """LLM provider error"""
    
    def __init__(self, message: str, provider: str):
        super().__init__(
            message=message,
            code="LLM_ERROR",
            status_code=502,
            details={"provider": provider},
        )


class ScrapingException(LeadGenException):
    """Scraping error"""
    
    def __init__(self, message: str, source: str):
        super().__init__(
            message=message,
            code="SCRAPING_ERROR",
            status_code=502,
            details={"source": source},
        )


class QuotaExceededException(LeadGenException):
    """Quota exceeded"""
    
    def __init__(self, resource: str, limit: int, current: int):
        super().__init__(
            message=f"{resource} quota exceeded: {current}/{limit}",
            code="QUOTA_EXCEEDED",
            status_code=429,
            details={
                "resource": resource,
                "limit": limit,
                "current": current,
            },
        )


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

async def leadgen_exception_handler(
    request: Request,
    exc: LeadGenException,
) -> JSONResponse:
    """Handle custom LeadGen exceptions"""
    
    request_id = getattr(request.state, "request_id", "unknown")
    
    logger.error(
        f"LeadGen exception: {exc.code} - {exc.message}",
        extra={
            "request_id": request_id,
            "code": exc.code,
            "status_code": exc.status_code,
            "details": exc.details,
        },
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


async def http_exception_handler(
    request: Request,
    exc: HTTPException,
) -> JSONResponse:
    """Handle FastAPI HTTP exceptions"""
    
    request_id = getattr(request.state, "request_id", "unknown")
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": f"HTTP_{exc.status_code}",
                "message": exc.detail,
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle validation errors"""
    
    request_id = getattr(request.state, "request_id", "unknown")
    
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field,
            "message": error["msg"],
            "type": error["type"],
        })
    
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "details": {"errors": errors},
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions"""
    
    request_id = getattr(request.state, "request_id", "unknown")
    
    # Log full traceback
    logger.error(
        f"Unhandled exception: {str(exc)}",
        extra={
            "request_id": request_id,
            "traceback": traceback.format_exc(),
        },
    )
    
    # In production, don't expose internal errors
    if settings.app_env == "production":
        message = "An unexpected error occurred. Please try again later."
        details = {}
    else:
        message = str(exc)
        details = {"traceback": traceback.format_exc().split("\n")}
    
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": message,
                "details": details,
                "request_id": request_id,
            }
        },
        headers={"X-Request-ID": request_id},
    )


# =============================================================================
# SETUP EXCEPTION HANDLERS
# =============================================================================

def setup_exception_handlers(app: FastAPI):
    """Register all exception handlers"""
    
    app.add_exception_handler(LeadGenException, leadgen_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
    
    logger.info("? Exception handlers configured")
