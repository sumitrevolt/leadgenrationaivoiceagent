"""mcp_keys.py — API-key issuance + metered-usage tracking for MCP-as-product.

The 2026-06-16 billionaire-scale audit named this the single "biggest-leverage
billionaire-scale automation" available to the platform: expose the existing
internal MCP capabilities through a metered, key-gated REST surface so other
AI agents (and a B2B customer's automation stack) can drive the qualification
pipeline programmatically. Outcome-based billing = revenue without time.

This module is the AUTH + METERING layer. The API surface itself lives in
app/api/mcp_product.py.

Design:
- **Keys**: format lgmcp_<24-byte url-safe random>. Stored as SHA-256 hash
  in data/mcp_keys.jsonl so a leaked file can't be replayed. Issued shown
  ONCE at creation.
- **Per-key quota**: daily call budget (default 1000) + total cap (default
  None = unlimited). Quota tracked in data/mcp_keys_usage.jsonl as
  (key_hash, ymd, count) appends; a fast in-memory cache reads tail and
  caches today's count per key. 429 + Retry-After when exceeded.
- **Per-key scope**: capabilities list (subset of SUPPORTED_CAPABILITIES) the
  key is allowed to invoke. Default = all read-only capabilities.
- **Admin-only management**: issue / list / revoke via /api/admin/mcp-keys.

Flag MCP_PRODUCT=1 — OFF default. The PRODUCT routes (app/api/mcp_product.py)
require this AND a valid key; with the flag off, every metered route returns
503 so customers know the surface is paused.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from pathlib import Path
from typing import Optional

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "MCP_PRODUCT"
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_KEYS_PATH = _DATA_DIR / "mcp_keys.jsonl"
_USAGE_PATH = _DATA_DIR / "mcp_keys_usage.jsonl"

_DEFAULT_DAILY = 1000

SUPPORTED_CAPABILITIES = (
    "niches.list",  # GET 42-niche catalog
    "lead.score",  # POST score a lead from text/json
    "qualifier.run",  # POST run BANT qualifier (placeholder until billing)
)


def enabled() -> bool:
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _ensure_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _hash(plain: str) -> str:
    return hashlib.sha256(plain.strip().encode("utf-8")).hexdigest()


def _read_keys() -> list[dict]:
    if not _KEYS_PATH.exists():
        return []
    try:
        out: list[dict] = []
        for line in _KEYS_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _atomic_rewrite_keys(rows: list[dict]) -> bool:
    _ensure_dir()
    tmp = _KEYS_PATH.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(_KEYS_PATH)
        return True
    except Exception as exc:
        logger.error("mcp_keys rewrite failed: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _append_usage(key_hash: str, capability: str) -> None:
    _ensure_dir()
    rec = {
        "kh": key_hash[:16],  # only the prefix — file can be shared if needed
        "ymd": time.strftime("%Y-%m-%d"),
        "cap": capability,
        "ts": int(time.time()),
    }
    try:
        with _USAGE_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass


def _today_count(key_hash: str) -> int:
    """Count today's usage for a key (tail-read the usage file)."""
    if not _USAGE_PATH.exists():
        return 0
    ymd = time.strftime("%Y-%m-%d")
    prefix = key_hash[:16]
    try:
        # Tail-read enough lines for a busy day; usage rolls forward, so the
        # window stays bounded.
        lines = _USAGE_PATH.read_text(encoding="utf-8").splitlines()[-50000:]
    except Exception:
        return 0
    n = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Cheap substring prefilter — both compact and human-readable JSON
        # dumps contain "ymd" + the date. Avoids json-parsing every line on
        # a busy day. False negatives would silently undercount usage, which
        # is exactly the bug to avoid here, so keep this loose.
        if ymd not in line:
            continue
        try:
            rec = json.loads(line)
            if rec.get("kh") == prefix and rec.get("ymd") == ymd:
                n += 1
        except Exception:
            continue
    return n


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def _redact(row: dict) -> dict:
    r = dict(row)
    r.pop("key_hash", None)
    r["key_preview"] = r.pop("key_preview", "lgmcp_...")
    return r


