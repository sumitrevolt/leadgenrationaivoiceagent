"""Governance guards (D2/D3) — INERT by default, enforce only when flag set.

These are the deferred-backlog hardening items shipped 2026-06-28. Each MUST be a
no-op unless its flag is explicitly enabled (the whole reason they were safe to ship
on a live platform). Tests pin both the INERT default and the enforcement.
"""

from __future__ import annotations

from typing import Any

import pytest


# --------------------------------------------------------------------------- #
# D2 — coordinator LLM rate-cap (COORDINATOR_LLM_CAP_PER_MIN)
# --------------------------------------------------------------------------- #
def test_coordinator_rate_cap_inert_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents import coordinator

    monkeypatch.delenv("COORDINATOR_LLM_CAP_PER_MIN", raising=False)
    coordinator._LLM_WINDOW.update({"start": 0.0, "count": 0.0})
    # No cap → never blocks, however many calls
    assert all(coordinator._llm_rate_ok() for _ in range(50))


def test_coordinator_rate_cap_enforces_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents import coordinator

    monkeypatch.setenv("COORDINATOR_LLM_CAP_PER_MIN", "2")
    coordinator._LLM_WINDOW.update({"start": 0.0, "count": 0.0})
    assert coordinator._llm_rate_ok() is True  # 1st
    assert coordinator._llm_rate_ok() is True  # 2nd
    assert coordinator._llm_rate_ok() is False  # 3rd — capped within the 60s window


# --------------------------------------------------------------------------- #
# D3 — DLQ queue-depth backpressure (QUEUE_DEPTH_BACKPRESSURE / QUEUE_DEPTH_CAP)
# --------------------------------------------------------------------------- #
class _FakeRedis:
    def __init__(self, depth: int) -> None:
        self._depth = depth

    def llen(self, key: str) -> int:
        return self._depth


def test_queue_flooded_inert_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import dlq_retry

    monkeypatch.delenv("QUEUE_DEPTH_BACKPRESSURE", raising=False)
    # Even a huge queue is NOT flooded when the guard is off
    assert dlq_retry._queue_flooded(_FakeRedis(999999)) is False


def test_queue_flooded_trips_above_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import dlq_retry

    monkeypatch.setenv("QUEUE_DEPTH_BACKPRESSURE", "1")
    monkeypatch.setenv("QUEUE_DEPTH_CAP", "800")
    assert dlq_retry._queue_flooded(_FakeRedis(801)) is True
    assert dlq_retry._queue_flooded(_FakeRedis(799)) is False


def test_queue_flooded_safe_on_redis_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import dlq_retry

    monkeypatch.setenv("QUEUE_DEPTH_BACKPRESSURE", "1")

    class _BadRedis:
        def llen(self, key: str) -> Any:
            raise RuntimeError("redis down")

    # Error reading depth must fail-open (not flooded) — never block the sweep on a glitch
    assert dlq_retry._queue_flooded(_BadRedis()) is False


def test_kb_share_flags_in_automation_registry() -> None:
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "COORD_KB_SHARE" in AUTOMATION_FLAGS
    assert "KB_SKILL_LEARN" in AUTOMATION_FLAGS


def test_coordinator_heartbeat_records_automation_health(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agents import coordinator
    from app.platform import automation_health as ah

    recorded: list[tuple] = []
    monkeypatch.setattr(
        ah,
        "record_run",
        lambda job, ok=True, seconds=0.0, note="", **_k: recorded.append((job, ok, note)),
    )
    coordinator._heartbeat("coordinate", True, 0.0, "test goal")
    assert recorded and recorded[0][0] == "coordinator" and recorded[0][1] is True
