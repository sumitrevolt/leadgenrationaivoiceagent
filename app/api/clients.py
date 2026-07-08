"""
Clients API — marketing client store + per-client auto content engine.
=======================================================================

  POST   /api/clients                          — naya marketing client add
  GET    /api/clients?status=                  — clients list (optional status)
  GET    /api/clients/{cid}                     — ek client
  PATCH  /api/clients/{cid}/status              — status badlo {status}
  POST   /api/clients/{cid}/content/run         — aaj ka content generate + queue
  GET    /api/clients/{cid}/content?status=     — content queue (newest first)
  POST   /api/clients/{cid}/content/{item_id}/status — item status {status}

Sab admin-auth (marketing.py jaisa pattern). Generators kabhi raise nahi karte;
phir bhi unexpected par 500 + detail. Har action team-log (isha) — best-effort.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import log_audit
from app.api.auth_deps import require_admin
from app.marketing import auto_content, clients_store
from app.models.base import get_async_db
from app.models.user import User
from app.utils.logger import setup_logger

logger = setup_logger(__name__)
router = APIRouter(prefix="/clients", tags=["Clients"])


def _log_isha(action: str, detail: str) -> None:
    """Team activity log (best-effort — kabhi request fail nahi karata)."""
    try:
        from app.platform.team import log_event

        log_event("isha", action, detail)
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Request models
# --------------------------------------------------------------------------- #


class ClientBrand(BaseModel):
    """Brand profile (#RRGGBB colors; invalid => ignore)."""

    primary: str = Field("", max_length=10)
    accent: str = Field("", max_length=10)
    tagline: str = Field("", max_length=160)
    logo_text: str = Field("", max_length=40)


class ClientSocials(BaseModel):
    """Client ke social handles (display/links ke liye)."""

    instagram: str = Field("", max_length=200)
    facebook: str = Field("", max_length=200)
    gbp: str = Field("", max_length=300)


class AddClientRequest(BaseModel):
    """Naya marketing client."""

    business_name: str = Field(..., min_length=1, max_length=120)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    phone: str = Field("", max_length=40)
    plan: str = Field("starter", max_length=40)
    product: str = Field("marketing", max_length=20)  # marketing|voice|combo (ADR-009)
    brand: ClientBrand = Field(default_factory=ClientBrand)
    socials: ClientSocials = Field(default_factory=ClientSocials)


class StatusRequest(BaseModel):
    """Status update (active/paused/dead)."""

    status: str = Field(..., min_length=1, max_length=30)


class ItemStatusRequest(BaseModel):
    """Content item status (draft/approved/posted/skipped)."""

    status: str = Field(..., min_length=1, max_length=30)


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@router.post("")
async def create_client(
    req: AddClientRequest,
    current_user: User = Depends(require_admin),
):
    """Naya marketing client banao (phone/naam pe dedupe; brand auto-save)."""
    try:
        client = clients_store.add_client(
            business_name=req.business_name,
            niche=req.niche,
            city=req.city,
            phone=req.phone,
            plan=req.plan,
            brand=req.brand.model_dump(),
            socials=req.socials.model_dump(),
            product=req.product,
        )
        _log_isha(
            "client_added",
            f"{req.business_name} ({req.product}/{req.niche or 'general'}, {req.plan})",
        )
        return {"client": client}
    except Exception as e:
        logger.error(f"Client add failed: {e}")
        raise HTTPException(status_code=500, detail=f"Client add failed: {e}")


@router.get("")
async def list_all_clients(
    status: str | None = None,
    product: str | None = Query(
        None, description="Filter by product lane: marketing | voice | combo"
    ),
    current_user: User = Depends(require_admin),
):
    """Marketing clients list (?status= / ?product= filters)."""
    try:
        rows = clients_store.list_clients(status=status, product=product)
        return {"clients": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"Client list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Client list failed: {e}")


@router.get("/{cid}")
async def get_one_client(
    cid: str,
    current_user: User = Depends(require_admin),
):
    """Ek client by id (404 agar na mile)."""
    try:
        client = clients_store.get_client(cid)
    except Exception as e:
        logger.error(f"Client lookup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Client lookup failed: {e}")
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return {"client": client}


@router.patch("/{cid}/status")
async def set_client_status(
    cid: str,
    req: StatusRequest,
    request: Request,
    current_user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Client ka status badlo (active/paused/dead)."""
    try:
        ok = clients_store.set_status(cid, req.status)
    except Exception as e:
        logger.error(f"Client status update failed: {e}")
        raise HTTPException(status_code=500, detail=f"Status update failed: {e}")
    if not ok:
        raise HTTPException(status_code=404, detail="Client not found")
    _log_isha("client_status", f"{cid} -> {req.status}")
    # AUDIT — pausing a customer's automation is a sensitive admin action; the
    # team-log above is informal/ephemeral, this is the formal tamper-record
    # /api/admin/audit-logs reads (best-effort — audit failure never blocks
    # the actual status change, mirrors impersonation.py's pattern).
    try:
        await log_audit(
            db,
            user_id=str(getattr(current_user, "id", "")),
            action="client.status_change",
            resource_type="client",
            resource_id=cid,
            new_value={"status": req.status.strip().lower()},
            ip_address=request.client.host if request.client else None,
            severity="warning",
        )
    except Exception as e:
        logger.warning(f"Audit log failed for client status change {cid}: {e}")
    return {"updated": True, "status": req.status.strip().lower()}


@router.post("/{cid}/content/run")
async def run_client_content(
    cid: str,
    current_user: User = Depends(require_admin),
):
    """Is client ke liye aaj ka content generate + queue me append (dedupe)."""
    try:
        client = clients_store.get_client(cid)
        if client is None:
            raise HTTPException(status_code=404, detail="Client not found")
        items = await auto_content.generate_for_client(client)
        added = auto_content._append_items(cid, items)
        _log_isha("content_run", f"{client.get('business_name') or cid}: {added} items")
        return {"client_id": cid, "generated": len(items), "added": added, "items": items}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Client content run failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content run failed: {e}")


@router.get("/{cid}/content")
async def get_client_content(
    cid: str,
    status: str | None = None,
    current_user: User = Depends(require_admin),
):
    """Client ke content queue items (newest first, optional ?status=)."""
    try:
        items = auto_content.list_queue(cid, status=status)
        return {"client_id": cid, "items": items, "total": len(items)}
    except Exception as e:
        logger.error(f"Client content list failed: {e}")
        raise HTTPException(status_code=500, detail=f"Content list failed: {e}")


@router.post("/{cid}/content/{item_id}/status")
async def set_content_item_status(
    cid: str,
    item_id: str,
    req: ItemStatusRequest,
    current_user: User = Depends(require_admin),
):
    """Content item ka status badlo (draft/approved/posted/skipped)."""
    try:
        ok = auto_content.mark_item(cid, item_id, req.status)
    except Exception as e:
        logger.error(f"Content item status failed: {e}")
        raise HTTPException(status_code=500, detail=f"Item status failed: {e}")
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found or invalid status")
    _log_isha("content_item_status", f"{cid}/{item_id} -> {req.status}")
    return {"updated": True, "status": req.status.strip().lower()}
