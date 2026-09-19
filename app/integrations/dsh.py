"""
DeepSeek Harness (DSH) Integration.

Centralized logic for:
- DSH_RUNTIME_ENABLED flag check
- DSH_AGENT_ALLOWLIST parsing (canonical; FAIL-CLOSED)
- Shadow mode control (DSH_SHADOW_ENABLED)
- Health endpoint DSH fields

Allowlist contract (repaired 2026-09-19):
    ``DSH_AGENT_ALLOWLIST`` is the ONE canonical bounded allowlist. It matches
    ``app/platform/automation_flag_manifest.py`` (which declares
    "empty means no DSH authority or shadow") and
    ``app/platform/workforce_runtime/dispatch.py`` (Plane 1, fail-closed).

        * empty / unset -> DENY everything (fail-closed)
        * ``*``         -> DENY everything (means "no bounded set")

    The legacy ``DSH_ALLOWLIST_CSV`` name was RETIRED here. It was defined
    nowhere in ``docker-compose.vps.yml``, so the previous fail-OPEN default
    (``if not allowlist: return True``) silently disabled this gate in
    production while the call site's own comment claimed "fail-closed", and
    while the flag manifest declared "empty = none". Two variable names for one
    gate is precisely how it stopped working: do NOT reintroduce a second name.

    Regression pins: ``tests/test_dsh_integration.py``.
"""

import os

# The single canonical allowlist variable.
ALLOWLIST_ENV = "DSH_AGENT_ALLOWLIST"

# Mirrors workforce_runtime.dispatch: "*" means "no bounded set" -> deny all.
_WILDCARD = "*"

# Pinned upstream SHA prefix of the DeepSeek Harness runtime we deploy as a
# governed child process. SINGLE SOURCE OF TRUTH: dsh_jobs.py and
# workforce_runtime/dispatch.py both import this, so a version bump is atomic
# across all 4 emission sites (previously 3 hard-coded copies + 1 constant).
DSH_RUNTIME_VERSION = "47f943859bef"  # pragma: allowlist secret -- pinned upstream SHA prefix


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


def get_dsh_allowlist() -> set[str]:
    """Parse DSH_AGENT_ALLOWLIST into a set of allowed agents/tools.

    Returns:
        Set[str]: Allowed agents/tools. An EMPTY set when the variable is unset,
        empty, or when the wildcard ``*`` is present (meaning "no bounded set",
        which denies all -- matching Plane 1 in workforce_runtime/dispatch.py).
    """
    raw = (os.getenv(ALLOWLIST_ENV, "") or "").strip()
    values = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return set() if _WILDCARD in values else values


def get_dsh_health_fields() -> dict:
    """Get DSH fields for /health endpoint.

    Reports the SAME canonical allowlist that enforcement reads, so /health
    cannot disagree with the gate that actually runs.

    Returns:
        dict: DSH health fields (enabled, shadow, allowlist).
    """
    return {
        "dsh_runtime_enabled": is_dsh_runtime_enabled(),
        "dsh_shadow_enabled": is_dsh_shadow_enabled(),
        "dsh_allowlist": sorted(get_dsh_allowlist()),
    }


def is_dsh_allowed(agent_id: str | None = None, tool_token: str | None = None) -> bool:
    """Check if an agent/tool is allowed by DSH_AGENT_ALLOWLIST.

    FAIL-CLOSED. An empty or unset allowlist denies everything, per the declared
    contract in ``automation_flag_manifest.py``.

    Args:
        agent_id (Optional[str]): Agent ID to check.
        tool_token (Optional[str]): Tool token to check (format: "<name>@<version>").

    Returns:
        bool: True only if the identity is explicitly listed.
    """
    allowlist = get_dsh_allowlist()
    if not allowlist:
        return False  # No bounded allowlist = no DSH authority.

    if agent_id and agent_id.strip().lower() in allowlist:
        return True
    if tool_token and tool_token.strip().lower() in allowlist:
        return True

    return False
