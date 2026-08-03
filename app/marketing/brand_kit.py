"""
brand_kit.py — per-client brand profile (naam/tagline/phone/colors/tone).
==========================================================================

Ek baar brand save karo → posters/posts har jagah wahi branding auto-apply.
Persistence: data/brand_kits/{client_id}.json (gitignored data dir, pure
stdlib). Colors strict #RRGGBB validate hote hain (SVG injection-safe).

  save_brand(client_id, data)              -> saved brand dict
  get_brand(client_id)                     -> dict | None
  apply_brand_to_poster_args(client_id, a) -> poster args + brand merge
    (missing business_name/tagline/phone fill + brand_primary/brand_accent
     colors — posters.generate_poster inhe gradient stops me lagata hai).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_BRAND_DIR = os.path.join("data", "brand_kits")
_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _safe_id(client_id: Any) -> str:
    """client_id ko filename-safe banao (path traversal block)."""
    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(client_id or "").strip())[:64]
    return s or "default"


def _path(client_id: Any) -> str:
    return os.path.join(_BRAND_DIR, _safe_id(client_id) + ".json")


def _clean_color(value: Any) -> str:
    c = str(value or "").strip()
    return c if _HEX_RE.match(c) else ""


def save_brand(client_id: Any, data: dict[str, Any] | None) -> dict[str, Any]:
    """Brand profile save karo (data/brand_kits/{id}.json). Saved dict lautata hai.

    Unknown/extra keys ignore; colors invalid hon to "" (kabhi raw inject nahi).
    """
    data = data if isinstance(data, dict) else {}
    colors = data.get("colors") if isinstance(data.get("colors"), dict) else {}
    brand = {
        "client_id": _safe_id(client_id),
        "business_name": str(data.get("business_name") or "").strip()[:120],
        "tagline": str(data.get("tagline") or "").strip()[:160],
        "phone": str(data.get("phone") or "").strip()[:40],
        "colors": {
            "primary": _clean_color(colors.get("primary")),
            "accent": _clean_color(colors.get("accent")),
        },
        "tone": str(data.get("tone") or "").strip()[:40],
        "logo_text": str(data.get("logo_text") or "").strip()[:40],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    os.makedirs(_BRAND_DIR, exist_ok=True)
    with open(_path(client_id), "w", encoding="utf-8") as f:
        json.dump(brand, f, ensure_ascii=False, indent=2)
    return brand


def get_brand(client_id: Any) -> dict[str, Any] | None:
    """Saved brand dict ya None (missing/corrupt par bhi kabhi raise nahi)."""
    path = _path(client_id)
    try:
        if not os.path.isfile(path):
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception as e:
        logger.warning(f"[brand_kit] read failed for {path}: {e}")
        return None


def delete_brand(client_id: Any) -> bool:
    """Delete saved brand profile file (admin customer removal). Returns True
    if a file was removed; never raises.

    The path is built from _BRAND_DIR at the call site rather than via _path()
    so the runtime-data scanner can prove WHICH store this DELETE touches. A
    destructive operation whose target resolves to an opaque expression cannot
    be reviewed, and the governance ratchet correctly refuses it.
    """
    brand_path = os.path.join(_BRAND_DIR, _safe_id(client_id) + ".json")
    try:
        if os.path.isfile(brand_path):
            os.remove(brand_path)
            return True
    except Exception as e:
        logger.warning(f"[brand_kit] delete failed for {brand_path}: {e}")
    return False


def apply_brand_to_poster_args(client_id: Any, args: dict[str, Any] | None) -> dict[str, Any]:
    """Poster args me brand merge karo (args ke explicit values jeet-te hain).

    Fill: business_name/tagline/phone (agar args me khali) + brand_primary/
    brand_accent colors. Brand na ho to args jaisa ke waisa wapas.
    """
    merged = dict(args or {})
    brand = get_brand(client_id)
    if not brand:
        return merged
    for key in ("business_name", "tagline", "phone"):
        if not str(merged.get(key) or "").strip() and brand.get(key):
            merged[key] = brand[key]
    colors = brand.get("colors") or {}
    if not str(merged.get("brand_primary") or "").strip() and colors.get("primary"):
        merged["brand_primary"] = colors["primary"]
    if not str(merged.get("brand_accent") or "").strip() and colors.get("accent"):
        merged["brand_accent"] = colors["accent"]
    return merged
