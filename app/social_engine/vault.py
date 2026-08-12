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
    expires_at: str = "",
) -> bool:
    """Loop-social-11 (2026-07-11): expires_at (ISO string) tracked for FB/LI
    60-day token rotation. Optional — empty means unknown/never-expires (e.g.
    LinkedIn app tokens, Postiz gateway keys, WhatsApp self-host). Meta gains
    `token_expiry_source` (`fb_60d_default` etc) so ops can distinguish computed
    vs owner-provided expiry."""
    try:
        client_id = (client_id or "").strip()
        platform = (platform or "").strip().lower()
        if not client_id or not platform or not token:
            return False
        enc_val, enc = _encrypt(str(token))
        meta = dict(meta or {})
        # If caller didn't supply expiry, apply platform defaults for the two
        # platforms with hard finite windows so the token-expiry watcher can
        # warn ahead of time.
        eff_expiry = (expires_at or "").strip()
        if not eff_expiry:
            _default = _default_expiry_for(platform)
            if _default:
                eff_expiry = _default
                meta.setdefault("token_expiry_source", f"{platform}_default")
        rec = {
            "k": _key(client_id, platform, account_ref or ""),
            "client_id": client_id,
            "platform": platform,
            "account_ref": account_ref or "",
            "tok": enc_val,
            "enc": enc,
            "meta": meta,
            "expires_at": eff_expiry,
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }
        os.makedirs(os.path.dirname(_PATH) or ".", exist_ok=True)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        logger.warning(f"[vault] put failed: {e}")
        return False


def _default_expiry_for(platform: str) -> str:
    """Platform-typical expiry window. FB Page tokens ~60d, LI 60d. Others =
    unknown/none. Returns ISO date string or ''."""
    import datetime as _dt

    windows = {"facebook": 60, "instagram": 60, "linkedin": 60}
    days = windows.get(platform.lower())
    if not days:
        return ""
    return (_dt.datetime.utcnow() + _dt.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")


def is_expired(rec: dict[str, Any]) -> bool:
    """True iff `expires_at` is set and in the past. Unknown expiry = never
    expires (empty string). Never raises."""
    try:
        exp = str((rec or {}).get("expires_at") or "").strip()
        if not exp:
            return False
        import datetime as _dt

        # Accept both "YYYY-MM-DDTHH:MM:SS" and date-only.
        try:
            when = _dt.datetime.fromisoformat(exp)
        except ValueError:
            when = _dt.datetime.strptime(exp[:10], "%Y-%m-%d")
        return when < _dt.datetime.utcnow()
    except Exception:
        return False


def is_expiring_soon(rec: dict[str, Any], days: int = 7) -> bool:
    """True iff token expires within `days` days (default 7). Includes
    already-expired tokens for the admin cockpit summary."""
    try:
        exp = str((rec or {}).get("expires_at") or "").strip()
        if not exp:
            return False
        import datetime as _dt

        try:
            when = _dt.datetime.fromisoformat(exp)
        except ValueError:
            when = _dt.datetime.strptime(exp[:10], "%Y-%m-%d")
        delta = when - _dt.datetime.utcnow()
        return delta.total_seconds() < days * 86400
    except Exception:
        return False


def check_token_expiries(days: int = 7) -> dict[str, Any]:
    """Scheduler-friendly sweep. Emits `token_expired` delivery-ledger event per
    expired token + returns admin cockpit summary. Never raises."""
    expired: list[dict[str, Any]] = []
    warning: list[dict[str, Any]] = []
    try:
        for rec in list_accounts(""):
            if is_expired(rec):
                expired.append(rec)
            elif is_expiring_soon(rec, days=days):
                warning.append(rec)
        # Import once outside loop so pytest monkeypatch.setattr on
        # delivery_ledger.log_event is respected (per-iteration re-import would
        # pick up the ORIGINAL not the patched one).
        try:
            from app.marketing import delivery_ledger as _dl
        except Exception:
            _dl = None  # type: ignore
        for row in expired:
            if _dl is None:
                break
            try:
                _dl.log_event(
                    str(row.get("client_id") or ""),
                    "token_expired",
                    detail=f"{row.get('platform')} account {row.get('account_ref') or ''}"[:200],
                    key=f"token_expired:{row.get('platform')}:{row.get('account_ref')}",
                )
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"[vault] check_token_expiries failed: {e}")
    return {
        "expired": expired,
        "warning": warning,
        "expired_count": len(expired),
        "warning_count": len(warning),
    }


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
        return {
            "token": token,
            "account_ref": rec.get("account_ref") or "",
            "meta": rec.get("meta") or {},
        }
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
                # Loop-social-11 fix (2026-07-11): include expires_at so
                # is_expired/is_expiring_soon/check_token_expiries work.
                "expires_at": rec.get("expires_at") or "",
            }
        )
    return out


def delete(client_id: str, platform: str, account_ref: str = "") -> bool:
    try:
        rec = {
            "k": _key(
                (client_id or "").strip(), (platform or "").strip().lower(), account_ref or ""
            ),
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
