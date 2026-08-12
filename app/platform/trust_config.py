"""Runtime trust keys — env first, admin data-file fallback (UPI pattern).

Turnstile: no-restart configure via admin dashboard.
Sentry DSN: saved to file + lazy init on configure (restart still recommended for worker).
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "trust_config.json")


def _read_store() -> dict:
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("trust_config read failed: %s", e)
    return {}


def _write_store(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("trust_config write failed: %s", e)
        return False


def get_turnstile_site_key() -> str:
    env_v = (os.environ.get("TURNSTILE_SITE_KEY") or "").strip()
    if env_v:
        return env_v
    return str(_read_store().get("turnstile_site_key") or "").strip()


def get_turnstile_secret() -> str:
    env_v = (os.environ.get("TURNSTILE_SECRET_KEY") or "").strip()
    if env_v:
        return env_v
    return str(_read_store().get("turnstile_secret_key") or "").strip()


def get_sentry_dsn() -> str:
    env_v = (os.environ.get("SENTRY_DSN") or "").strip()
    if env_v:
        return env_v
    try:
        from app.config import settings

        cfg = (getattr(settings, "sentry_dsn", "") or "").strip()
        if cfg:
            return cfg
    except Exception:
        pass
    return str(_read_store().get("sentry_dsn") or "").strip()


def set_turnstile(*, site_key: str, secret_key: str, set_by: str = "admin") -> dict:
    site = (site_key or "").strip()
    secret = (secret_key or "").strip()
    if not site or not secret:
        return {"ok": False, "error": "Turnstile site_key aur secret_key dono chahiye"}
    row = _read_store()
    row.update(
        {
            "turnstile_site_key": site,
            "turnstile_secret_key": secret,
            "turnstile_set_by": (set_by or "admin")[:80],
            "turnstile_updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    ok = _write_store(row)
    return {"ok": ok, "armed": bool(site and secret), "source": "file"}


def set_sentry_dsn(dsn: str, *, set_by: str = "admin") -> dict:
    v = (dsn or "").strip()
    if not v or not v.startswith("https://"):
        return {"ok": False, "error": "Valid Sentry DSN chahiye (https://…)"}
    row = _read_store()
    row.update(
        {
            "sentry_dsn": v,
            "sentry_set_by": (set_by or "admin")[:80],
            "sentry_updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    ok = _write_store(row)
    init_ok = False
    if ok:
        init_ok = _lazy_sentry_init(v)
    return {"ok": ok, "lazy_init": init_ok, "restart_recommended": True}


def _lazy_sentry_init(dsn: str) -> bool:
    """Best-effort Sentry init in running web process (worker needs restart)."""
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        if sentry_sdk.Hub.current.client is not None:
            return True
        sentry_sdk.init(dsn=dsn, integrations=[FastApiIntegration()], traces_sample_rate=0.05)
        return True
    except Exception as e:
        logger.debug("trust_config sentry lazy init skip: %s", e)
        return False


def status() -> dict:
    ts_site = get_turnstile_site_key()
    ts_secret = get_turnstile_secret()
    sentry = get_sentry_dsn()
    store = _read_store()
    return {
        "turnstile": {
            "armed": bool(ts_secret),
            "site_key_set": bool(ts_site),
            "site_key_prefix": ts_site[:8] + "…" if len(ts_site) > 8 else ts_site,
            "source": (
                "env"
                if (os.environ.get("TURNSTILE_SECRET_KEY") or "").strip()
                else ("file" if ts_secret else "none")
            ),
            "updated_at": store.get("turnstile_updated_at"),
        },
        "sentry": {
            "armed": bool(sentry),
            "dsn_prefix": sentry[:28] + "…" if len(sentry) > 28 else sentry,
            "source": (
                "env"
                if (os.environ.get("SENTRY_DSN") or "").strip()
                else ("file" if sentry else "none")
            ),
            "updated_at": store.get("sentry_updated_at"),
        },
    }
