"""1-click background removal (AdBanao-parity) — rembg lazy-optional.

Photo bytes → transparent PNG cutout (product/owner photo poster pe layer karne
ke liye). rembg HEAVY dep (onnxruntime ~200MB) — pip install USER ka decision
(VPS OOM lesson), isliye yahan SIRF lazy import + graceful error dict.

Cache: data/bg_removed/<sha1>.png — same photo dobara = free (CPU bachao).
Import-safe, NEVER raises.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_CACHE_DIR = os.path.join("data", "bg_removed")
_MAX_BYTES = 8 * 1024 * 1024  # 8MB


def available() -> bool:
    """rembg installed hai ya nahi (lazy check, import-time pe kabhi nahi)."""
    try:
        import rembg  # noqa: F401

        return True
    except Exception:
        return False


def _cache_name(image_bytes: bytes) -> str:
    return hashlib.sha1(image_bytes).hexdigest()[:24] + ".png"


def remove_bg(image_bytes: bytes) -> bytes | dict[str, Any]:
    """Image bytes → transparent PNG cutout bytes, ya {ok: False, error} dict.
    Kabhi raise nahi karta."""
    if not image_bytes:
        return {"ok": False, "error": "image bytes missing — pehle photo do."}
    if len(image_bytes) > _MAX_BYTES:
        return {"ok": False, "error": "photo 8MB se badi hai — chhoti photo use karo."}

    # cache hit = free
    try:
        name = _cache_name(image_bytes)
        cached = os.path.join(_CACHE_DIR, name)
        if os.path.exists(cached) and os.path.getsize(cached) > 100:
            with open(cached, "rb") as f:
                return f.read()
    except Exception:
        name, cached = "", ""

    try:
        from rembg import remove  # lazy — heavy dep
    except Exception:
        return {
            "ok": False,
            "error": "rembg installed nahi — background removal abhi unavailable. "
            "(Install user decision: `pip install rembg` — heavy ~200MB.)",
        }

    try:
        out = remove(image_bytes)
        if not out or len(out) < 100:
            return {"ok": False, "error": "cutout empty aaya — alag photo try karo."}
        if cached:
            try:
                os.makedirs(_CACHE_DIR, exist_ok=True)
                with open(cached, "wb") as f:
                    f.write(out)
            except Exception as e:
                logger.debug(f"[bg_remove] cache write skip: {e}")
        return bytes(out)
    except Exception as e:
        logger.warning(f"remove_bg failed: {e}")
        return {"ok": False, "error": str(e)[:200]}
