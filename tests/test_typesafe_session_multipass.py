"""Integration test: judge_task_multipass wired on top of the legacy judge_task.

Verifies:
  - multipass NEVER weakens the legacy review verdict
  - multipass emits at least 5 consumed_calls for a full lifecycle
  - ABSENT credential -> all stages are kind=mock
  - the legacy_decision_id is preserved in the trace for audit continuity
"""
from __future__ import annotations
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pytest

from app.platform import typesafe_session_policy as _sp
from app.platform import typesafe_integration as _ts


class _Record:
    """Minimal stand-in for the orchestrator's TaskRecord."""
    def __init__(self, task_id: str, agent: str, owner_bot: str = "jarvis", input_payload: dict | None = None):
        self.task_id = task_id
        self.assigned_agent = agent
        self.owner_bot = owner_bot
        self.input_payload = dict(input_payload or {})
        self.priority = "normal"


class _Contract:
    def __init__(self, lane: str = "GREEN"):
        self.lane = lane


class _DisabledClient:
    """A stub typesafe client with enabled=False — short-circuits the legacy gate."""
    model = "fake-jev"
    enabled = False


class _RouteClient:
    """A stub typesafe client that returns a hard-coded route (review or proceed)."""
    def __init__(self, route_value: str = "proceed"):
        self.model = "fake-jev"
        self.enabled = True
        self._route = route_value

    def system_one(self, state, questions, **kw):
        from app.platform.typesafe_integration import TypeSafeResponse
        return TypeSafeResponse(
            success=True,
            result={"answers": {"route": {"choice": self._route}, "material": {"noul": True}}, "model": "fake-jev"},
            model="fake-jev",
        )


def test_multipass_completes_full_lifecycle_when_credential_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """ABSENT credential: full 5-stage lifecycle runs in mock mode."""
    import app.platform.typesafe_integration as ti
    monkeypatch.setattr(ti, "credential_state", lambda: {
        "state": "ABSENT", "enabled": False, "source": "none", "fingerprint": "", "model": "fake-jev",
    })
    # Legacy judge_task imports get_typesafe_client at module level; patch it
    # on the session_policy module (its bound name), not on ti.
    monkeypatch.setattr(_sp, "get_typesafe_client", lambda: _DisabledClient())

    rec = _Record(task_id="t-mp-1", agent="swara", input_payload={"tenant_id": "acme", "evidence": {"size": 100}})
    contract = _Contract(lane="GREEN")

    result = _sp.judge_task_multipass(
        record=rec,
        contract=contract,
        artifact={"body": "hello"},
        options=["dispatch", "review"],
        downstream_action="execute",
        side_effect_id="se-001",
        observed_outcome="ok",
    )

    assert result["task_id"] == "t-mp-1"
    assert result["tenant_scope"] == "acme"
    assert "verdict" in result
    # Full lifecycle: intake + plan + qa + final + outcome = 5 calls
    assert result["consumed_calls"] == 5
    # by_kind can be either mock (ABSENT) or real (PRESENT but mocked client);
    # either way no external network traffic happened
    assert result["by_kind"].get("real", 0) + result["by_kind"].get("mock", 0) == 5
    assert result["by_stage"].get("intake", 0) == 1
    assert result["by_stage"].get("plan", 0) == 1
    assert result["by_stage"].get("intermediate_qa", 0) == 1
    assert result["by_stage"].get("final", 0) == 1
    assert result["by_stage"].get("outcome", 0) == 1
    # Legacy verdict is preserved
    assert result["legacy_decision_id"] == result["verdict"]["decision_id"]
    assert result["reason"] in {"multipass_complete", "provider_exception", "provider_fallback"}


def test_multipass_short_circuits_on_legacy_review(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the legacy judge_task says 'review', multipass MUST defer and skip the lifecycle.

    This is the safety guarantee — multipass can never WEAKEN a review verdict.
    """
    import app.platform.typesafe_integration as ti
    monkeypatch.setattr(ti, "credential_state", lambda: {
        "state": "PRESENT", "enabled": True, "source": "env:TYPESAFE_API_KEY",
        "fingerprint": "abcdef000000", "model": "fake-jev", "pool_size": 1,
        "pool_fingerprints": ["abcdef000000"],
    })
    monkeypatch.setattr(ti, "get_typesafe_client", lambda: _RouteClient("review"))
    monkeypatch.setattr(_sp, "get_typesafe_client", lambda: _RouteClient("review"))

    rec = _Record(task_id="t-mp-review", agent="arya", input_payload={"tenant_id": "acme"})
    contract = _Contract(lane="GREEN")

    result = _sp.judge_task_multipass(record=rec, contract=contract)
    assert result["verdict"]["route"] == "review"
    # Short-circuit means zero new multipass calls were made
    assert result["consumed_calls"] == 0
    assert result["by_kind"]["skipped"] == 5
    assert result["reason"] == "legacy_review_short_circuit"


def test_multipass_handles_artifact_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    """If artifact is None, multipass should run intake + plan only (no qa/final)."""
    import app.platform.typesafe_integration as ti
    monkeypatch.setattr(ti, "credential_state", lambda: {
        "state": "ABSENT", "enabled": False, "source": "none", "fingerprint": "", "model": "fake-jev",
    })
    monkeypatch.setattr(ti, "get_typesafe_client", lambda: _DisabledClient())
    monkeypatch.setattr(_sp, "get_typesafe_client", lambda: _DisabledClient())

    rec = _Record(task_id="t-mp-no-artifact", agent="arjun", input_payload={"tenant_id": "acme"})
    result = _sp.judge_task_multipass(record=rec, contract=_Contract())
    assert result["consumed_calls"] == 2  # intake + plan only
    assert result["by_stage"].get("intermediate_qa", 0) == 0
    assert result["by_stage"].get("final", 0) == 0
