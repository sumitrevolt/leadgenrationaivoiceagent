"""Client-facing API keys — Zapier-style integrations ka base (key se apna data pull).

Key format `lga_<32hex>`; sirf SHA-256 hash store hota (data/client_api_keys.jsonl) —
plain key sirf issue-response me ek baar. verify() → client_id | None. NEVER raises.
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "client_api_keys.jsonl")


def _read() -> list[dict[str, Any]]:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"api_keys read failed: {e}")
        return []


def _hash(key: str) -> str:
    return hashlib.sha256((key or "").encode()).hexdigest()


def issue(client_id: str, name: str = "default") -> dict[str, Any]:
    """Naya key — plain value SIRF is response me (store = hash only)."""
    client_id = (client_id or "").strip()
    if not client_id:
        return {"ok": False, "error": "client_id required"}
    key = "lga_" + secrets.token_hex(16)
    rec = {
        "hash": _hash(key),
        "client_id": client_id,
        "name": (name or "default")[:60],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "active": True,
    }
    try:
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}
    return {
        "ok": True,
        "api_key": key,
        "client_id": client_id,
        "note": "Key ko safe rakho — dobara nahi dikhegi.",
    }


def revoke(key_hash_prefix: str) -> dict[str, Any]:
    rows = _read()
    n = 0
    for r in rows:
        if r.get("hash", "").startswith((key_hash_prefix or "").strip()) and r.get("active"):
            r["active"] = False
            n += 1
    if n:
        try:
            with open(_PATH, "w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r) + "\n")
        except Exception as e:
            return {"ok": False, "error": str(e)[:120]}
    return {"ok": True, "revoked": n}


def list_keys(client_id: str = "") -> list[dict[str, Any]]:
    """Masked list (hash-prefix only)."""
    out = []
    for r in _read():
        if client_id and r.get("client_id") != client_id:
            continue
        out.append(
            {
                "hash_prefix": r.get("hash", "")[:12],
                "client_id": r.get("client_id"),
                "name": r.get("name"),
                "active": r.get("active"),
                "created_at": r.get("created_at"),
            }
        )
    return out


def verify(key: str) -> str | None:
    """key → client_id (active) | None."""
    key = (key or "").strip()
    if not key.startswith("lga_"):
        return None
    h = _hash(key)
    for r in _read():
        if r.get("hash") == h and r.get("active"):
            return r.get("client_id")
    return None
