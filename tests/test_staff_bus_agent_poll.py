"""Tests for Staff Bus agent polling mechanism."""

from __future__ import annotations

import json
import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _clean_state():
    """Reset in-memory state between tests."""
    from app.platform.staff_bus.agent_poll import reset_poll_state_for_tests

    reset_poll_state_for_tests()
    yield
    reset_poll_state_for_tests()


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #


def _make_event(
    event_id: str,
    target_agent: str,
    *,
    event_type: str = "task.assigned",
    task_id: str = "",
    goal: str = "test goal",
    destination: str = "",
) -> dict:
    """Build a minimal bus envelope for testing."""
    payload = {"target_agent": target_agent, "task_id": task_id, "goal": goal}
    return {
        "schema_version": "staff_bus.envelope.v1",
        "event_id": event_id,
        "correlation_id": event_id,
        "idempotency_key": f"test:{event_id}",
        "timestamp": "2026-08-19T12:00:00Z",
        "tenant_id": "platform",
        "source_agent_id": "coordinator",
        "destination": destination or target_agent,
        "event_type": event_type,
        "payload": payload,
        "payload_hash": "abc123",
        "sensitivity": "internal",
        "authority_requirement": "none",
        "retry_count": 0,
        "terminal_state": "open",
    }


def _write_events(path: str, events: list[dict]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False) + "\n")


# ------------------------------------------------------------------ #
# Tests: poll (bus discovery)
# ------------------------------------------------------------------ #


class TestPollDiscovery:
    """Verify poll() reads bus JSONL and filters by target_agent."""

    def test_poll_returns_events_for_agent(self, tmp_path):
        """Events targeting 'rohan' are returned; others are not."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        events = [
            _make_event("e1", "rohan", task_id="t1", goal="follow up leads"),
            _make_event("e2", "neha", task_id="t2", goal="rescore pipeline"),
            _make_event("e3", "rohan", task_id="t3", goal="send emails"),
        ]
        _write_events(events_file, events)

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            fresh = poller.poll()

        assert len(fresh) == 2
        targets = {e["payload"]["target_agent"] for e in fresh}
        assert targets == {"rohan"}

    def test_poll_deduplicates_across_calls(self, tmp_path):
        """Same event_id is not returned twice."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        _write_events(events_file, [_make_event("e1", "rohan", task_id="t1")])

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            first = poller.poll()
            second = poller.poll()

        assert len(first) == 1
        assert len(second) == 0

    def test_poll_empty_when_no_events(self, tmp_path):
        """No events file = empty result."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        nonexistent = str(tmp_path / "nonexistent_events.jsonl")
        with _patch_events_path(nonexistent):
            poller = AgentPoller("rohan")
            result = poller.poll()

        assert result == []

    def test_poll_skips_malformed_lines(self, tmp_path):
        """Malformed JSON lines are skipped gracefully."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        with open(events_file, "w") as fh:
            fh.write("not json\n")
            fh.write(json.dumps(_make_event("e1", "rohan", task_id="t1")) + "\n")
            fh.write("}{bad json}\n")

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            result = poller.poll()

        assert len(result) == 1
        assert result[0]["event_id"] == "e1"

    def test_poll_only_task_assigned_by_default(self, tmp_path):
        """By default, only task.assigned events are returned."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        events = [
            _make_event("e1", "rohan", event_type="task.assigned"),
            _make_event("e2", "rohan", event_type="work.status"),
            _make_event("e3", "rohan", event_type="task.completed"),
        ]
        _write_events(events_file, events)

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            result = poller.poll()

        assert len(result) == 1
        assert result[0]["event_type"] == "task.assigned"

    def test_poll_custom_event_types(self, tmp_path):
        """Custom event_types filter works."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        events = [
            _make_event("e1", "rohan", event_type="task.assigned"),
            _make_event("e2", "rohan", event_type="task.completed"),
        ]
        _write_events(events_file, events)

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            result = poller.poll(event_types=("task.assigned", "task.completed"))

        assert len(result) == 2


# ------------------------------------------------------------------ #
# Tests: bus_summary
# ------------------------------------------------------------------ #


class TestBusSummary:
    def test_summary_counts_correctly(self, tmp_path):
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        _write_events(
            events_file,
            [
                _make_event("e1", "rohan"),
                _make_event("e2", "rohan"),
                _make_event("e3", "neha"),
            ],
        )

        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            summary = poller.bus_summary()

        assert summary["agent_id"] == "rohan"
        assert summary["bus_events_found"] == 2


# ------------------------------------------------------------------ #
# Tests: poll_and_claim integration
# ------------------------------------------------------------------ #


class TestPollAndClaim:
    """Integration tests using mock ATQ."""

    def test_poll_and_claim_returns_none_when_empty(self, tmp_path):
        """No tasks in ATQ → returns None."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "nonexistent.jsonl")
        with _patch_events_path(events_file):
            poller = AgentPoller("rohan")
            # claim_next will fail because no DB, but should return None gracefully
            result = _run_sync(poller.poll_and_claim())

        # Either None (no pending tasks) or None (DB error, fail-open)
        assert result is None

    def test_complete_graceful_on_missing_task(self):
        """complete() on nonexistent task returns error dict, no crash."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        poller = AgentPoller("rohan")
        result = _run_sync(poller.complete("nonexistent-task-id", result="done"))
        assert result["ok"] is False

    def test_fail_graceful_on_missing_task(self):
        """fail() on nonexistent task returns error dict, no crash."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        poller = AgentPoller("rohan")
        result = _run_sync(poller.fail("nonexistent-task-id", error="oops"))
        assert result["ok"] is False


# ------------------------------------------------------------------ #
# Tests: edge cases
# ------------------------------------------------------------------ #


class TestEdgeCases:
    def test_agent_ids_are_lowercased(self):
        """Agent IDs are normalized to lowercase."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        poller = AgentPoller("ROHAN")
        assert poller.agent_id == "rohan"

    def test_poll_state_isolation_between_agents(self, tmp_path):
        """Seeing event e1 for rohan does not affect neha's poll."""
        from app.platform.staff_bus.agent_poll import AgentPoller

        events_file = str(tmp_path / "events.jsonl")
        _write_events(
            events_file,
            [_make_event("e1", "rohan"), _make_event("e2", "neha")],
        )

        with _patch_events_path(events_file):
            p1 = AgentPoller("rohan")
            p1.poll()
            p2 = AgentPoller("neha")
            fresh = p2.poll()

        assert len(fresh) == 1
        assert fresh[0]["event_id"] == "e2"


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

import contextlib
from unittest.mock import patch


@contextlib.contextmanager
def _patch_events_path(path: str):
    """Temporarily override the events.jsonl path for agent_poll."""
    with patch("app.platform.staff_bus.agent_poll._events_path", return_value=path):
        yield


def _run_sync(coro):
    """Run an async coroutine synchronously for tests."""
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
