"""Runtime UPI VPA — env first, admin data-file fallback.

Razorpay removed 2026-06-18; manual UPI is the India payment path.
``UPI_VPA`` in ``.env`` wins when set; otherwise ``data/platform_upi.json``
(set via admin dashboard / ``POST /api/admin/upi/configure``) enables pay-info
without container recreate.
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

logger = logging.getLogger(__name__)

_VPA_RE = re.compile(r"^[^\s@]+@[^\s@]+$")


def _STORE() -> str:
    """Platform UPI VPA config — same store family as upi_payments, sibling file."""
    from app.platform import runtime_data_authority as _auth

    return str(
        _auth.resolve_store_path(
            store_id="billing.upi_payments",
            legacy_path=Path("data") / "platform_upi.json",
            target_segments=("billing", "platform_upi.json"),
        )
    )


def _valid_vpa(vpa: str) -> bool:
    v = (vpa or "").strip()
    return bool(v and "@" in v and _VPA_RE.match(v))


def _read_store() -> dict:
    try:
        # Resolver at each I/O site — binding to a local unbinds the allowlist.
        if os.path.isfile(_STORE()):
            with open(_STORE(), encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("upi_config read failed: %s", e)
    return {}


def _write_store(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_STORE()) or ".", exist_ok=True)
        with open(_STORE(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("upi_config write failed: %s", e)
        return False


def get_vpa() -> str:
    """Effective VPA: ``UPI_VPA`` env → settings → data file."""
    env_v = (os.environ.get("UPI_VPA") or "").strip()
    if env_v:
        return env_v
    try:
        from app.config import settings

        cfg = (getattr(settings, "upi_vpa", "") or "").strip()
        if cfg:
            return cfg
    except Exception:
        pass
    stored = (_read_store().get("vpa") or "").strip()
    return stored if _valid_vpa(stored) else ""


def source() -> str:
    """Where the active VPA came from: env | settings | file | none."""
    if (os.environ.get("UPI_VPA") or "").strip():
        return "env"
    try:
        from app.config import settings

        if (getattr(settings, "upi_vpa", "") or "").strip():
            return "settings"
    except Exception:
        pass
    stored = (_read_store().get("vpa") or "").strip()
    if stored and _valid_vpa(stored):
        return "file"
    return "none"


def is_armed() -> bool:
    return _valid_vpa(get_vpa())


def set_vpa(vpa: str, *, set_by: str = "admin") -> dict:
    """Persist VPA to data file (env still wins on read if later set)."""
    v = (vpa or "").strip()
    if not _valid_vpa(v):
        return {"ok": False, "error": "Invalid UPI VPA — format: name@bank (e.g. shop@ybl)"}
    row = {
        "vpa": v,
        "set_by": (set_by or "admin")[:80],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ok = _write_store(row)
    return {"ok": ok, **row, "source": "file"}


def info() -> dict:
    """Summary for admin UI + activation probes."""
    vpa = get_vpa()
    src = source()
    wa = (os.environ.get("UPI_VERIFY_WA") or "918459012607").strip().lstrip("+")
    wa_link = f"https://wa.me/{wa}?text=" + quote("Payment screenshot — plan activate karo please")
    out: dict = {
        "enabled": is_armed(),
        "vpa": vpa,
        "source": src,
        "env_locked": src == "env",
        "wa_phone": wa,
        "wa_link": wa_link,
    }
    if vpa:
        try:
            from app.marketing.upi_kit import payment_kit

            kit = payment_kit("LeadGen AI", vpa)
            out["upi_link"] = kit.get("upi_link") or ""
            out["qr_svg"] = kit.get("qr_svg") or ""
        except Exception:
            out["upi_link"] = ""
            out["qr_svg"] = ""
    return out
