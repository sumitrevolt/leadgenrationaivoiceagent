"""Agent poll — lightweight polling loop for agents to discover + claim bus tasks.

Completes the coordination loop:
    scheduler assigns (ATQ) → bus publishes (task_bridge) → agent polls (here) → agent claims (ATQ) → agent completes (ATQ)

Design:
    - **Two-source discovery**: bus JSONL for event visibility + PostgreSQL ATQ for
      authoritative state.  Bus events are the "discovery feed"; ATQ is the "claim gate".
    - **Fail-open**: bus read errors are logged and skipped — agent still tries claim_next().
    - **Idempotent**: tracks seen event_ids to avoid double-processing.
    - **Minimal**: ~100 lines, no new infrastructure, reuses existing ATQ + bus.

Usage::

    poller = AgentPoller("rohan")

    # One-shot: poll bus + claim next available task
    task = await poller.poll_and_claim()

    # Or step-by-step
    events = poller.poll()          # discover new task.assigned events
    task = await poller.claim()     # atomically claim from ATQ
    await poller.complete(task, result="done")
"""

from __future__ import annotations

import json
import os
import threading
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

# Thread-local seen-set per agent_id (avoid cross-agent contamination).
_LOCAL_SEEN: dict[str, set[str]] = {}
_LOCAL_LOCK = threading.Lock()


def _events_path() -> str:
    override = (os.getenv("STAFF_BUS_DATA_ROOT") or "").strip()
    root = override or "data/staff_bus"
    return os.path.join(root, "events.jsonl")


def _load_events_for_agent(
    agent_id: str,
    *,
    event_types: tuple[str, ...] = ("task.assigned",),
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Read bus JSONL and filter for events targeting this agent.

    Returns newest-first list of envelopes where:
      - event_type is in *event_types*
      - payload.target_agent == agent_id OR destination matches agent's team channel

    Fail-open: any read/parse error returns empty list.
    """
    path = _events_path()
    if not os.path.isfile(path):
        return []

    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        logger.debug("agent_poll: bus read skip: %s", exc)
        return []

    results: list[dict[str, Any]] = []
    # Read last N lines (most recent first) — bounded scan
    for line in reversed(lines[-500:]):
        line = line.strip()
        if not line:
            continue
        try:
            env = json.loads(line)
        except json.JSONDecodeError:
            continue

        et = env.get("event_type", "")
        if et not in event_types:
            continue

        payload = env.get("payload") or {}
        target = payload.get("target_agent", "")
        destination = env.get("destination", "")

        if target == agent_id or destination == agent_id:
            results.append(env)
            if len(results) >= limit:
                break

    return results


class AgentPoller:
    """Lightweight poll loop for one agent.

    Tracks seen event_ids across poll cycles to avoid re-processing.
    Thread-safe (per-agent_id isolation).
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id.strip().lower()
        with _LOCAL_LOCK:
            if self.agent_id not in _LOCAL_SEEN:
                _LOCAL_SEEN[self.agent_id] = set()

    # ------------------------------------------------------------------ #
    # Discovery — read bus JSONL for events targeting this agent
    # ------------------------------------------------------------------ #

    def poll(
        self,
        *,
        event_types: tuple[str, ...] = ("task.assigned",),
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Return new (unseen) events for this agent from the bus log.

        Each call returns events not seen in prior poll() calls.
        """
        all_events = _load_events_for_agent(self.agent_id, event_types=event_types, limit=limit)
        with _LOCAL_LOCK:
            seen = _LOCAL_SEEN[self.agent_id]
            fresh = []
            for env in all_events:
                eid = env.get("event_id", "")
                if eid and eid not in seen:
                    seen.add(eid)
                    fresh.append(env)
            # Cap seen set to prevent unbounded memory growth
            if len(seen) > 5000:
                # Keep most recent 2500 (set preserves insertion order in 3.7+)
                excess = len(seen) - 2500
                for _ in range(excess):
                    seen.pop()
        return fresh

    # ------------------------------------------------------------------ #
    # Claim — atomically claim next pending task from ATQ
    # ------------------------------------------------------------------ #

    async def claim(self) -> dict[str, Any] | None:
        """Claim the next pending task for this agent from the ATQ.

        Returns task dict or None if queue empty.
        This is the authoritative claim — bus events are discovery only.
        """
        try:
            from app.platform.agent_task_queue import claim_next

            return await claim_next(self.agent_id)
        except Exception as exc:
            logger.debug("agent_poll claim skip: %s", exc)
            return None

    # ------------------------------------------------------------------ #
    # Poll + Claim — convenience combo
    # ------------------------------------------------------------------ #

    async def poll_and_claim(self) -> dict[str, Any] | None:
        """Discover new bus events, then atomically claim next task.

        Returns claimed task dict or None.
        The poll() step is for visibility (what did the bus see?);
        the claim() step is for action (what did ATQ give me?).
        """
        # Always try claim — even if no new bus events, ATQ may have pending tasks
        # from earlier assignments that haven't been claimed yet.
        _fresh = self.poll()  # side effect: update seen-set
        return await self.claim()

    # ------------------------------------------------------------------ #
    # Complete / Fail — mark task terminal
    # ------------------------------------------------------------------ #

    async def complete(
        self,
        task_id: str,
        *,
        result: str = "",
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost_usd: float = 0.0,
        provider: str = "",
    ) -> dict[str, Any]:
        """Mark task as done. Bus event published by ATQ bridge automatically."""
        try:
            from app.platform.agent_task_queue import complete

            return await complete(
                task_id,
                result=result,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost_usd=cost_usd,
                provider=provider,
            )
        except Exception as exc:
            logger.debug("agent_poll complete skip: %s", exc)
            return {"ok": False, "error": str(exc)}

    async def fail(self, task_id: str, error: str = "") -> dict[str, Any]:
        """Mark task as failed. Bus event published by ATQ bridge automatically."""
        try:
            from app.platform.agent_task_queue import fail

            return await fail(task_id, error=error)
        except Exception as exc:
            logger.debug("agent_poll fail skip: %s", exc)
            return {"ok": False, "error": str(exc)}

    # ------------------------------------------------------------------ #
    # Query helpers
    # ------------------------------------------------------------------ #

    async def pending_tasks(self) -> list[dict[str, Any]]:
        """List pending tasks for this agent (read-only, no claim)."""
        try:
            from app.platform.agent_task_queue import list_tasks

            return await list_tasks(self.agent_id, status="pending", limit=10)
        except Exception:
            return []

    def bus_summary(self) -> dict[str, Any]:
        """Quick diagnostic: how many events on bus for this agent."""
        events = _load_events_for_agent(self.agent_id, limit=100)
        with _LOCAL_LOCK:
            seen_count = len(_LOCAL_SEEN.get(self.agent_id, set()))
        return {
            "agent_id": self.agent_id,
            "bus_events_found": len(events),
            "unique_events_seen": seen_count,
            "events_path": _events_path(),
        }


def reset_poll_state_for_tests() -> None:
    """Clear all per-agent seen-sets (tests only)."""
    with _LOCAL_LOCK:
        _LOCAL_SEEN.clear()