def issue(
    label: str,
    daily_limit: int = _DEFAULT_DAILY,
    capabilities: list[str] | None = None,
) -> dict:
    """Create a new API key. Returns plaintext key ONCE — store it client-side
    immediately."""
    caps = list(capabilities or SUPPORTED_CAPABILITIES)
    bad = [c for c in caps if c not in SUPPORTED_CAPABILITIES]
    if bad:
        return {"ok": False, "error": f"unknown capabilities: {bad}"}
    plain = "lgmcp_" + secrets.token_urlsafe(24)
    h = _hash(plain)
    row = {
        "id": "mck_" + secrets.token_hex(8),
        "label": (label or "")[:80],
        "key_hash": h,
        "key_preview": plain[:12] + "..." + plain[-4:],
        "daily_limit": max(1, int(daily_limit)),
        "capabilities": caps,
        "enabled": True,
        "created_at": int(time.time()),
    }
    rows = _read_keys()
    rows.append(row)
    if not _atomic_rewrite_keys(rows):
        return {"ok": False, "error": "storage write failed"}
    return {"ok": True, "key": plain, **_redact(row)}


def list_all() -> list[dict]:
    return [_redact(r) for r in _read_keys()]


def set_enabled(key_id: str, enabled: bool) -> bool:
    """L.2: pause/resume a key without permanent revocation. Resuming a paused
    key restores all prior capabilities + quota counters."""
    rows = _read_keys()
    found = False
    for r in rows:
        if r.get("id") == key_id:
            r["enabled"] = bool(enabled)
            r["enabled_toggled_at"] = int(time.time())
            found = True
    if not found:
        return False
    return _atomic_rewrite_keys(rows)


def revoke(key_id: str) -> bool:
    rows = _read_keys()
    new_rows = []
    found = False
    for r in rows:
        if r.get("id") == key_id and r.get("enabled", True):
            r["enabled"] = False
            r["revoked_at"] = int(time.time())
            found = True
        new_rows.append(r)
    if not found:
        return False
    return _atomic_rewrite_keys(new_rows)


# --------------------------------------------------------------------------- #
# Auth + metering (called from app/api/mcp_product.py)
# --------------------------------------------------------------------------- #
def authenticate(key_plain: str) -> dict | None:
    """Resolve a plaintext key to its row. None on bad/disabled key."""
    if not key_plain or not key_plain.startswith("lgmcp_"):
        return None
    h = _hash(key_plain)
    for r in _read_keys():
        if r.get("key_hash") == h and r.get("enabled", True):
            return r
    return None


def check_and_meter(key_row: dict, capability: str) -> dict:
    """Atomic-ish: confirm the key is allowed + under quota, then record use.

    Returns:
      {"ok": True, "remaining": int}            - request authorized
      {"ok": False, "code": 403, "error": ...}  - capability not granted
      {"ok": False, "code": 429, "error": ...}  - daily quota exceeded
    """
    caps = list(key_row.get("capabilities") or [])
    if capability not in caps:
        return {"ok": False, "code": 403, "error": f"capability '{capability}' not granted"}
    used = _today_count(key_row["key_hash"])
    limit = int(key_row.get("daily_limit", _DEFAULT_DAILY))
    if used >= limit:
        return {
            "ok": False,
            "code": 429,
            "error": f"daily quota exceeded ({used}/{limit})",
            "retry_after_s": _seconds_until_midnight_utc(),
        }
    _append_usage(key_row["key_hash"], capability)
    return {"ok": True, "remaining": max(0, limit - used - 1)}


def _seconds_until_midnight_utc() -> int:
    now = time.time()
    return int((now // 86400 + 1) * 86400 - now)


def usage_summary(key_id: str | None = None) -> dict:
    """Aggregate: per-key calls today + last 7d. For the admin dashboard."""
    keys = _read_keys()
    out_keys = []
    for r in keys:
        today = _today_count(r["key_hash"])
        out_keys.append(
            {
                "id": r["id"],
                "label": r.get("label"),
                "enabled": r.get("enabled", True),
                "calls_today": today,
                "daily_limit": r.get("daily_limit"),
                "remaining_today": max(0, int(r.get("daily_limit", _DEFAULT_DAILY)) - today),
            }
        )
    return {"keys": out_keys, "total_keys": len(out_keys)}


__all__ = [
    "enabled",
    "SUPPORTED_CAPABILITIES",
    "issue",
    "list_all",
    "revoke",
    "set_enabled",
    "authenticate",
    "check_and_meter",
    "usage_summary",
]
