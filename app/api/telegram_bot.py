"""FastAPI Endpoints for Telegram Bot Management.

Provides REST API for:
- Multi-tenant Telegram bot configuration
- Message sending
- Webhook processing
- Audit logging
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/api/telegram", tags=["Telegram"])


# ============================================================================
# TENANT MANAGEMENT ENDPOINTS
# ============================================================================

class TenantCreateRequest(BaseModel):
    tenant_id: str
    bot_token: str
    chat_id: Optional[str] = None
    group_id: Optional[str] = None
    ops_group_id: Optional[str] = None
    rate_limit: int = 30


class TenantResponse(BaseModel):
    success: bool
    tenant: Optional[dict[str, Any]] = None
    error: Optional[str] = None


class TenantListResponse(BaseModel):
    tenants: list[dict[str, Any]]
    total: int


@router.get("/tenants")
async def list_tenants(_user=Depends(require_admin)) -> TenantListResponse:
    """List all Telegram tenants."""
    from app.telegram.multi_tenant import list_tenants
    
    tenants = list_tenants()
    return TenantListResponse(tenants=tenants, total=len(tenants))


@router.post("/tenants")
async def create_tenant(
    request: TenantCreateRequest,
    _user=Depends(require_admin),
) -> TenantResponse:
    """Create a new Telegram tenant."""
    from app.telegram.multi_tenant import register_tenant
    
    result = register_tenant(
        tenant_id=request.tenant_id,
        bot_token=request.bot_token,
        chat_id=request.chat_id,
        group_id=request.group_id,
        ops_group_id=request.ops_group_id,
        rate_limit=request.rate_limit,
    )
    
    if "error" in result:
        return TenantResponse(success=False, error=result["error"])
    
    return TenantResponse(success=True, tenant=result.get("tenant"))


@router.get("/tenants/{tenant_id}")
async def get_tenant(
    tenant_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Get tenant configuration."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    bot = get_telegram_bot()
    tenant = bot.get_tenant(tenant_id)
    
    if not tenant:
        raise HTTPException(status_code=404, detail=f"Tenant {tenant_id} not found")
    
    return tenant


@router.delete("/tenants/{tenant_id}")
async def delete_tenant(
    tenant_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Delete a tenant."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    bot = get_telegram_bot()
    result = bot.unregister_tenant(tenant_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.post("/tenants/{tenant_id}/activate")
async def activate_tenant(
    tenant_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Activate a tenant."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    bot = get_telegram_bot()
    result = bot.activate_tenant(tenant_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


@router.post("/tenants/{tenant_id}/deactivate")
async def deactivate_tenant(
    tenant_id: str,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Deactivate a tenant."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    bot = get_telegram_bot()
    result = bot.deactivate_tenant(tenant_id)
    
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    
    return result


# ============================================================================
# MESSAGE ENDPOINTS
# ============================================================================

class SendMessageRequest(BaseModel):
    tenant_id: str
    chat_id: str
    message: str
    parse_mode: Optional[str] = "HTML"


class SendMessageResponse(BaseModel):
    success: bool
    message_id: Optional[str] = None
    error: Optional[str] = None


@router.post("/messages")
async def send_message(
    request: SendMessageRequest,
    _user=Depends(require_admin),
) -> SendMessageResponse:
    """Send message to tenant."""
    from app.telegram.multi_tenant import send_message
    
    result = send_message(request.tenant_id, request.chat_id, request.message)
    
    if "error" in result:
        return SendMessageResponse(success=False, error=result["error"])
    
    return SendMessageResponse(
        success=True,
        message_id=result.get("message_id"),
    )


@router.get("/queue/status")
async def get_queue_status(_user=Depends(require_admin)) -> dict[str, Any]:
    """Get message queue status."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    return get_telegram_bot().get_queue_status()


# ============================================================================
# WEBHOOK ENDPOINTS
# ============================================================================

@router.post("/webhook")
async def handle_webhook(
    request: Request,
    _user=Depends(require_admin),
) -> dict[str, Any]:
    """Process Telegram webhook update."""
    from app.telegram.multi_tenant import process_webhook
    
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    result = process_webhook(update)
    return result


# ============================================================================
# AUDIT LOG ENDPOINTS
# ============================================================================

class AuditLogResponse(BaseModel):
    logs: list[dict[str, Any]]
    total: int


@router.get("/audit/logs")
async def get_audit_logs(
    tenant_id: Optional[str] = None,
    limit: int = 50,
    _user=Depends(require_admin),
) -> AuditLogResponse:
    """Get audit logs."""
    from app.telegram.multi_tenant import get_audit_logs
    
    logs = get_audit_logs(tenant_id, limit)
    return AuditLogResponse(logs=logs, total=len(logs))


# ============================================================================
# STATISTICS ENDPOINTS
# ============================================================================

@router.get("/stats")
async def get_stats(_user=Depends(require_admin)) -> dict[str, Any]:
    """Get Telegram bot statistics."""
    from app.telegram.multi_tenant import get_telegram_bot
    
    bot = get_telegram_bot()
    
    return {
        "total_tenants": len(bot.tenants),
        "active_tenants": len([t for t in bot.tenants.values() if t.is_active]),
        "total_messages_sent": sum(t.message_count for t in bot.tenants.values()),
        "audit_log_count": len(bot.audit_logs),
        "queue_size": len(bot._message_queue),
    }
