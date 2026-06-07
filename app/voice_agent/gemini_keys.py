"""
Shared Gemini API-key pool — multi-key rotation (free-AI resilience).
=====================================================================

WHY
---
Gemini free-tier quota is PER KEY *and* shared across uses: the same key powers
both audio-in STT (vobiz_stream) and the LLM replies (telecaller_brain /
llm_brain). One busy day of testing exhausts it → the phone agent goes deaf
AND dumb at once. Putting 2-3 keys in ``GEMINI_API_KEYS`` lets us rotate to the
next key the moment one returns a quota/429/ResourceExhausted error.

DESIGN
------
* Keys come from ``settings.gemini_api_keys`` (comma/space/newline separated)
  first, then the single ``settings.gemini_api_key`` — both deduped, order
  preserved. Env (``GEMINI_API_KEYS`` / ``GEMINI_API_KEY``) is a fallback when
  settings can't be imported.
* ONE process-wide "active" key (round-robin index). STT and LLM share it, so
  when STT burns key A, the LLM immediately stops using A too.
* ``advance_key(bad_key)`` only rotates when ``bad_key`` is still the active one
  → a burst of concurrent failures on the same key advances exactly once
  (doesn't skip the whole pool).
* Pure-python, thread-safe, zero new deps. Importing this NEVER raises.
"""
from __future__ import annotations

import os
import re
import threading
from typing import List, Optional

_LOCK = threading.Lock()
_KEYS: Optional[List[str]] = None
_IDX = 0

# Substrings that mark a quota / rate-limit failure across SDKs (google-genai,
# google.generativeai, REST). Matched case-insensitively against type+message.
_QUOTA_MARKERS = (
    "resourceexhausted", "resource exhausted", "quota", "429",
    "rate limit", "rate-limit", "ratelimit", "exhausted", "too many requests",
)


def _split(raw: str) -> List[str]:
    return [k.strip() for k in re.split(r"[,\s]+", raw or "") if k.strip()]


def _load_keys() -> List[str]:
    """Collect keys from settings (preferred) then env, deduped + ordered."""
    multi = single = ""
    try:
        from app.config import settings

        multi = (getattr(settings, "gemini_api_keys", "") or "").strip()
        single = (getattr(settings, "gemini_api_key", "") or "").strip()
    except Exception:
        pass
    multi = multi or (os.environ.get("GEMINI_API_KEYS", "") or "").strip()
    single = single or (os.environ.get("GEMINI_API_KEY", "") or "").strip()

    keys: List[str] = []
    seen = set()
    for k in _split(multi) + _split(single):
        if k not in seen:
            seen.add(k)
            keys.append(k)
    return keys


def reload_keys() -> List[str]:
    """Force re-read (e.g. after .env change). Resets the active index."""
    global _KEYS, _IDX
    with _LOCK:
        _KEYS = _load_keys()
        _IDX = 0
        return list(_KEYS)


def gemini_keys() -> List[str]:
    """All configured Gemini keys (lazy, cached). Empty list = none set."""
    global _KEYS
    if _KEYS is None:
        with _LOCK:
            if _KEYS is None:
                _KEYS = _load_keys()
    return list(_KEYS)


def key_count() -> int:
    return len(gemini_keys())


def active_key() -> str:
    """The currently-active key (round-robin position). "" if none configured."""
    keys = gemini_keys()
    if not keys:
        return ""
    with _LOCK:
        return keys[_IDX % len(keys)]


def advance_key(bad_key: str = "") -> str:
    """Rotate to the next key and return it. If ``bad_key`` is given, only
    advance when it is still the active key — so simultaneous failures on the
    SAME key rotate just once instead of cycling past good keys."""
    global _IDX
    keys = gemini_keys()
    if not keys:
        return ""
    if len(keys) == 1:
        return keys[0]
    with _LOCK:
        cur = keys[_IDX % len(keys)]
        if bad_key and bad_key != cur:
            return cur  # someone else already rotated past the bad key
        _IDX = (_IDX + 1) % len(keys)
        return keys[_IDX % len(keys)]


def is_quota_error(exc: BaseException) -> bool:
    """True when an exception looks like a quota/rate-limit error (→ rotate)."""
    try:
        s = f"{type(exc).__name__} {exc}".lower()
    except Exception:
        return False
    return any(m in s for m in _QUOTA_MARKERS)


__all__ = [
    "gemini_keys",
    "active_key",
    "advance_key",
    "key_count",
    "reload_keys",
    "is_quota_error",
]
