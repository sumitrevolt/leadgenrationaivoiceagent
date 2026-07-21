"""OpenClaw audit helpers — always redacted, always correlatable."""

from __future__ import annotations

from typing import Any

from app.integrations.openclaw.policies import redact_secrets
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def audit_openclaw(
    actor: str,
    action: str,
    *,
    command: str | None = None,
    safety_lane: str | None = None,
    correlation_id: str | None = None,
    detail: dict[str, Any] | None = None,
) -> None:
    """Write Owner OS audit row + structured log. Never raises to caller."""
    meta = redact_secrets(
        {
            "source": "openclaw_owner_copilot",
            "command": command,
            "safety_lane": safety_lane,
            "correlation_id": correlation_id,
            **(detail or {}),
        }
    )
    try:
        from app.platform import owner_os

        owner_os.audit(
            actor or "openclaw",
            f"openclaw.{action}",
            {
                "target": command or action,
                "correlation_id": correlation_id,
                "status": (detail or {}).get("status"),
                **meta,
            },
        )
    except Exception as exc:  # pragma: no cover — fail-open on audit store
        logger.warning("openclaw audit store failed: %s", type(exc).__name__)
    logger.info(
        "openclaw_audit action=%s command=%s lane=%s corr=%s actor=%s",
        action,
        command,
        safety_lane,
        correlation_id,
        (actor or "")[:80],
    )
