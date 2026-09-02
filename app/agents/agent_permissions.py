"""Per-agent tool/side-effect permission matrix — OpenCode-style per-tool ACL.

OpenCode (open-source AI coding agent) ka ek standout safety-feature: har agent
ke liye per-tool "allow"/"deny" matrix — taaki ek agent jo content draft karta hai
woh galti se paisa kharch ya call na kar de. Yahi capability is project ke AI staff
ko deta hai (15+ named agents, har ek ke alag duties — team.py STAFF roster).

Design (project patterns):
  - `enabled()` sirf ENFORCEMENT ko gate karta — default OFF = `can()` hamesha True
    = ZERO behaviour change (allow-all, jaisa abhi hai).
  - Flag ON pe: matrix lookup. Tool unset → DEFAULT allow (fail-OPEN, project ka
    house pattern — meter/DND-transactional sab fail-open) EXCEPT HIGH_RISK tools
    {spend, place_call, send_whatsapp} jahan unset → DENY (fail-SAFE — yeh wahi
    ban/paisa-risk side-effects hain jinpe CLAUDE.md har jagah extra-careful hai).
  - Data file `data/agent_permissions.json`: {agent_name: {tool: "allow"|"deny"}}.
  - KABHI raise nahi karta — permission-check ki wajah se koi pipeline nahi girni
    chahiye (lookup error = fail to safe default per-tool).

Flag: AGENT_PERMISSIONS=1
"""

from __future__ import annotations

import json
import os
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_DATA_FILE = os.path.join("data", "agent_permissions.json")

# Side-effect tool categories an agent can be allowed/denied.
TOOL_CATEGORIES = (
    "send_email",
    "send_whatsapp",
    "place_call",
    "spend",
    "write_code",
    "execute_code",
    "publish",
    "external_api",
)

# Ban/paisa-risk side-effects: unset = DENY (fail-safe). Matches CLAUDE.md
# "WhatsApp bulk = ban", "cold calls = ₹10L risk", "spend" guardrails.
# `execute_code` (arbitrary-code executor, code_exec.py) is RCE-class → fail-safe.
HIGH_RISK = {"spend", "place_call", "send_whatsapp", "execute_code"}


def enabled() -> bool:
    """Gates ENFORCEMENT only. OFF (default) → can() always True = allow-all."""
    return (os.getenv("AGENT_PERMISSIONS") or "").strip().lower() in ("1", "true", "yes")


def _load() -> dict[str, dict[str, str]]:
    """Read the matrix json. Never raises; missing/corrupt → {}."""
    try:
        if not os.path.isfile(_DATA_FILE):
            return {}
        with open(_DATA_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        logger.debug(f"agent_permissions load failed: {e}")
        return {}


def _save(data: dict[str, dict[str, str]]) -> bool:
    """Persist matrix. Never raises; returns ok."""
    try:
        os.makedirs(os.path.dirname(_DATA_FILE), exist_ok=True)
        with open(_DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.warning(f"agent_permissions save failed: {e}")
        return False


def can(agent: str, tool: str) -> bool:
    """Kya `agent` `tool` (side-effect) use kar sakta hai?

    - Flag OFF → hamesha True (zero behaviour change, allow-all).
    - Flag ON → matrix lookup:
        * explicit "allow"/"deny" → wahi maano.
        * unset + HIGH_RISK tool → False (fail-safe, ban/paisa-risk).
        * unset + normal tool → True (fail-open, house pattern).
    Never raises — error pe HIGH_RISK = deny, warna allow.
    """
    if not enabled():
        return True
    a = (agent or "").strip().lower()
    t = (tool or "").strip().lower()
    high_risk = t in HIGH_RISK
    try:
        matrix = _load()
        perms = matrix.get(a) or {}
        action = (perms.get(t) or "").strip().lower()
        if action == "deny":
            return False
        if action == "allow":
            return True
        # unset → high-risk deny, else allow
        return not high_risk
    except Exception as e:
        logger.debug(f"agent_permissions can() failed for {a}/{t}: {e}")
        return not high_risk


def set_permission(agent: str, tool: str, action: str) -> dict[str, Any]:
    """Ek agent+tool ka allow/deny set karo (persist). Never raises."""
    a = (agent or "").strip().lower()
    t = (tool or "").strip().lower()
    act = (action or "").strip().lower()
    if not a:
        return {"ok": False, "error": "agent name required"}
    if t not in TOOL_CATEGORIES:
        return {"ok": False, "error": f"tool must be one of {list(TOOL_CATEGORIES)}"}
    if act not in ("allow", "deny"):
        return {"ok": False, "error": "action must be 'allow' or 'deny'"}
    try:
        matrix = _load()
        matrix.setdefault(a, {})[t] = act
        if not _save(matrix):
            return {"ok": False, "error": "save failed"}
        logger.info(f"agent_permissions: set {a}/{t} = {act}")
        return {"ok": True, "agent": a, "tool": t, "action": act}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def list_permissions() -> dict[str, Any]:
    """Poori matrix + meta (enforcement on/off, risk policy)."""
    return {
        "enabled": enabled(),
        "tool_categories": list(TOOL_CATEGORIES),
        "high_risk": sorted(HIGH_RISK),
        "permissions": _load(),
    }


__all__ = [
    "enabled",
    "can",
    "set_permission",
    "list_permissions",
    "TOOL_CATEGORIES",
    "HIGH_RISK",
]
