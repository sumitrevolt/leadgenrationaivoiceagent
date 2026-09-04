"""Impersonation — "login as customer" (super-admin support superpower).

KYUN: customer bole "mera dashboard tuta hai" to abhi screenshots maangne padte.
Yeh super_admin ko EK customer ka short-lived portal-session mint karne deta —
uske data me jaake debug, bina uska password jaane/maange.

SECURITY (non-negotiable):
  - SIRF super_admin (`require_super_admin`) — sub-admin/member ko bhi nahi.
  - GATED `IMPERSONATION=1` (default OFF) — flag off = saare endpoints 404 (feature inert).
  - SHORT-LIVED token (default 30 min) — blast-radius bounded.
  - HAR start/stop `log_audit` (AuditLog, severity=warning) me — kisne kis client ko,
    kab, kis IP se. Tamper-record.
  - Token me `imp=true` + `imp_by` claim — portal banner dikha sake; password kabhi
    read/return nahi hota.

Customer portal `require_customer` sirf role=="customer" check karta — yeh token
seamless chalta wahan, par audit + markers ke saath.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.admin import log_audit
from app.api.auth_deps import require_super_admin
from app.config import settings
from app.models.base import get_async_db
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/impersonate", tags=["Impersonation"])


def _enabled() -> bool:
    return (os.getenv("IMPERSONATION", "") or "").strip().lower() in ("1", "true", "yes", "on")


def _ttl_min() -> int:
    try:
        return int(os.getenv("IMPERSONATION_TTL_MIN", "30") or 30)
    except Exception:
        return 30


def _guard() -> None:
    if not _enabled():
        raise HTTPException(status_code=404, detail="Not found")


def _client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    try:
        return request.client.host if request.client else ""
    except Exception:
        return ""


def _client_email(client_id: str) -> str:
    """Customer login store se email; warna client profile se; warna placeholder."""
    cid = str(client_id or "").strip()
    try:
        from app.api.customer_auth import _read

        for r in _read():
            if str(r.get("client_id") or "").strip() == cid:
                return str(r.get("email") or "")
    except Exception:
        pass
    try:
        from app.marketing.clients_store import get_client

        return str((get_client(cid) or {}).get("email") or "")
    except Exception:
        return ""


def _biz_name(client_id: str) -> str:
    try:
        from app.marketing.clients_store import get_client

        return str((get_client(client_id) or {}).get("business_name") or "")
    except Exception:
        return ""


def _client_product(client_id: str) -> str:
    """Product enum for a client: marketing | voice | combo (ADR-009 two-product split).

    Normalisation mirrors ``app/api/customer_auth.py::me`` so both surfaces always
    agree on what a client is entitled to. Unknown/missing collapses to
    ``marketing`` — same safe default as the auth endpoint.
    """
    try:
        from app.marketing.clients_store import get_client

        p = str((get_client(client_id) or {}).get("product") or "").strip().lower()
    except Exception:
        p = ""
    if p not in ("marketing", "voice", "combo"):
        return "marketing"
    return p


# Landing targets an impersonating operator may be sent to. Strict allowlist:
# `portal_url` is echoed to the browser and followed by the frontend, so a free-
# form value here would be an open redirect. Anything not listed falls back to
# /app/customer rather than erroring — a bad hint must never break impersonation.
PORTAL_ALLOWLIST: tuple[str, ...] = (
    "/app/customer",
    "/app/customer/marketing",
    "/app/customer/voice",
    "/app/voice-console",
    "/app/marketing-console",
)


def _safe_portal_url(to: str) -> str:
    """Validate the requested landing target; default to /app/customer.

    Exact-match against the allowlist is the whole check: anything carrying a
    scheme, host, query or trailing path simply is not a member and therefore
    falls back. No string surgery is needed, which is the point — every rewrite
    is a place for an open-redirect bypass to hide.
    """
    return str(to or "").strip() if str(to or "").strip() in PORTAL_ALLOWLIST else "/app/customer"


def _mint_impersonation_token(client_id: str, email: str, admin_id: str, admin_email: str) -> str:
    """Customer-role JWT with impersonation markers. Short-lived."""
    from jose import jwt

    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(client_id),
        "email": (email or "").strip().lower(),
        "role": "customer",  # customer portal require_customer ise accept karta
        "type": "access",
        "imp": True,
        "imp_by": str(admin_id),
        "imp_email": (admin_email or "").lower(),
        "iat": now,
        "exp": now + timedelta(minutes=_ttl_min()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


@router.get("/config")
async def impersonation_config(admin=Depends(require_super_admin)):
    """Feature ON/OFF + TTL (UI ke liye)."""
    return {"enabled": _enabled(), "ttl_min": _ttl_min()}


@router.get("/targets")
async def impersonation_targets(admin=Depends(require_super_admin)):
    """Impersonate-able clients (jinke paas login hai). super_admin only + GATED."""
    _guard()
    out: list[dict] = []
    try:
        from app.api.customer_auth import _read

        seen: set[str] = set()
        for r in _read():
            cid = str(r.get("client_id") or "").strip()
            if not cid or cid in seen:
                continue
            seen.add(cid)
            out.append(
                {
                    "client_id": cid,
                    "email": str(r.get("email") or ""),
                    "business_name": _biz_name(cid),
                    # Lets the admin UI pick the right console per client instead
                    # of guessing: voice -> voice console, marketing -> marketing
                    # console, combo -> either.
                    "product": _client_product(cid),
                }
            )
            if len(out) >= 500:
                break
    except Exception as e:
        logger.debug(f"impersonation targets failed: {e}")
    out.sort(key=lambda x: (x.get("business_name") or "").lower())
    return {"targets": out, "count": len(out)}


class ImpersonateIn(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    reason: str = Field("", max_length=300)
    # Optional landing hint. Validated against PORTAL_ALLOWLIST by
    # _safe_portal_url(); unknown values fall back to /app/customer rather than
    # failing, so an outdated caller degrades instead of breaking.
    to: str = Field("", max_length=200)


@router.post("/start")
async def impersonation_start(
    body: ImpersonateIn,
    request: Request,
    admin=Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Super-admin: ek customer ka short-lived portal-session mint karo (audited)."""
    _guard()
    cid = str(body.client_id).strip()

    # Client exist karta hai? (login store ya client profile me)
    email = _client_email(cid)
    biz = _biz_name(cid)
    if not email and not biz:
        raise HTTPException(status_code=404, detail="Client not found")

    token = _mint_impersonation_token(cid, email, str(admin.id), str(getattr(admin, "email", "")))

    # AUDIT — tamper-record (kisne, kise, kab, kahan se, kyun).
    try:
        await log_audit(
            db,
            user_id=str(admin.id),
            action="impersonate.start",
            resource_type="client",
            resource_id=cid,
            new_value={
                "admin_email": str(getattr(admin, "email", "")),
                "client_email": email,
                "reason": body.reason or "",
                "ttl_min": _ttl_min(),
                "portal_url": _safe_portal_url(body.to),
            },
            ip_address=_client_ip(request),
            severity="warning",
        )
    except Exception as e:  # audit fail = log loud, par operation chalu (best-effort)
        logger.error(f"impersonation audit failed (start) cid={cid}: {e}")

    logger.warning(
        "IMPERSONATION start: admin=%s -> client=%s ip=%s",
        getattr(admin, "email", admin.id),
        cid,
        _client_ip(request),
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "client_id": cid,
        "business_name": biz,
        "impersonation": True,
        "expires_in": _ttl_min() * 60,
        # The frontend already honours this field (frontend/impersonate.html:77);
        # until now the backend hard-coded it, so operators could only ever land
        # on /app/customer and had no supported way to reach a console.
        "portal_url": _safe_portal_url(body.to),
    }


@router.post("/stop")
async def impersonation_stop(
    body: ImpersonateIn,
    request: Request,
    admin=Depends(require_super_admin),
    db: AsyncSession = Depends(get_async_db),
):
    """Impersonation end ka audit record (token client-side discard hota — stateless JWT)."""
    _guard()
    cid = str(body.client_id).strip()
    try:
        await log_audit(
            db,
            user_id=str(admin.id),
            action="impersonate.stop",
            resource_type="client",
            resource_id=cid,
            ip_address=_client_ip(request),
            severity="info",
        )
    except Exception as e:
        logger.debug(f"impersonation audit failed (stop) cid={cid}: {e}")
    return {"ok": True}
