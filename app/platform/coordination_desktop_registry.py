"""Desktop-app coordination registry — read-only projection source.

Loads docs/coordination/desktop_registry.json (machine-readable truth)
and exposes it for the Coordination Hub snapshot. Never raises: missing,
unreadable, or invalid JSON degrades to {"ok": False, "apps": []}.
Mutations stay on Owner OS / missions / buzzlock — this is a doc loader.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REGISTRY_PATH = _REPO_ROOT / "docs" / "coordination" / "desktop_registry.json"

_REQUIRED_APP_KEYS = (
    "id",
    "name",
    "project",
    "worktree",
    "channel",
    "buzzlock_tool",
    "harness",
    "headless_cli",
    "heartbeat",
    "status",
)


def _valid_app(row: Any) -> bool:
    if not isinstance(row, dict):
        return False
    return all(key in row for key in _REQUIRED_APP_KEYS) and bool(str(row.get("id") or "").strip())


def load_registry(path: str | os.PathLike | None = None) -> dict[str, Any]:
    """Load the desktop registry. Never raises — always returns a dict."""
    target = Path(path) if path else _REGISTRY_PATH
    try:
        with open(target, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"ok": False, "error": "registry_malformed", "apps": []}
        apps = data.get("apps")
        if not isinstance(apps, list):
            return {"ok": False, "error": "registry_missing_apps", "apps": []}
        apps = [row for row in apps if _valid_app(row)]
        return {
            "ok": True,
            "version": int(data.get("version") or 0),
            "updated": str(data.get("updated") or ""),
            "apps": apps,
            "note": "Projected from docs/coordination/desktop_registry.json — Hub does not own enrollment.",
        }
    except OSError:
        logger.debug("[coord_desktop_registry] registry unreadable: %s", target)
        return {"ok": False, "error": "registry_unreadable", "apps": []}
    except json.JSONDecodeError:
        logger.debug("[coord_desktop_registry] registry invalid json: %s", target)
        return {"ok": False, "error": "registry_invalid_json", "apps": []}


def registry_slice() -> dict[str, Any]:
    """Hub-facing slice — static registry projection, inert-safe."""
    out = load_registry()
    return {
        "ok": out.get("ok") is True,
        "enabled": out.get("ok") is True,
        "apps": out.get("apps") or [],
        "version": out.get("version") or 0,
        "updated": out.get("updated") or "",
        "error": out.get("error"),
        "note": "Read-only projection — enrollment changes via Owner OS.",
    }


__all__ = ["load_registry", "registry_slice"]
