"""OpenClaw safety lanes, allowlist, and fail-closed gates.

GREEN  — autonomous after super-admin / gateway auth (read-only / diagnostics)
AMBER  — requires Owner OS approval before mutation (Stage B + durable idempotency)
RED    — prohibited via OpenClaw; owner must use existing admin workflows
"""

from __future__ import annotations

import logging
import os
from typing import Any

# Canonical typed command names (Stage A read-only default allowlist).
GREEN_COMMANDS: frozenset[str] = frozenset(
    {
        "platform.status",
        "agents.list",
        "agents.unhealthy",
        "agent.status",
        "approvals.list",
        "delivery.status",
        "queues.status",
        "business.daily_summary",
        "owner.next_actions",
        "runtime.status",
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

# --- Kavach harness command surface (additive; read=GREEN, control=AMBER) ---
try:
    from app.integrations.openclaw.harness_commands import HARNESS_AMBER, HARNESS_GREEN

    GREEN_COMMANDS = GREEN_COMMANDS | HARNESS_GREEN
    AMBER_COMMANDS = AMBER_COMMANDS | HARNESS_AMBER
except Exception:  # never break the base policy surface
    pass

# --- Automation-Max observe surface (additive GREEN only) ---
try:
    from app.integrations.openclaw.automation_commands import AUTOMATION_GREEN

    GREEN_COMMANDS = GREEN_COMMANDS | AUTOMATION_GREEN
except Exception:
    pass

# --- Mission-control chat ingress (GREEN observe/create + AMBER controls) ---
try:
    from app.integrations.openclaw.mission_commands import MISSION_AMBER, MISSION_GREEN

    GREEN_COMMANDS = GREEN_COMMANDS | MISSION_GREEN
    AMBER_COMMANDS = AMBER_COMMANDS | MISSION_AMBER
except Exception:
    pass

# --- External Agent Orchestrator observe surface (additive GREEN only) ---
try:
    from app.integrations.openclaw.external_agent_commands import EXTERNAL_AGENT_GREEN

    GREEN_COMMANDS = GREEN_COMMANDS | EXTERNAL_AGENT_GREEN
except Exception:
    pass

ALL_TYPED = GREEN_COMMANDS | AMBER_COMMANDS | RED_COMMANDS

DEFAULT_STAGE_A_ALLOWLIST = ",".join(sorted(GREEN_COMMANDS))

logger = logging.getLogger(__name__)


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


def is_production_env() -> bool:
    """True if any authoritative env marker is production.

    CI often sets ENVIRONMENT=development with APP_ENV=test. Stage A tests may
    set APP_ENV=production via monkeypatch — that must win even if ENVIRONMENT
    remains development. Never treat unknown/empty as production unless
    explicitly set.
    """
    values = {
        (os.getenv("ENVIRONMENT") or "").strip().lower(),
        (os.getenv("APP_ENV") or "").strip().lower(),
    }
    return "production" in values


def durable_idempotency_ready() -> bool:
    """AMBER production requires durable Redis idempotency. Memory alone is insufficient."""
    try:
        from app.integrations.openclaw.idempotency import durable_idempotency_available

        return bool(durable_idempotency_available())
    except Exception:
        return False


def _raw_allowlist_parts() -> set[str]:
    raw = (os.getenv("OPENCLAW_ALLOWED_COMMANDS") or "").strip()
    if not raw:
        return set(GREEN_COMMANDS)
    return {p.strip() for p in raw.split(",") if p.strip()}


def allowed_commands() -> frozenset[str]:
    """Env allowlist. Empty/unset → Stage A GREEN defaults.

    Production Stage A: strict subset of GREEN_COMMANDS. AMBER entries are stripped
    when durable idempotency is unavailable (high-severity warning). RED never admitted.
    OPENCLAW_ALLOW_RED_ACTIONS never expands RED into executable set.
    """
    parts = _raw_allowlist_parts()
    # Never expand allowlist into RED even if operator mis-sets env or ALLOW_RED=1.
    parts = {p for p in parts if p not in RED_COMMANDS}

    amber_requested = parts & AMBER_COMMANDS
    if is_production_env() and amber_requested and not durable_idempotency_ready():
        logger.error(
            "openclaw_stage_a_guard stripped_amber=%s reason=durable_idempotency_unavailable "
            "severity=high note=Stage_A_GREEN_only_until_Stage_B",
            sorted(amber_requested),
        )
        parts -= AMBER_COMMANDS

    if is_production_env():
        # Stage A production = GREEN-only structural subset.
        non_green = parts - GREEN_COMMANDS
        if non_green:
            logger.error(
                "openclaw_stage_a_guard stripped_non_green=%s reason=stage_a_green_only severity=high",
                sorted(non_green),
            )
            parts &= GREEN_COMMANDS

    return frozenset(parts)


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
        # OPENCLAW_ALLOW_RED_ACTIONS must NEVER make RED executable.
        _ = allow_red_actions()  # observed for ops clarity only
        return False, (
            f"RED command refused via OpenClaw: {c}. Use existing secure admin / Owner OS workflow."
        )
    if c not in allowed_commands():
        if lane == "AMBER" and is_production_env() and not durable_idempotency_ready():
            return (
                False,
                "AMBER disabled in production until durable OpenClaw idempotency (Stage B)",
            )
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
    durable = durable_idempotency_ready()
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
        "production": is_production_env(),
        "stage_a_green_only": is_production_env() or not durable,
        "durable_idempotency": durable,
        "idempotency_note": (
            "In-process cache is GREEN-read optimization / local tests only. "
            "AMBER production requires durable Redis idempotency (Stage B)."
        ),
        "note": "OpenClaw is an edge Copilot — Owner OS remains sole action authority",
    }
