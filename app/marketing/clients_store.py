"""
clients_store.py — marketing CLIENT records (per-client social-media handling).
================================================================================

Har marketing client ka record `data/marketing_clients.jsonl` me — jsonl-first
(append-only, kabhi data lost nahi). Brand bhi brand_kit.save_brand() se save
hota hai taaki posters/posts auto-brand ho jaayein.

  add_client(business_name, niche, ...) -> dict   (uuid id, dedupe by phone/name)
  list_clients(status=None)             -> list
  get_client(cid)                       -> dict | None
  set_status(cid, status)               -> bool
  update_client(cid, **fields)          -> dict | None

Pure stdlib, file-based, KABHI raise nahi karta. Module-level path const
`_CLIENTS_FILE` test-monkeypatch ke liye exposed hai.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Tests isse monkeypatch karte hain (tmp path). Hamesha is const ke through padho.
_CLIENTS_FILE = os.path.join("data", "marketing_clients.jsonl")

_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# brand_kit import-safe (na mile to bhi clients_store chale).
try:
    from app.marketing import brand_kit  # type: ignore
except Exception:  # pragma: no cover
    brand_kit = None  # type: ignore


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _digits(phone: Any) -> str:
    """Phone ke sirf last-10 digits (dedupe key)."""
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-10:] if len(d) >= 10 else d


def _clean_color(value: Any) -> str:
    c = str(value or "").strip()
    return c if _HEX_RE.match(c) else ""


def _norm_brand(brand: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    b = brand if isinstance(brand, dict) else {}
    return {
        "primary": _clean_color(b.get("primary")),
        "accent": _clean_color(b.get("accent")),
        "tagline": str(b.get("tagline") or "").strip()[:160],
        "logo_text": str(b.get("logo_text") or "").strip()[:40],
    }


def _norm_socials(socials: Optional[Dict[str, Any]]) -> Dict[str, str]:
    s = socials if isinstance(socials, dict) else {}
    return {
        "instagram": str(s.get("instagram") or "").strip()[:200],
        "facebook": str(s.get("facebook") or "").strip()[:200],
        "gbp": str(s.get("gbp") or "").strip()[:300],
    }


def _read_all() -> List[Dict[str, Any]]:
    """Saare client records (parse-safe; corrupt lines skip)."""
    rows: List[Dict[str, Any]] = []
    path = _CLIENTS_FILE
    try:
        if not os.path.isfile(path):
            return rows
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if isinstance(rec, dict) and rec.get("id"):
                        rows.append(rec)
                except Exception:
                    continue
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] read failed: {e}")
    return rows


def _append(rec: Dict[str, Any]) -> None:
    path = _CLIENTS_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _rewrite(rows: List[Dict[str, Any]]) -> None:
    """Poori file dobara likho (status/update ke liye). Atomic-ish."""
    path = _CLIENTS_FILE
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def add_client(
    business_name: str,
    niche: str,
    city: str = "",
    phone: str = "",
    plan: str = "starter",
    brand: Optional[Dict[str, Any]] = None,
    socials: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Naya marketing client banao (uuid id). Dedupe by phone (last-10) ya
    business_name (case-insensitive) — existing mile to wahi return (no dup).
    Brand bhi brand_kit me save hota hai (posters auto-brand). Kabhi raise nahi."""
    try:
        name = (business_name or "").strip()[:120] or "Aapka Business"
        niche_k = (niche or "general").strip().lower() or "general"
        ph_key = _digits(phone)
        name_key = name.lower()

        existing = _read_all()
        for r in existing:
            if ph_key and _digits(r.get("phone")) == ph_key:
                return r
            if not ph_key and str(r.get("business_name") or "").strip().lower() == name_key:
                return r

        cid = uuid.uuid4().hex[:12]
        brand_d = _norm_brand(brand)
        rec: Dict[str, Any] = {
            "id": cid,
            "business_name": name,
            "niche": niche_k,
            "city": (city or "").strip()[:80],
            "phone": str(phone or "").strip()[:40],
            "plan": (plan or "starter").strip().lower()[:30] or "starter",
            "status": "active",
            "brand": brand_d,
            "socials": _norm_socials(socials),
            "created_at": _now(),
        }
        _append(rec)

        # Brand ko brand_kit me bhi mirror karo (posters/content-pack auto-brand).
        if brand_kit is not None:
            try:
                brand_kit.save_brand(cid, {
                    "business_name": name,
                    "tagline": brand_d.get("tagline", ""),
                    "phone": rec["phone"],
                    "colors": {"primary": brand_d.get("primary", ""),
                               "accent": brand_d.get("accent", "")},
                    "logo_text": brand_d.get("logo_text", ""),
                })
            except Exception as e:  # pragma: no cover
                logger.debug(f"[clients_store] brand mirror skip: {e}")
        return rec
    except Exception as e:
        logger.warning(f"[clients_store] add_client failed: {e}")
        return {"error": str(e)}


