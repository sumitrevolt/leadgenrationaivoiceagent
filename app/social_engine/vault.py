"""social_engine.vault — per-client per-platform OAuth token store, ENCRYPTED-at-rest.

Fernet (cryptography==48 stack me hai). Key: env `SOCIAL_TOKEN_KEY` (urlsafe-b64 32B
Fernet key) warna `SECRET_KEY` se derive. Key unset = plaintext store + loud warning
(dev-only; prod me key set karo). Store: data/social_tokens.jsonl (latest (client,
platform,account_ref) wins). NEVER raises.

  put(client_id, platform, token, account_ref="", meta=None) -> bool
  get(client_id, platform, account_ref="") -> dict | None    # {token, meta, account_ref}
  list_accounts(client_id="") -> list[dict]
  delete(client_id, platform, account_ref="") -> bool
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_PATH = os.path.join("data", "social_tokens.jsonl")


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except Exception:
        return None
    key = (os.getenv("SOCIAL_TOKEN_KEY") or "").strip()
    if not key:
        sk = (os.getenv("SECRET_KEY") or os.getenv("SECRET") or "").strip()
        if not sk:
            return None
        key = base64.urlsafe_b64encode(hashlib.sha256(sk.encode()).digest()).decode()
    try:
        from cryptography.fernet import Fernet

        return Fernet(key.encode() if isinstance(key, str) else key)
    except Exception as e:
        logger.warning(f"[vault] bad key: {e}")
        return None


def _encrypt(token: str) -> tuple[str, bool]:
    f = _fernet()
    if f is None:
        logger.warning("[vault] SOCIAL_TOKEN_KEY/SECRET_KEY unset — token PLAINTEXT (dev only!)")
        return token, False
    try:
        return f.encrypt(token.encode()).decode(), True
    except Exception:
        return token, False


def _decrypt(value: str, enc: bool) -> str:
    if not enc:
        return value
    f = _fernet()
    if f is None:
        return ""
    try:
        return f.decrypt(value.encode()).decode()
    except Exception as e:
        logger.warning(f"[vault] decrypt failed: {e}")
        return ""


def _key(client_id: str, platform: str, account_ref: str) -> str:
    return f"{client_id}|{platform}|{account_ref}"


def _read() -> list[dict[str, Any]]:
    try:
        with open(_PATH, encoding="utf-8") as f:
            return [json.loads(x) for x in f if x.strip()]
    except FileNotFoundError:
        return []
    except Exception as e:
        logger.warning(f"[vault] read failed: {e}")
        return []


def put(
    client_id: str,
    platform: str,
    token: str,
    account_ref: str = "",
    meta: dict[str, Any] | None = None,
) -> bool:
    try:
        client_id = (client_id or "").strip()
        platform = (platform or "").strip().lower()
        if not client_id or not platform or not token:
            return False
        enc_val, enc = _encrypt(str(token))
        rec = {
            "k": _key(client_id, platform, account_ref or ""),
            "client_id": client_id,
            "platform": platform,
            "account_ref": account_ref or "",
            "tok": enc_val,
            "enc": enc,
            "meta": meta or {},
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[vault] put failed: {e}")
        return False


def _latest() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for rec in _read():
        k = str(rec.get("k") or "")
        if k:
            out[k] = rec  # baad wali line jeet ti
    return out


def get(client_id: str, platform: str, account_ref: str = "") -> dict[str, Any] | None:
    """account_ref diya = exact match; warna us client+platform ka LATEST account."""
    try:
        cid = (client_id or "").strip()
        plat = (platform or "").strip().lower()
        if account_ref:
            rec = _latest().get(_key(cid, plat, account_ref))
        else:
            cands = [
                r
                for r in _latest().values()
                if str(r.get("client_id") or "") == cid and str(r.get("platform") or "") == plat
            ]
            cands.sort(key=lambda r: str(r.get("ts") or ""))
            rec = cands[-1] if cands else None
        if not rec or rec.get("deleted"):
            return None
        token = _decrypt(str(rec.get("tok") or ""), bool(rec.get("enc")))
        if not token:
            return None
        return {"token": token, "account_ref": rec.get("account_ref") or "", "meta": rec.get("meta") or {}}
    except Exception as e:
        logger.warning(f"[vault] get failed: {e}")
        return None


def list_accounts(client_id: str = "") -> list[dict[str, Any]]:
    cid = (client_id or "").strip()
    out = []
    for rec in _latest().values():
        if rec.get("deleted"):
            continue
        if cid and str(rec.get("client_id") or "") != cid:
            continue
        out.append(
            {
                "client_id": rec.get("client_id"),
                "platform": rec.get("platform"),
                "account_ref": rec.get("account_ref") or "",
                "meta": rec.get("meta") or {},
                "ts": rec.get("ts"),
            }
        )
    return out


def delete(client_id: str, platform: str, account_ref: str = "") -> bool:
    try:
        rec = {
            "k": _key((client_id or "").strip(), (platform or "").strip().lower(), account_ref or ""),
            "deleted": True,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[vault] delete failed: {e}")
        return False
