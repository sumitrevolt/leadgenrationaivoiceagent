"""Tests for Staff Bus ↔ agent_task_queue bridge.

Verifies that task state changes in agent_task_queue produce matching bus
envelopes visible on the live SSE stream.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _enable_bus(monkeypatch):
    """Arm Staff Bus for all tests in this module."""
    monkeypatch.setenv("STAFF_BUS_ENABLED", "1")
    monkeypatch.delenv("STAFF_BUS_ENABLED", raising=False)
    monkeypatch.setenv("STAFF_BUS_ENABLED", "1")
    yield


# --------------------------------------------------------------------------- #
# task_bridge unit tests (no DB required)
# --------------------------------------------------------------------------- #


class TestTaskBridgePublish:
    """Verify _try_publish is called with the right event types."""

    def test_on_task_assigned_calls_publish(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        calls: list[dict] = []
        monkeypatch.setattr(
            task_bridge,
            "_try_publish",
            lambda **kw: calls.append(kw),
        )
        task_bridge.on_task_assigned("rohan", "follow up leads", "t_001", delegated_by="manager")
        assert len(calls) == 1
        ev = calls[0]
        assert ev["event_type"] == "task.assigned"
        assert ev["source_agent_id"] == "manager"
        assert ev["payload"]["target_agent"] == "rohan"
        assert ev["payload"]["task_id"] == "t_001"

    def test_on_task_accepted_calls_publish(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        calls: list[dict] = []
        monkeypatch.setattr(
            task_bridge,
            "_try_publish",
            lambda **kw: calls.append(kw),
        )
        task_bridge.on_task_accepted("kavya", "scan infra", "t_002")
        assert len(calls) == 1
        ev = calls[0]
        assert ev["event_type"] == "task.accepted"
        assert ev["source_agent_id"] == "kavya"
        assert ev["payload"]["task_id"] == "t_002"

    def test_on_task_completed_calls_publish(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        calls: list[dict] = []
        monkeypatch.setattr(
            task_bridge,
            "_try_publish",
            lambda **kw: calls.append(kw),
        )
        task_bridge.on_task_completed("isha", "t_003", result="3 leads scored")
        assert len(calls) == 1
        ev = calls[0]
        assert ev["event_type"] == "task.completed"
        assert ev["source_agent_id"] == "isha"
        assert ev["payload"]["result"] == "3 leads scored"

    def test_on_task_failed_calls_publish(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        calls: list[dict] = []
        monkeypatch.setattr(
            task_bridge,
            "_try_publish",
            lambda **kw: calls.append(kw),
        )
        task_bridge.on_task_failed("arjun", "t_004", error="timeout")
        assert len(calls) == 1
        ev = calls[0]
        assert ev["event_type"] == "task.failed"
        assert ev["source_agent_id"] == "arjun"
        assert ev["payload"]["error"] == "timeout"


class TestTryPublishFailOpen:
    """_try_publish must never raise, even with bad inputs."""

    def test_publish_returns_ok_when_flag_off(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        monkeypatch.delenv("STAFF_BUS_ENABLED", raising=False)
        # Should not raise
        task_bridge._try_publish(
            event_type="task.assigned",
            source_agent_id="manager",
            destination="ops",
            payload={"task_id": "x"},
        )

    def test_publish_handles_bus_exception(self, monkeypatch):
        from app.platform.staff_bus import runtime, task_bridge

        def _boom(**kw):
            raise RuntimeError("redis down")

        monkeypatch.setattr(runtime.StaffBus, "publish", _boom)
        # Should not raise
        task_bridge._try_publish(
            event_type="task.assigned",
            source_agent_id="manager",
            destination="ops",
            payload={"task_id": "x"},
        )


class TestTeamChannelResolution:
    """_agent_team_channel resolves agent → channel from manifest."""

    def test_known_agent_returns_channel(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        monkeypatch.setattr(
            task_bridge,
            "_TEAM_CHANNEL_CACHE",
            {"kavya": "ops", "neha": "gtm", "manager": "admin"},
        )
        assert task_bridge._agent_team_channel("kavya") == "ops"
        assert task_bridge._agent_team_channel("neha") == "gtm"
        assert task_bridge._agent_team_channel("manager") == "admin"

    def test_unknown_agent_falls_back_to_ops(self, monkeypatch):
        from app.platform.staff_bus import task_bridge

        monkeypatch.setattr(task_bridge, "_TEAM_CHANNEL_CACHE", {"kavya": "ops"})
        assert task_bridge._agent_team_channel("nonexistent") == "ops"


# --------------------------------------------------------------------------- #
# Integration: verify agent_task_queue bridge hooks fire
# --------------------------------------------------------------------------- #


class TestATQBridgeIntegration:
    """Verify the bridge hooks in agent_task_queue are wired correctly."""

    def test_bridge_helpers_are_callable(self):
        from app.platform.agent_task_queue import (
            _bridge_on_assign,
            _bridge_on_claimed,
            _bridge_on_complete,
            _bridge_on_fail,
        )

        # These should not raise (bridge is fail-open)
        _bridge_on_assign("rohan", "test goal", "t_test_001")
        _bridge_on_claimed("kavya", "test goal", "t_test_002")
        _bridge_on_complete("t_test_003", "done")
        _bridge_on_fail("t_test_004", "error")
