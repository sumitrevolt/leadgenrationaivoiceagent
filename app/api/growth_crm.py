"""Native CRM sync (Zoho / HubSpot) endpoints.

Extracted from app/api/growth.py (2026-06-20 refactor) to shrink the god-router.
Mounted via growth.router.include_router(); paths unchanged (/api/growth/...).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.auth_deps import require_admin

router = APIRouter(tags=["Growth"])


# ------------- Native CRM sync (Zoho/HubSpot — Indian SMB) ------------- #
@router.get("/crm/status")
async def crm_status(client_id: str = "", user=Depends(require_admin)):
    """CRM sync armed status (global ya per-client). Creds kabhi expose nahi hote."""
    from app.platform import crm_sync

    return crm_sync.status(client_id)


@router.post("/crm/config")
async def crm_config(payload: dict, user=Depends(require_admin)):
    """Client ka CRM connect karo. Body: {client_id, provider: zoho|hubspot,
    zoho_client_id, zoho_client_secret, zoho_refresh_token, zoho_dc?, hubspot_token?}"""
    from app.platform import crm_sync

    client_id = str((payload or {}).get("client_id") or "").strip()
    if not client_id:
        return {"ok": False, "error": "client_id required"}
    return crm_sync.save_client_config(client_id, payload or {})


@router.post("/crm/test")
async def crm_test(payload: dict | None = None, user=Depends(require_admin)):
    """Configured CRM creds verify (kuch create nahi hota)."""
    from app.platform import crm_sync

    return await crm_sync.test_connection(str((payload or {}).get("client_id") or ""))


@router.post("/crm/sync-lead")
async def crm_sync_lead(payload: dict, user=Depends(require_admin)):
    """Manual lead push. Body: {client_id?, note?, lead: {business_name, phone, email, ...}}"""
    from app.platform import crm_sync

    lead = (payload or {}).get("lead") or {}
    if not (lead.get("phone") or lead.get("email")):
        return {"ok": False, "error": "lead.phone ya lead.email chahiye"}
    return await crm_sync.push_lead(
        lead,
        client_id=str((payload or {}).get("client_id") or ""),
        note=str((payload or {}).get("note") or ""),
    )


@router.get("/crm/log")
async def crm_log(limit: int = 50, user=Depends(require_admin)):
    """Recent CRM pushes (ops visibility)."""
    from app.platform import crm_sync

    return {"recent": crm_sync.recent(limit)}
