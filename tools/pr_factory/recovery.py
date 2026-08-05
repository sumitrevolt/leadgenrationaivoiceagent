"""Lease reclaim / stuck-mission playbook hooks (Wave 1 — documentation + thin API)."""

from __future__ import annotations

from typing import Any

from app.dev_control.external_agents import store
from app.dev_control.external_agents.schema import MissionState

STUCK_HINTS: tuple[str, ...] = (
    "Lease expired without heartbeat — reclaim via Owner OS / orchestrator retry",
    "Do not force-delete another agent's worktree",
    "ownership_conflict → cancel loser; winner keeps paths",
    "FAILED_RETRYABLE → orchestrator.retry(mission_id)",
    "Never reclaim into protected paths or RED intents",
)


def stuck_missions(limit: int = 50) -> list[dict[str, Any]]:
    """List missions that look stuck (blocked / retryable / owner decision)."""
    rows: list[dict[str, Any]] = []
    for m in store.list_missions(limit=limit):
        status = getattr(m, "status", None)
        if status in {
            MissionState.BLOCKED,
            MissionState.FAILED_RETRYABLE,
            MissionState.OWNER_DECISION_REQUIRED,
        }:
            rows.append(
                {
                    "mission_id": m.mission_id,
                    "status": status.value if hasattr(status, "value") else str(status),
                    "blocker": getattr(m, "blocker", "") or "",
                    "title": m.title,
                }
            )
    return rows


def playbook() -> dict[str, Any]:
    return {
        "steps": list(STUCK_HINTS),
        "canonical_retry": "app.dev_control.external_agents.orchestrator.retry",
        "canonical_cancel": "app.dev_control.external_agents.orchestrator.cancel",
        "note": "PR Factory does not own leases — external_agents store remains source of truth",
    }
