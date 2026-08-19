"""Agent Task Queue → Staff Bus bridge.

Every state change in ``agent_task_queue`` (assign / delegate / complete / fail)
is mirrored as a signed envelope on the Staff Bus so the live SSE stream and
OpenClaw coordination plane see real work flowing through the 31-agent
workforce.

Design:
  - **Fail-open**: bridge errors are logged and swallowed — a bus hiccup must
    never block a task state transition.
  - **Idempotent-ish**: each task_id is unique and the bus has its own
    idempotency guard; double-fires are deduped by the bus.
  - **No new infrastructure**: reuses existing ``StaffBus.publish()`` and the
    ``lgai:events`` Redis channel wired in PR #409.
"""

from __future__ import annotations

from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _try_publish(
    *,
    event_type: str,
    source_agent_id: str,
    destination: str,
    payload: dict[str, Any],
    tenant_id: str = "platform",
) -> None:
    """Publish one envelope; never raises."""
    try:
        from app.platform.staff_bus.runtime import StaffBus, enabled

        if not enabled():
            return
        bus = StaffBus(require_flag=False)
        bus.publish(
            event_type=event_type,
            tenant_id=tenant_id,
            source_agent_id=source_agent_id,
            destination=destination,
            payload=payload,
        )
    except Exception as exc:
        logger.debug("staff_bus task_bridge publish skip: %s", exc)


def on_task_assigned(
    agent_id: str,
    goal: str,
    task_id: str,
    *,
    delegated_by: str = "human",
    client_id: str | None = None,
) -> None:
    """Mirror a new task to the bus as ``task.assigned``.

    ``source_agent_id`` is *who assigned* (the manager / delegating agent);
    ``destination`` is the target agent's team channel.
    """
    destination = _agent_team_channel(agent_id)
    _try_publish(
        event_type="task.assigned",
        source_agent_id=delegated_by or "manager",
        destination=destination,
        payload={
            "task_id": task_id,
            "target_agent": agent_id,
            "goal": (goal or "")[:500],
            "client_id": client_id or "",
            "delegated_by": delegated_by or "human",
        },
    )


def on_task_accepted(
    agent_id: str,
    goal: str,
    task_id: str,
) -> None:
    """Mirror a task claim to the bus as ``task.accepted``.

    ``source_agent_id`` is the agent claiming the task.
    """
    _try_publish(
        event_type="task.accepted",
        source_agent_id=agent_id,
        destination="manager",
        payload={
            "task_id": task_id,
            "target_agent": agent_id,
            "goal": (goal or "")[:500],
        },
    )


def on_task_completed(
    agent_id: str,
    task_id: str,
    *,
    result: str = "",
) -> None:
    """Mirror task completion to the bus as ``task.completed``."""
    _try_publish(
        event_type="task.completed",
        source_agent_id=agent_id,
        destination="manager",
        payload={
            "task_id": task_id,
            "result": (result or "")[:500],
        },
    )


def on_task_failed(
    agent_id: str,
    task_id: str,
    *,
    error: str = "",
) -> None:
    """Mirror task failure to the bus as ``task.failed``."""
    _try_publish(
        event_type="task.failed",
        source_agent_id=agent_id,
        destination="manager",
        payload={
            "task_id": task_id,
            "error": (error or "")[:500],
        },
    )


# --------------------------------------------------------------------------- #
# Team channel resolution (reuses manifest team mapping)
# --------------------------------------------------------------------------- #

_TEAM_CHANNEL_CACHE: dict[str, str] | None = None


def _agent_team_channel(agent_id: str) -> str:
    """Resolve an agent_id → bus channel name.  Falls back to 'ops'."""
    global _TEAM_CHANNEL_CACHE  # noqa: PLW0603
    if _TEAM_CHANNEL_CACHE is None:
        try:
            from app.platform.staff_bus.manifest import build_manifest

            manifest = build_manifest()
            _TEAM_CHANNEL_CACHE = {}
            for entry in manifest.get("agents") or []:
                _TEAM_CHANNEL_CACHE[entry["agent_id"]] = entry.get("default_buzz_channel", "ops")
        except Exception:
            _TEAM_CHANNEL_CACHE = {}
    return _TEAM_CHANNEL_CACHE.get(agent_id, "ops")
