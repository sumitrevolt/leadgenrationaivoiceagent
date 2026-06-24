"""Multi-key credential pools — Hermes-agent parity. Free-tier capacity = #1 constraint.

Per-provider MULTIPLE API keys with round-robin rotation (load-spread → higher aggregate
free rate-limit) + per-key cooldown machinery. `free_ai._key()` consults `rotate()` ONLY
when `CRED_POOLS=1`; default OFF = single-key behaviour unchanged (settings value used
directly). Pure in-memory, hot-path safe, never-raise.

Extra keys read from env as `<ATTR>_2 .. <ATTR>_5` where ATTR is the settings/env key name
(e.g. `GROQ_API_KEY_2`). The base key (settings value) is slot 1. Key VALUES are never
logged or exposed via status — only counts/indices.

Note: MVP wires round-robin into the hot path (the capacity win). `mark_fail()` cooldown is
available for programmatic callers; deep per-call failure attribution into free_ai is a
future wire (kept out to minimise danger-file surgery).

Flag: CRED_POOLS=1
"""

from __future__ import annotations

import os
import threading
import time

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_LOCK = threading.Lock()
_RR: dict[str, int] = {}  # attr -> next round-robin index
_COOLDOWN: dict[str, float] = {}  # f"{attr}#{key}" -> until_ts
_DEFAULT_COOLDOWN_S = 120.0


def enabled() -> bool:
    return (os.getenv("CRED_POOLS") or "").strip().lower() in ("1", "true", "yes")


def _norm(attr: str) -> str:
    """Canonical env/dict key — UPPER (env vars are uppercase; free_ai may pass the
    lowercase settings-attr, the router passes uppercase — normalize so both match)."""
    return (attr or "").strip().upper()


def _extra_keys(attr: str) -> list[str]:
    out: list[str] = []
    a = _norm(attr)
    for n in (2, 3, 4, 5):
        v = (os.getenv(f"{a}_{n}") or "").strip()
        if v and v not in out:
            out.append(v)
    return out


def pool(attr: str, base: str = "") -> list[str]:
    """All keys for attr: base (slot 1) + env extras. Deduped. Never raises."""
    keys: list[str] = []
    try:
        b = (base or "").strip()
        if b:
            keys.append(b)
        for k in _extra_keys(attr):
            if k not in keys:
                keys.append(k)
    except Exception:
        return [base] if base else []
    return keys


def rotate(attr: str, base: str = "") -> str:
    """Next non-cooled key for attr (round-robin). Returns base if <=1 key. Never raises."""
    try:
        attr = _norm(attr)
        keys = pool(attr, base)
        if len(keys) <= 1:
            return base
        now = time.time()
        with _LOCK:
            n = len(keys)
            start = _RR.get(attr, 0) % n
            for off in range(n):
                idx = (start + off) % n
                k = keys[idx]
                if _COOLDOWN.get(f"{attr}#{k}", 0.0) <= now:
                    _RR[attr] = (idx + 1) % n
                    return k
            # all cooled → still rotate (fail-open: a cooled key beats no key)
            _RR[attr] = (start + 1) % n
            return keys[start]
    except Exception:
        return base


def mark_fail(attr: str, key: str, cooldown_s: float = _DEFAULT_COOLDOWN_S) -> None:
    """Cool a key after a 429/quota failure so rotate() skips it for a while."""
    try:
        if not key:
            return
        with _LOCK:
            _COOLDOWN[f"{_norm(attr)}#{key}"] = time.time() + max(1.0, float(cooldown_s))
    except Exception:
        pass


def key_counts(attrs: list[str]) -> dict[str, int]:
    """Per-attr key count (base+extras). Reads settings/env; values never exposed."""
    out: dict[str, int] = {}
    for a in attrs or []:
        try:
            base = (os.getenv(_norm(a)) or "").strip()
            out[a] = len(pool(a, base))
        except Exception:
            out[a] = 0
    return out


def pool_status() -> dict:
    try:
        attrs = set(_RR) | {c.split("#", 1)[0] for c in _COOLDOWN}
        return {
            "enabled": enabled(),
            "active_pools": {a: {"rr_index": _RR.get(a, 0)} for a in sorted(attrs)},
            "cooled_keys": sum(1 for v in _COOLDOWN.values() if v > time.time()),
        }
    except Exception:
        return {"enabled": enabled(), "active_pools": {}, "cooled_keys": 0}


__all__ = ["enabled", "pool", "rotate", "mark_fail", "key_counts", "pool_status"]
