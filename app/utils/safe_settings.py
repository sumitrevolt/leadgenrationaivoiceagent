"""Safe settings introspection — never print credential values.

2026-08-07 incident: dumping ``settings`` / ``settings.__dict__`` leaked
``vobiz_auth_token``, ``vobiz_sip_pass``, and ``DATABASE_URL`` into a chat
transcript. Use these helpers (or field-name allowlists) instead.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Field-name substrings that mark a value as secret (case-insensitive).
_SECRET_NAME_RE = re.compile(
    r"(pass|password|pwd|secret|token|api[_-]?key|credential|private[_-]?key|"
    r"auth[_-]?token|sip[_-]?pass|database_url|dsn|connection_string)",
    re.IGNORECASE,
)

# Safe to report presence/length/type for debugging telephony routing, etc.
_PROBE_ALLOWLIST = frozenset(
    {
        "public_base_url",
        "environment",
        "app_version",
        "vobiz_auth_id",
        "vobiz_sip_user",
        "vobiz_trunk_id",
        "vobiz_trunk_domain",
        "vobiz_caller_id",
        "redis_url",  # host only via presence — value still redacted below
        "qdrant_url",
        "smtp_host",
        "waha_base_url",
        "dnd_api_url",
        "platform_website_url",
    }
)


def is_secret_field_name(name: str) -> bool:
    """True if this attribute name must never have its value printed."""
    n = (name or "").strip()
    if not n or n.startswith("_"):
        return True
    if n.lower() in ("database_url", "sqlalchemy_database_uri", "proxy_url"):
        return True
    return bool(_SECRET_NAME_RE.search(n))


def value_fingerprint(value: Any, *, prefix_len: int = 8) -> dict[str, Any]:
    """Presence + length + sha256 prefix — never the raw value."""
    if value is None:
        return {"present": False, "length": 0, "sha256_prefix": None}
    s = str(value)
    if not s:
        return {"present": False, "length": 0, "sha256_prefix": None}
    digest = hashlib.sha256(s.encode("utf-8", errors="replace")).hexdigest()
    return {
        "present": True,
        "length": len(s),
        "sha256_prefix": digest[: max(4, min(prefix_len, 16))],
    }


def settings_names_only(settings_obj: Any) -> list[str]:
    """Sorted public attribute names on a settings-like object (no values)."""
    names: list[str] = []
    for name in dir(settings_obj):
        if name.startswith("_"):
            continue
        try:
            attr = getattr(type(settings_obj), name, None)
            if callable(attr) and not isinstance(attr, property):
                continue
        except Exception:
            continue
        names.append(name)
    return sorted(names)


def safe_settings_probe(
    settings_obj: Any,
    *,
    allowlist: frozenset[str] | None = None,
) -> dict[str, Any]:
    """Debug probe: allowlisted fields as fingerprints only; secrets as names+present.

    Never includes raw credential strings. Suitable for logging / chat reports.
    """
    allow = allowlist if allowlist is not None else _PROBE_ALLOWLIST
    out: dict[str, Any] = {"ok": True, "fields": {}, "secret_names_present": []}
    for name in settings_names_only(settings_obj):
        try:
            val = getattr(settings_obj, name)
        except Exception:
            continue
        if callable(val):
            continue
        if is_secret_field_name(name):
            fp = value_fingerprint(val)
            if fp["present"]:
                out["secret_names_present"].append(name)
            # Never put fingerprint of secrets into chat by default — names only.
            continue
        if name not in allow:
            continue
        # Non-secret allowlisted: fingerprint only (still no raw URL passwords).
        out["fields"][name] = value_fingerprint(val)
    out["secret_names_present"] = sorted(set(out["secret_names_present"]))
    return out


__all__ = [
    "is_secret_field_name",
    "value_fingerprint",
    "settings_names_only",
    "safe_settings_probe",
]
