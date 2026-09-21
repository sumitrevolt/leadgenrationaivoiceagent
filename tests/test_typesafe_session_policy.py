from __future__ import annotations

import json
from types import SimpleNamespace

from app.platform.automation_orchestrator import TaskPriority, TaskRecord, TaskStatus
from app.platform.typesafe_integration import TypeSafeResponse
from app.platform.typesafe_session_policy import judge_task


def _record(payload=None):
    return TaskRecord(
        task_id="task-session-1",
        owner_bot="sales",
        assigned_agent="neha",
        priority=TaskPriority.HIGH,
        status=TaskStatus.READY,
        idempotency_key="task-session-1",
        input_payload=payload or {"tenant_id": "tenant-7", "objective": "private customer value"},
    )


class _FakeClient:
    enabled = True
    model = "jev-latest"

    def __init__(self, response):
        self.response = response
        self.states = []

    def system_one(self, state, questions, **kwargs):
        self.states.append((state, questions))
        self.kwargs = kwargs
        return self.response


def test_review_judgment_is_traced_without_payload_values(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_ENABLED", "1")
    client = _FakeClient(
        TypeSafeResponse(
            success=True,
            result={"answers": {"route": {"choice": "review"}, "material": {"noul": 0.91}}},
            model="jev-1.13.0",
        )
    )
    trace = tmp_path / "session.jsonl"

    verdict = judge_task(
        record=_record(),
        contract=SimpleNamespace(lane="GREEN"),
        client=client,
        trace_path=trace,
    )

    assert verdict["route"] == "review"
    assert verdict["traced"] is True
    assert client.kwargs == {
        "connect_timeout_sec": 2.0,
        "read_timeout_sec": 5.0,
        "max_attempts": 1,
    }
    state, _questions = client.states[0]
    assert state["payload_keys"] == ["objective", "tenant_id"]
    assert "private customer value" not in trace.read_text(encoding="utf-8")
    row = json.loads(trace.read_text(encoding="utf-8"))
    assert row["task_id"] == "task-session-1"
    assert row["resolved_model"] == "jev-1.13.0"


def test_provider_failure_degrades_to_proceed_and_is_traced(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_ENABLED", "1")
    client = _FakeClient(TypeSafeResponse(success=False, error="NETWORK", model="jev-latest"))

    verdict = judge_task(
        record=_record(),
        contract=SimpleNamespace(lane="GREEN"),
        client=client,
        trace_path=tmp_path / "session.jsonl",
    )

    assert verdict["route"] == "proceed"
    assert verdict["reason"] == "provider_fallback"
    assert verdict["traced"] is True


def test_provider_exception_is_bounded_and_traced(tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_ENABLED", "1")

    class RaisingClient(_FakeClient):
        def system_one(self, state, questions, **kwargs):
            raise TimeoutError("provider timed out")

    verdict = judge_task(
        record=_record(),
        contract=SimpleNamespace(lane="GREEN"),
        client=RaisingClient(TypeSafeResponse(success=False)),
        trace_path=tmp_path / "session.jsonl",
    )

    assert verdict["route"] == "proceed"
    assert verdict["reason"] == "provider_exception"
    assert verdict["traced"] is True


def test_existing_typesafe_flag_disables_session_policy(monkeypatch):
    monkeypatch.setenv("TYPESAFE_ENABLED", "0")

    verdict = judge_task(
        record=_record(),
        contract=SimpleNamespace(lane="GREEN"),
        client=_FakeClient(TypeSafeResponse(success=True)),
    )

    assert verdict["route"] == "proceed"
    assert verdict["reason"] == "policy_disabled"
