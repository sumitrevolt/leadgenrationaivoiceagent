"""RBAC module grants — roles ke UPAR module-level access (design: docs/ADMIN_RBAC_DESIGN.md).

Storage: `users.preferences` JSON me `{"modules": [...], "must_change_password": bool}` —
existing Text column reuse, koi migration nahi. Enforcement: auth_deps.require_admin
member-roles (manager/agent/viewer) ke liye `module_for_path()` check karta hai.
Pure-python, never-raise, import-safe.
"""

from __future__ import annotations

import json
from typing import Any

# Grantable modules → path prefixes (naya admin router banao to yahan add karo,
# warna module-limited members ke liye wo 403 rahega — fail-closed by design).
MODULES: dict[str, list[str]] = {
    "marketing": ["/api/marketing", "/api/creative", "/api/contentauto", "/api/widgets"],
    "growth": ["/api/growth", "/api/seoops", "/api/localseo", "/api/brand"],
    "leads": ["/api/leads", "/api/data"],
    "agents": ["/api/agents", "/api/ai"],
    "clients": [
        "/api/clientcrm",
        "/api/conversion",
        "/api/lifecycle",
        "/api/minisite",
        "/api/journeys",
        "/api/clientops",
    ],
    "billing": ["/api/billing"],
    "telephony": ["/api/voiceai", "/api/calls", "/api/booking"],
    "analytics": ["/api/analytics", "/api/memory"],
}

_PREFIX_TO_MODULE: list[tuple[str, str]] = sorted(
    ((p, m) for m, ps in MODULES.items() for p in ps), key=lambda t: -len(t[0])
)


def module_for_path(path: str) -> str | None:
    """Request path → module name (longest-prefix match), unmapped → None."""
    p = (path or "").split("?")[0]
    for prefix, mod in _PREFIX_TO_MODULE:
        if p == prefix or p.startswith(prefix + "/"):
            return mod
    return None


def _prefs(user: Any) -> dict[str, Any]:
    try:
        raw = getattr(user, "preferences", None)
        if raw:
            d = json.loads(raw)
            if isinstance(d, dict):
                return d
    except Exception:
        pass
    return {}


def get_user_modules(user: Any) -> list[str]:
    """User ke granted modules (sirf valid catalog entries)."""
    mods = _prefs(user).get("modules")
    if not isinstance(mods, list):
        return []
    return [m for m in mods if isinstance(m, str) and m in MODULES]


def must_change_password(user: Any) -> bool:
    return bool(_prefs(user).get("must_change_password"))


def set_user_modules(user: Any, modules: list[str]) -> list[str]:
    """preferences JSON me modules set (invalid drop). Caller db.commit kare."""
    clean = [m for m in (modules or []) if isinstance(m, str) and m in MODULES]
    d = _prefs(user)
    d["modules"] = clean
    user.preferences = json.dumps(d, ensure_ascii=False)
    return clean


def set_must_change_password(user: Any, value: bool) -> None:
    d = _prefs(user)
    d["must_change_password"] = bool(value)
    user.preferences = json.dumps(d, ensure_ascii=False)


def member_can_access(user: Any, path: str) -> bool:
    """Module-limited member is path ko access kar sakta? (super/admin yahan nahi aate)."""
    mod = module_for_path(path)
    if mod is None:
        return False  # unmapped admin surface = fail-closed
    return mod in get_user_modules(user)


__all__ = [
    "MODULES",
    "module_for_path",
    "get_user_modules",
    "set_user_modules",
    "must_change_password",
    "set_must_change_password",
    "member_can_access",
]
