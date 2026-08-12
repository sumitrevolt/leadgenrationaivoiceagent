"""Data-defined custom agents/personas — OpenCode/Kilo custom-modes parity.

OpenCode aur Kilo-Code dono "custom modes" dete hain: user ek naya agent/persona
(role + system_prompt + allowed tools) DEFINE kar sakta hai bina code-deploy ke.
Yahi capability is project me deta hai — skill_pack ke pattern par (jo
data/skills_extra/*.md ko runtime pe load karta), yahan
data/custom_agents/*.json se naye personas load hote hain (bind-mount = git pull
pe live, NO rebuild).

Data file shape (data/custom_agents/<name>.json):
    {
      "name": "harsh",
      "role": "Retention specialist",
      "system_prompt": "...",
      "allowed_tools": ["send_email", "publish"],   # ACL hint (agent_permissions)
      "product": "marketing"                          # optional
    }

Design (project patterns):
  - `enabled()` sirf gating ke liye (custom personas ko team roster me merge karna
    main-session wire karega — yeh module sirf load/validate/register deta hai).
  - mtime-cached load (skill_pack jaisa), pure-python, path-escape blocked.
  - `merged_roster()` ek hardcoded NOTE + custom agents return karta — team.py ko
    HEAVY import NAHI karta (sirf data dir read); actual STAFF-dict merge main
    session app/platform/team.py me wire karega (owned-file boundary respect).
  - KABHI raise nahi karta.

Flag: CUSTOM_AGENTS=1
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DATA_DIR = os.path.join("data", "custom_agents")
_REQUIRED = ("name", "role", "system_prompt")
_CACHE_TTL_S = 300
_MAX_BYTES = 32 * 1024

_cache: dict[str, Any] = {"at": 0.0, "agents": []}


def enabled() -> bool:
    return (os.getenv("CUSTOM_AGENTS") or "").strip().lower() in ("1", "true", "yes")


def _safe_name(name: str) -> str:
    """Slug-only — path escape / weird chars block (skill_pack pattern)."""
    return re.sub(r"[^a-z0-9_-]", "", (name or "").strip().lower())[:60]


def _parse(path: str) -> dict[str, Any] | None:
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            spec = json.load(f)
        if not isinstance(spec, dict):
            return None
        if not all((spec.get(k) or "") for k in _REQUIRED):
            return None
        tools = spec.get("allowed_tools")
        return {
            "name": _safe_name(spec.get("name", "")),
            "role": str(spec.get("role", ""))[:200],
            "system_prompt": str(spec.get("system_prompt", "")),
            "allowed_tools": [str(t) for t in tools] if isinstance(tools, list) else [],
            "product": str(spec.get("product", "") or "platform"),
            "source": "custom",
        }
    except Exception:
        return None


def _load_all() -> list[dict[str, Any]]:
    now = time.time()
    if _cache["agents"] and now - _cache["at"] < _CACHE_TTL_S:
        return _cache["agents"]
    out: list[dict[str, Any]] = []
    try:
        if os.path.isdir(_DATA_DIR):
            for fn in sorted(os.listdir(_DATA_DIR)):
                if fn.endswith(".json"):
                    a = _parse(os.path.join(_DATA_DIR, fn))
                    if a and a["name"]:
                        out.append(a)
    except Exception as e:
        logger.warning(f"custom_agents load failed: {e}")
    _cache["agents"] = out
    _cache["at"] = now
    return out


def list_custom_agents() -> list[dict[str, Any]]:
    """Saare data-defined personas (validated)."""
    return list(_load_all())


def get(name: str) -> dict[str, Any] | None:
    """Ek custom agent by name (slug-matched). None agar nahi mila."""
    n = _safe_name(name)
    if not n:
        return None
    for a in _load_all():
        if a["name"] == n:
            return a
    return None


def register(spec: dict[str, Any]) -> dict[str, Any]:
    """Naya custom agent define karo — validate + write json file. Never raises."""
    try:
        if not isinstance(spec, dict):
            return {"ok": False, "error": "spec must be an object"}
        missing = [k for k in _REQUIRED if not (spec.get(k) or "")]
        if missing:
            return {"ok": False, "error": f"missing required: {missing}"}
        n = _safe_name(spec.get("name", ""))
        if not n:
            return {"ok": False, "error": "invalid name (a-z 0-9 _ - only)"}
        payload = {
            "name": n,
            "role": str(spec.get("role", ""))[:200],
            "system_prompt": str(spec.get("system_prompt", "")),
            "allowed_tools": [
                str(t)
                for t in spec.get("allowed_tools", [])
                if isinstance(spec.get("allowed_tools"), list)
            ],
            "product": str(spec.get("product", "") or "platform"),
        }
        body = json.dumps(payload, indent=2, ensure_ascii=False)
        if len(body.encode("utf-8")) > _MAX_BYTES:
            return {"ok": False, "error": f"spec too large (>{_MAX_BYTES // 1024}KB)"}
        if "<script" in body.lower():
            return {"ok": False, "error": "script tags not allowed"}
        os.makedirs(_DATA_DIR, exist_ok=True)
        path = os.path.join(_DATA_DIR, f"{n}.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        _cache["at"] = 0.0  # bust cache
        logger.info(f"custom_agents: registered persona '{n}'")
        return {"ok": True, "name": n, "path": path}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def merged_roster() -> dict[str, Any]:
    """Hardcoded note + custom agents.

    NOTE: team.py ke STAFF-dict me actual merge MAIN SESSION wire karega — yeh
    helper sirf data dir se custom personas surface karta (team.py ko heavy import
    nahi karta, owned-file boundary respect). Use this output to merge upstream.
    """
    return {
        "enabled": enabled(),
        "note": (
            "Hardcoded STAFF roster app/platform/team.py me hai (code-defined). Yeh "
            "custom personas data/custom_agents/*.json se aate hain — team.py merge "
            "main session wire karega."
        ),
        "custom_agents": list(_load_all()),
    }


__all__ = [
    "enabled",
    "list_custom_agents",
    "get",
    "register",
    "merged_roster",
]
