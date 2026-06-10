"""Exotel account helpers — balance/credits live monitoring (free API GET).

`balance()` 30-min cache ke saath ₹ credits lautata (Trial me bhi kaam karta —
live verified: v1 /Balance.json -> {"Balance": {"Amount": 422.61}}).
telephony_readiness (Tara) isse hourly use karta + low-balance alert.
Import-safe, kabhi raise nahi, bina creds = None.
"""

from __future__ import annotations

import base64
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CACHE: dict[str, Any] = {"at": 0.0, "amount": None}
_TTL_S = 1800  # 30 min


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if v:
        return v
    try:
        from app.config import settings

        return str(getattr(settings, name.lower(), "") or "")
    except Exception:
        return ""


def _conn() -> tuple[str, str] | None:
    sid, key, tok = _env("EXOTEL_SID"), _env("EXOTEL_API_KEY"), _env("EXOTEL_API_TOKEN")
    if not (sid and key and tok):
        return None
    host = (_env("EXOTEL_SUBDOMAIN") or "api").rstrip(".")
    if not host.endswith(".exotel.com"):
        host = f"{host}.exotel.com"
    auth = base64.b64encode(f"{key}:{tok}".encode()).decode()
    return f"https://{host}/v1/Accounts/{sid}", auth


async def balance(force: bool = False) -> float | None:
    """Account credits (₹). Cached 30 min. None = creds nahi / API fail."""
    if not force and _CACHE["amount"] is not None and time.time() - _CACHE["at"] < _TTL_S:
        return _CACHE["amount"]
    c = _conn()
    if not c:
        return None
    base, auth = c
    try:
        import httpx

        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{base}/Balance.json", headers={"Authorization": f"Basic {auth}"}, timeout=15.0
            )
            if r.status_code == 200:
                amt = float(((r.json() or {}).get("Balance") or {}).get("Amount") or 0)
                _CACHE["amount"], _CACHE["at"] = amt, time.time()
                return amt
    except Exception as e:
        logger.debug(f"[exotel_account] balance skip: {e}")
    return _CACHE["amount"]
