"""Customer (client) login portal — self-contained, non-breaking.

Marketing clients ko apna account: email+password login → JWT → apni leads/calls/
content dekhein. Reuses the platform JWT helpers (admin.create_access_token /
decode_token). Credentials ek ALAG store me (data/customer_auth.jsonl) — User model /
admin auth ko touch nahi karta (zero migration, zero break).

pbkdf2-sha256 (stdlib) hashing — koi naya dep nahi. Import-safe, never raises on import.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.api.auth_deps import require_admin
from app.utils.logger import setup_logger

logger = setup_logger(__name__)

router = APIRouter(prefix="/customer/auth", tags=["Customer Portal"])
_security = HTTPBearer(auto_error=True)

_STORE = os.path.join("data", "customer_auth.jsonl")
_ITER = 120_000


# --------------------------------------------------------------------------- #
# password hashing (stdlib pbkdf2) + jsonl credential store
# --------------------------------------------------------------------------- #
def _hash(password: str) -> str:
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt.encode(), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def _verify(password: str, stored: str) -> bool:
    try:
        _algo, it, salt, h = stored.split("$", 3)
        dk = hashlib.pbkdf2_hmac("sha256", (password or "").encode(), salt.encode(), int(it))
        return secrets.compare_digest(dk.hex(), h)
    except Exception:
        return False


def _read() -> list[dict]:
    out: list[dict] = []
    try:
        if os.path.exists(_STORE):
            for ln in open(_STORE, encoding="utf-8"):
                ln = ln.strip()
                if ln:
                    try:
                        out.append(json.loads(ln))
                    except Exception:
                        pass
    except Exception:
        pass
    return out


def _write_all(rows: list[dict]) -> None:
    # Lock + atomic — auth store corrupt hua to saare customer logins tut jaate.
    from app.utils.file_lock import locked_rewrite

    content = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    if not locked_rewrite(_STORE, content):
        # fallback: direct write (lock util hi na ho to bhi auth kabhi na ruke)
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            f.write(content)


def _find(email: str) -> dict | None:
    e = (email or "").strip().lower()
    for r in _read():
        if r.get("email") == e:
            return r
    return None


def _biz_name(client_id: str) -> str:
    try:
        from app.marketing.clients_store import get_client

        return str((get_client(client_id) or {}).get("business_name") or "")
    except Exception:
        return ""


# --------------------------------------------------------------------------- #
# auth dependency
# --------------------------------------------------------------------------- #
def require_customer(creds: HTTPAuthorizationCredentials = Depends(_security)) -> str:
    """Return the authenticated client_id from a customer JWT (role=customer)."""
    try:
        from app.api.admin import decode_token

        payload = decode_token(creds.credentials)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid token")
    if payload.get("role") != "customer":
        raise HTTPException(status_code=403, detail="Customer token required")
    cid = payload.get("sub")
    if not cid:
        raise HTTPException(status_code=401, detail="Invalid token payload")
    return str(cid)


# --------------------------------------------------------------------------- #
# endpoints
# --------------------------------------------------------------------------- #
def register_login(email: str, password: str, client_id: str) -> dict:
    """Public-safe helper: ek email+password login banao/overwrite (client_id se link).

    Admin set-password AUR public self-serve signup (public_site.py) dono isko use karte —
    credential-store wiring ek hi jagah. Existing email overwrite hoti (idempotent).
    """
    e = (email or "").strip().lower()
    rows = [r for r in _read() if r.get("email") != e]
    rows.append(
        {
            "email": e,
            "client_id": str(client_id).strip(),
            "password_hash": _hash(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_all(rows)
    return {"email": e, "client_id": str(client_id).strip()}


def login_exists(email: str) -> bool:
    """True agar is email ka login already hai (public signup dedupe ke liye)."""
    return _find(email) is not None


def client_has_login(client_id: str) -> bool:
    """True agar is client_id pe pehle se koi login attached hai.

    Self-serve signup me ANTI-HIJACK guard: add_client phone/business_name pe dedupe
    karta — koi existing client ka naam de ke uspe login attach na kar paaye.
    """
    cid = str(client_id or "").strip()
    if not cid:
        return False
    try:
        return any(str(r.get("client_id") or "").strip() == cid for r in _read())
    except Exception:
        return False


class SetPwIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    client_id: str = Field(..., min_length=1, max_length=64)


@router.post("/set-password")
async def set_password(req: SetPwIn, current_user=Depends(require_admin)):
    """ADMIN: ek client ka login email+password set/reset karo (client_id se link)."""
    res = register_login(req.email, req.password, req.client_id)
    return {"ok": True, **res}


class LoginIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=1, max_length=128)


@router.post("/login")
async def customer_login(req: LoginIn):
    """Client login → JWT (role=customer, sub=client_id)."""
    rec = _find(req.email)
    if not rec or not _verify(req.password, rec.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    from app.api.admin import create_access_token

    cid = str(rec["client_id"])
    token = create_access_token(cid, rec["email"], "customer")
    return {
        "access_token": token,
        "token_type": "bearer",
        "client_id": cid,
        "business_name": _biz_name(cid),
    }


_VALID_PLANS = {"starter", "growth", "advanced"}


def _plan_minutes_safe(plan: str) -> int:
    try:
        from app.billing.usage import plan_minutes

        return plan_minutes(plan)
    except Exception:
        return 0


class SignupIn(BaseModel):
    business_name: str = Field(..., min_length=2, max_length=120)
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    phone: str = Field("", max_length=40)
    niche: str = Field("general", max_length=80)
    city: str = Field("", max_length=80)
    plan: str = Field("starter", max_length=30)


@router.post("/signup")
async def customer_signup(req: SignupIn):
    """PUBLIC self-serve signup — naya client profile + login ek shot me (no admin).

    Flow (har step defensive, signup kabhi 500 pe nahi girta):
      1) Email already registered -> 409 (login karein).
      2) clients_store me client profile auto-create (dedupe by phone/business name).
      3) Login credential (email -> client_id) save (pbkdf2).
      4) Default plan ke calling-minutes provision (activate_plan + reset_usage_period).
      5) Customer JWT (role=customer) turant return -> frontend seedha portal me.
    """
    email = (req.email or "").strip().lower()
    if "@" not in email or "." not in email.rsplit("@", 1)[-1]:
        raise HTTPException(status_code=422, detail="Valid email zaroori hai")
    if _find(email):
        raise HTTPException(status_code=409, detail="Email already registered — login karein")

    plan = (req.plan or "starter").strip().lower()
    if plan not in _VALID_PLANS:
        plan = "starter"

    # 2) Client profile auto-create (clients_store dedupes by phone/name; never raises).
    client_id = ""
    business_name = (req.business_name or "").strip() or "Aapka Business"
    try:
        from app.marketing.clients_store import add_client

        rec = add_client(
            business_name=business_name,
            niche=(req.niche or "general"),
            city=(req.city or ""),
            phone=(req.phone or ""),
            plan=plan,
        )
        client_id = str((rec or {}).get("id") or "")
        business_name = str((rec or {}).get("business_name") or business_name)
    except Exception as e:  # pragma: no cover - defensive
        logger.error(f"signup add_client failed: {e}")
    if not client_id:
        # Fallback id so signup still succeeds even if clients_store hiccups.
        client_id = "c_" + secrets.token_hex(6)

    # 3) Persist the login credential (email -> client_id).
    rows = [r for r in _read() if r.get("email") != email]
    rows.append(
        {
            "email": email,
            "client_id": client_id,
            "password_hash": _hash(req.password),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source": "self_serve_signup",
        }
    )
    _write_all(rows)

    # 4) Provision the plan's calling minutes (best-effort — never blocks signup).
    try:
        from app.billing import usage as _usage

        _usage.activate_plan(client_id, plan)
        _usage.reset_usage_period(client_id)
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"signup provisioning skipped: {e}")

    # 5) Issue a customer JWT immediately (auto-login after signup).
    from app.api.admin import create_access_token

    token = create_access_token(client_id, email, "customer")
    return {
        "access_token": token,
        "token_type": "bearer",
        "client_id": client_id,
        "business_name": business_name,
        "plan": plan,
        "minutes": _plan_minutes_safe(plan),
    }


@router.get("/me")
async def me(client_id: str = Depends(require_customer)):
    return {"client_id": client_id, "business_name": _biz_name(client_id)}


@router.get("/portal/content")
async def portal_content(client_id: str = Depends(require_customer)):
    """Customer ka APNA marketing content (Isha ke daily posts — ready/posted) +
    mini-site/bio/widget links. Dashboard '📣 Aapka Content' section ka payload.
    Ownership token se enforced; kabhi raise nahi (empty graceful).
    (2026-06-12 UX upgrade: pehle customer ko apna content dikhta hi nahi tha.)"""
    out: dict = {"items": [], "links": {}}
    try:
        from app.marketing.auto_content import list_queue

        items = list_queue(client_id, limit=10) or []
        out["items"] = [
            {
                "id": i.get("id"),
                "date": i.get("date"),
                "type": i.get("type"),
                "title": i.get("title") or i.get("theme") or "",
                "caption": i.get("caption") or i.get("text") or "",
                "hashtags": i.get("hashtags") or [],
                "status": i.get("status"),
                "image_url": i.get("image_url") or "",
            }
            for i in items
        ]
    except Exception as e:
        logger.debug(f"portal content queue failed: {e}")
    try:
        from app.marketing.clients_store import get_client

        c = get_client(client_id) or {}
        slug = c.get("slug") or ""
        if slug:
            out["links"] = {
                "mini_site": f"/b/{slug}",
                "bio_link": f"/b/{slug}/bio",
                "digital_card": f"/b/{slug}/card",
            }
        out["business_name"] = c.get("business_name") or _biz_name(client_id)
        out["niche"] = c.get("niche") or ""
    except Exception as e:
        logger.debug(f"portal content client failed: {e}")
    return out


@router.get("/portal/invoices")
async def portal_invoices(client_id: str = Depends(require_customer)):
    """Customer ke APNE invoices (GST engine se) — ownership token se enforced."""
    try:
        from app.billing import gst_invoice

        rows = [r for r in gst_invoice.list_invoices(500) if str(r.get("client_id")) == client_id]
        return {
            "invoices": [
                {
                    "number": r.get("number"),
                    "date": r.get("date"),
                    "description": r.get("description"),
                    "gross_inr": r.get("gross_inr"),
                    "plan": r.get("plan"),
                }
                for r in rows
            ]
        }
    except Exception:
        return {"invoices": []}


@router.get("/portal/invoice-html")
async def portal_invoice_html(number: str, client_id: str = Depends(require_customer)):
    """Apna invoice printable HTML (?number=INV/2026-27/0001) — ownership check ke saath."""
    from fastapi.responses import HTMLResponse

    try:
        from app.billing import gst_invoice

        inv = gst_invoice.get_by_number(number)
        if not inv or str(inv.get("client_id")) != client_id:
            return {"error": "invoice not found"}
        return HTMLResponse(gst_invoice.invoice_html(inv))
    except Exception:
        return {"error": "invoice render error"}


@router.get("/portal/dashboard")
async def portal_dashboard(client_id: str = Depends(require_customer)):
    """Authenticated customer dashboard — sirf apna data (token ke client_id se)."""
    try:
        from app.api.customer_dashboard import _build_from_db, _build_from_files

        resp = _build_from_db(client_id=client_id, campaign=None)
        if resp is None:
            resp = _build_from_files(client_id=client_id, campaign=None)
        return resp
    except Exception as e:
        logger.error(f"portal dashboard failed: {e}")
        raise HTTPException(status_code=500, detail=f"dashboard failed: {e}")
