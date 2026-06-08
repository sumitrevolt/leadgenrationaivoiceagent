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
    os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
    with open(_STORE, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


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
class SetPwIn(BaseModel):
    email: str = Field(..., min_length=3, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    client_id: str = Field(..., min_length=1, max_length=64)


@router.post("/set-password")
async def set_password(req: SetPwIn, current_user=Depends(require_admin)):
    """ADMIN: ek client ka login email+password set/reset karo (client_id se link)."""
    e = req.email.strip().lower()
    rows = [r for r in _read() if r.get("email") != e]
    rows.append(
        {
            "email": e,
            "client_id": req.client_id.strip(),
            "password_hash": _hash(req.password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    _write_all(rows)
    return {"ok": True, "email": e, "client_id": req.client_id.strip()}


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


@router.get("/me")
async def me(client_id: str = Depends(require_customer)):
    return {"client_id": client_id, "business_name": _biz_name(client_id)}


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