def list_clients(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """Saare clients (optional status filter). Newest first. Kabhi raise nahi."""
    try:
        rows = _read_all()
        if status:
            st = status.strip().lower()
            rows = [r for r in rows if str(r.get("status") or "").lower() == st]
        rows.sort(key=lambda r: str(r.get("created_at") or ""), reverse=True)
        return rows
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] list_clients failed: {e}")
        return []


def get_client(cid: str) -> Optional[Dict[str, Any]]:
    """Ek client by id (None agar na mile). Kabhi raise nahi."""
    try:
        key = (cid or "").strip()
        for r in _read_all():
            if str(r.get("id")) == key:
                return r
    except Exception as e:  # pragma: no cover
        logger.warning(f"[clients_store] get_client failed: {e}")
    return None


def set_status(cid: str, status: str) -> bool:
    """Client ka status badlo (active/paused/dead). True agar update hua."""
    return update_client(cid, status=(status or "").strip().lower()) is not None


_ALLOWED_FIELDS = {
    "business_name", "niche", "city", "phone", "plan", "status",
    "brand", "socials",
}


def update_client(cid: str, **fields: Any) -> Optional[Dict[str, Any]]:
    """Client ke fields update karo (whitelist). Updated dict ya None. Kabhi
    raise nahi. Brand/socials dict-merge hote hain; brand change brand_kit me
    bhi mirror hota hai."""
    try:
        key = (cid or "").strip()
        rows = _read_all()
        found: Optional[Dict[str, Any]] = None
        for r in rows:
            if str(r.get("id")) == key:
                found = r
                break
        if found is None:
            return None

        for k, v in fields.items():
            if k not in _ALLOWED_FIELDS:
                continue
            if k == "brand":
                found["brand"] = _norm_brand(v)
            elif k == "socials":
                found["socials"] = _norm_socials(v)
            elif k == "status":
                found["status"] = str(v or "").strip().lower()[:30] or found.get("status", "active")
            elif k == "niche":
                found["niche"] = str(v or "").strip().lower()[:80] or found.get("niche", "general")
            else:
                found[k] = str(v or "").strip()[:120]
        found["updated_at"] = _now()
        _rewrite(rows)

        if "brand" in fields and brand_kit is not None:
            try:
                b = found["brand"]
                brand_kit.save_brand(key, {
                    "business_name": found.get("business_name", ""),
                    "tagline": b.get("tagline", ""),
                    "phone": found.get("phone", ""),
                    "colors": {"primary": b.get("primary", ""),
                               "accent": b.get("accent", "")},
                    "logo_text": b.get("logo_text", ""),
                })
            except Exception:  # pragma: no cover
                pass
        return found
    except Exception as e:
        logger.warning(f"[clients_store] update_client failed: {e}")
        return None


__all__ = [
    "add_client", "list_clients", "get_client", "set_status", "update_client",
]
