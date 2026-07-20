"""OpenClaw safety lanes, allowlist, and fail-closed gates.

GREEN  — autonomous after admin auth (read-only / diagnostics)
AMBER  — requires Owner OS approval before mutation
RED    — prohibited via OpenClaw; owner must use existing admin workflows
"""

from __future__ import annotations

import os
from typing import Any

# Canonical typed command names (Stage A read-only default allowlist).
GREEN_COMMANDS: frozenset[str] = frozenset(
    {
        "platform.status",
        "agents.list",
        "agent.status",
        "approvals.list",
        "delivery.status",
        "queues.status",
        "business.daily_summary",
        "owner.next_actions",
    }
)

AMBER_COMMANDS: frozenset[str] = frozenset(
    {
        "agent.pause",
        "agent.resume",
        "agent.drain",
        "agent.stop_claims",
        "agent.assign_mission",
        "approval.decide",
    }
)

# Explicit RED catalogue — always refused even if allowlist misconfigured.
RED_COMMANDS: frozenset[str] = frozenset(
    {
        "calling.enable",
        "platform_dial.enable",
        "deploy.production",
        "billing.activate",
        "billing.refund",
        "billing.mutate",
        "customer.bulk_outreach",
        "customer.delete",
        "secrets.rotate",
        "kill_switch.bypass",
        "tenant.identity_mutate",
        "shell.execute",
        "sql.execute",
        "db.write_destructive",
        "audit.disable",
    }
)

ALL_TYPED = GREEN_COMMANDS | AMBER_COMMANDS | RED_COMMANDS

DEFAULT_STAGE_A_ALLOWLIST = ",".join(sorted(GREEN_COMMANDS))


def _truthy(name: str, default: str = "0") -> bool:
    return (os.getenv(name) or default).strip().lower() in ("1", "true", "yes", "on")


def openclaw_enabled() -> bool:
    """Master kill-switch. Default OFF — fail closed."""
    return _truthy("OPENCLAW_ENABLED", "0")


def allow_red_actions() -> bool:
    """Must stay False in production. Even True cannot bypass RED catalogue refuse."""
    return _truthy("OPENCLAW_ALLOW_RED_ACTIONS", "0")


def require_approval_for_amber() -> bool:
    return _truthy("OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER", "1")


def request_timeout_seconds() -> float:
    try:
        return max(1.0, min(60.0, float(os.getenv("OPENCLAW_REQUEST_TIMEOUT_SECONDS") or "12")))
    except (TypeError, ValueError):
        return 12.0


def allowed_commands() -> frozenset[str]:
    """Env allowlist. Empty/unset → Stage A GREEN defaults. Fail-closed for unknown."""
    raw = (os.getenv("OPENCLAW_ALLOWED_COMMANDS") or "").strip()
    if not raw:
        return frozenset(GREEN_COMMANDS)
    parts = {p.strip() for p in raw.split(",") if p.strip()}
    # Never expand allowlist into RED even if operator mis-sets env.
    return frozenset(p for p in parts if p not in RED_COMMANDS)


def safety_lane_for(command: str) -> str:
    c = (command or "").strip()
    if c in RED_COMMANDS:
        return "RED"
    if c in AMBER_COMMANDS:
        return "AMBER"
    if c in GREEN_COMMANDS:
        return "GREEN"
    return "RED"  # unknown = refuse


def command_permitted(command: str) -> tuple[bool, str]:
    """Return (ok, reason). Fail-closed when flag off or not allowlisted."""
    if not openclaw_enabled():
        return False, "OPENCLAW_ENABLED=0 — OpenClaw edge layer disabled"
    c = (command or "").strip()
    if not c:
        return False, "empty command"
    lane = safety_lane_for(c)
    if lane == "RED":
        return False, (
            f"RED command refused via OpenClaw: {c}. "
            "Use existing secure admin / Owner OS workflow."
        )
    if c not in allowed_commands():
        return False, f"command not in OPENCLAW_ALLOWED_COMMANDS: {c}"
    if lane == "AMBER" and not require_approval_for_amber():
        # Still require Owner OS approval path in adapter — this flag only softens UX.
        pass
    return True, "ok"


def redact_secrets(payload: Any) -> Any:
    """Shallow/deep redact of obvious secret keys for logs + audit."""
    secret_keys = {
        "password",
        "secret",
        "token",
        "api_key",
        "apikey",
        "authorization",
        "bearer",
        "private_key",
        "smtp_password",
        "openclaw_api_token",
        "database_url",
        "redis_url",
    }

    def _walk(obj: Any) -> Any:
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                lk = str(k).lower()
                if lk in secret_keys or any(
                    s in lk for s in ("secret", "password", "token", "api_key")
                ):
                    out[k] = "***REDACTED***"
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(obj, list):
            return [_walk(x) for x in obj[:100]]
        if isinstance(obj, str) and (
            obj.startswith("sk-") or obj.startswith("Bearer ") or "BEGIN PRIVATE" in obj
        ):
            return "***REDACTED***"
        return obj

    return _walk(payload)


def policy_snapshot() -> dict[str, Any]:
    return {
        "enabled": openclaw_enabled(),
        "allow_red_actions": allow_red_actions(),
        "require_approval_for_amber": require_approval_for_amber(),
        "timeout_seconds": request_timeout_seconds(),
        "allowed_commands": sorted(allowed_commands()),
        "green": sorted(GREEN_COMMANDS),
        "amber": sorted(AMBER_COMMANDS),
        "red": sorted(RED_COMMANDS),
        "calling_hard_off": True,
        "note": "OpenClaw is an edge Copilot — Owner OS remains sole action authority",
    }
