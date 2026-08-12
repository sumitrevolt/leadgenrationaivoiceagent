"""Integration expiry/health honesty API — admin (sanitized diagnostics) + customer
(tenant-scoped, redacted). Reads stored evidence only (bounded); makes no live
provider calls, sends nothing, and never returns tokens/secrets/raw payloads.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.auth_deps import require_admin
from app.api.customer_auth import require_customer
from app.platform import integration_status

router = APIRouter(tags=["Integrations"])


@router.get("/api/admin/integrations/health")
async def admin_integrations_health(
    client_id: str | None = Query(default=None),
    _user=Depends(require_admin),
) -> dict:
    """Admin-only, fail-closed via require_admin. Sanitized per-integration diagnostics."""
    items = integration_status.admin_integration_statuses(client_id=client_id)
    return {
        "integrations": items,
        "threshold_days": integration_status.expiring_threshold_days(),
    }


@router.get("/api/customer/integrations/health")
async def customer_integrations_health(
    client_id: str = Depends(require_customer),
) -> dict:
    """Customer-safe, tenant-scoped. `client_id` is taken ONLY from the auth token
    (never a query/body param), so a customer can only ever see their own tenant."""
    items = integration_status.customer_integration_statuses(client_id)
    return {"integrations": items}
