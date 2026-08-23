"""
DeepSeek Harness (DSH) Integration.

Centralized logic for:
- DSH_RUNTIME_ENABLED flag check
- DSH_ALLOWLIST_CSV parsing
- Shadow mode control (DSH_SHADOW_MODE=0)
- Health endpoint DSH fields
"""

import os
from typing import List, Optional, Set


def is_dsh_runtime_enabled() -> bool:
    """Check if DSH runtime is enabled.
    
    Returns:
        bool: True if DSH_RUNTIME_ENABLED=1, False otherwise.
    """
    value = (os.getenv("DSH_RUNTIME_ENABLED", "0") or "0").strip().lower()
    return value == "1"


def is_dsh_shadow_enabled() -> bool:
    """Check if DSH shadow mode is enabled.
    
    Returns:
        bool: True if DSH_SHADOW_ENABLED=1, False otherwise.
    """
    value = (os.getenv("DSH_SHADOW_ENABLED", "0") or "0").strip().lower()
    return value == "1"


def get_dsh_allowlist() -> Set[str]:
    """Parse DSH_ALLOWLIST_CSV into a set of allowed agents/tools.
    
    Returns:
        Set[str]: Set of allowed agents/tools. Empty if not provided.
    """
    raw = (os.getenv("DSH_ALLOWLIST_CSV", "") or "").strip()
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def get_dsh_health_fields() -> dict:
    """Get DSH fields for /health endpoint.
    
    Returns:
        dict: DSH health fields (enabled, shadow, allowlist).
    """
    return {
        "dsh_runtime_enabled": is_dsh_runtime_enabled(),
        "dsh_shadow_enabled": is_dsh_shadow_enabled(),
        "dsh_allowlist": list(get_dsh_allowlist()),
    }


def is_dsh_allowed(agent_id: Optional[str] = None, tool_token: Optional[str] = None) -> bool:
    """Check if an agent/tool is allowed by DSH_ALLOWLIST_CSV.
    
    Args:
        agent_id (Optional[str]): Agent ID to check.
        tool_token (Optional[str]): Tool token to check (format: "<name>@<version>").
    
    Returns:
        bool: True if allowed, False otherwise.
    """
    allowlist = get_dsh_allowlist()
    if not allowlist:
        return True  # No allowlist = allow all
    
    if agent_id and agent_id.strip().lower() in allowlist:
        return True
    if tool_token and tool_token.strip().lower() in allowlist:
        return True
    
    return False