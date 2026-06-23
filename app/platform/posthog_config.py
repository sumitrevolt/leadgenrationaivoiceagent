"""PostHog runtime config - env first, admin data-file fallback."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_STORE = os.path.join("data", "posthog_config.json")
_DEFAULT_HOST = "https://us.i.posthog.com"


def _is_placeholder(value: str) -> bool:
    if not value:
        return False
    lower = value.lower()
    return any(
        marker in lower
        for marker in (
            "your-",
            "your_",
            "change-me",
            "change_me",
            "placeholder",
            "phc_test",
            "phc_xxx",
        )
    )


def _read_store() -> dict:
    try:
        if os.path.isfile(_STORE):
            with open(_STORE, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug("posthog_config read failed: %s", e)
    return {}


def _write_store(data: dict) -> bool:
    try:
        os.makedirs(os.path.dirname(_STORE) or ".", exist_ok=True)
        with open(_STORE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.warning("posthog_config write failed: %s", e)
        return False


def get_api_key() -> str:
    env_v = (os.environ.get("POSTHOG_API_KEY") or "").strip()
    if env_v and not _is_placeholder(env_v):
        return env_v
    return str(_read_store().get("posthog_api_key") or "").strip()


def get_host() -> str:
    env_v = (os.environ.get("POSTHOG_HOST") or "").strip()
    if env_v:
        return env_v
    return str(_read_store().get("posthog_host") or _DEFAULT_HOST).strip() or _DEFAULT_HOST


def set_posthog(*, api_key: str, host: str = "", set_by: str = "admin") -> dict:
    key = (api_key or "").strip()
    if not key:
        return {"ok": False, "error": "PostHog API key chahiye"}
    if _is_placeholder(key):
        return {"ok": False, "error": "Real PostHog API key chahiye"}

    host_v = (host or "").strip() or _DEFAULT_HOST
    row = _read_store()
    row.update(
        {
            "posthog_api_key": key,
            "posthog_host": host_v,
            "posthog_set_by": (set_by or "admin")[:80],
            "posthog_updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    ok = _write_store(row)
    return {"ok": ok, "armed": bool(key), "source": "file"}


def status() -> dict:
    key = get_api_key()
    host = get_host()
    store = _read_store()
    env_v = (os.environ.get("POSTHOG_API_KEY") or "").strip()
    source = "env" if env_v and not _is_placeholder(env_v) else ("file" if key else "none")
    return {
        "armed": bool(key and not _is_placeholder(key)),
        "api_key_prefix": key[:8] + "..." if len(key) > 8 else key,
        "host": host,
        "source": source,
        "updated_at": store.get("posthog_updated_at"),
    }


__all__ = ["get_api_key", "get_host", "set_posthog", "status"]
