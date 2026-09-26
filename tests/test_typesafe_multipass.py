"""Tests for the TypeSafe multi-pass consumer (M00A + ADR-200).

Coverage targets:
  - 5 public stages (intake, plan, qa, final, outcome) all return trace records
  - ABSENT credential -> deterministic mock (same input -> same answer)
  - cache: second call within window returns result_kind="cached" with the
    SAME decision_id and zero new network traffic
  - disabled consumer -> all calls are kind="skipped" with value=None
  - live path is NEVER exercised by tests (no real API call); live mode is
    guarded by credential_state() == "PRESENT" and is tested only via the
    `_call_real` stubbing path which monkey-patches the canonical typesafe
    integration module
  - summary() aggregates by kind + stage
  - no API key is ever logged or stored (real or mock)
"""

from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

# Make repo root importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.platform import typesafe_integration as _ts  # noqa: E402
from app.platform import typesafe_multipass as _mp  # noqa: E402


# ---- helpers ---- #


class _FakeResponse:
    """Stand-in for `TypeSafeResponse` returned by `_ts.typesafe_system_one`."""

    def __init__(self, value: object, confidence: float, latency: float = 0.01, success: bool = True, error: str | None = None) -> None:
        self.success = success
        self._value = value
        self.confidence = confidence
        self.latency_sec = latency
        self.error = error
        self.attempts = 1
        self.model = "fake-jev"
        self.result = {"answers": {"ans_0": {"choice": value, "confidence": confidence}}, "model": "fake-jev"}

    @property
    def value(self) -> object:
        return self._value

    @property
    def has_answer(self) -> bool:
        return self._value is not None

    @property
    def answers(self) -> dict[str, object]:
        return {"ans_0": {"choice": self._value, "confidence": self.confidence}}


@pytest.fixture
def monkeypatch_credential_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force credential_state() to look like PRESENT for the duration of one test."""
    monkeypatch.setattr(
        _ts,
        "credential_state",
        lambda: {
            "state": "PRESENT",
            "enabled": True,
            "source": "env:TYPESAFE_API_KEY",
            "fingerprint": "abcdef012345",
            "model": "fake-jev",
            "pool_size": 1,
            "pool_fingerprints": ["abcdef012345"],
        },
    )


@pytest.fixture
def monkeypatch_credential_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force credential_state() to look like ABSENT."""
    monkeypatch.setattr(
        _ts,
        "credential_state",
        lambda: {"state": "ABSENT", "enabled": False, "source": "none", "fingerprint": "", "model": "fake-jev"},
    )


@pytest.fixture
def stub_real_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub the canonical real-call function so 'PRESENT' credential tests do NOT hit the network."""
    calls = {"count": 0}

    def fake_system_one(state: dict, questions: dict) -> _FakeResponse:
        calls["count"] += 1
        # Echo back a deterministic value derived from the question type
        for name, q in questions.items():
            if isinstance(q, _ts.Noul):
                return _FakeResponse(value=True, confidence=0.9)
            if hasattr(q, "criteria") and q.criteria:
                # criteria is a dict after init (Choice normalises list -> {k:k})
                first_value = next(iter(q.criteria.values()))
                return _FakeResponse(value=first_value, confidence=0.9)
        return _FakeResponse(value="default", confidence=0.5)

    monkeypatch.setattr(_ts, "typesafe_system_one", fake_system_one)
    monkeypatch.setattr(_ts, "_DEFAULT_MODEL", "fake-jev")


# ---- tests ---- #


def test_consumer_runs_all_stages_in_absent_mode(monkeypatch_credential_absent: None) -> None:
    """ABSENT credential -> every stage produces a `mock` trace record with a deterministic value."""
    cons = _mp.multipass_consumer(task_id="t-absent")

    intake = cons.intake_pass(evidence={"e": 1}, task="hello")
    plan = cons.plan_pass(task="hello", options=["a", "b"])
    qa = cons.qa_pass(artifact={"kind": "msg", "body": "hi"}, evidence_refs=["ref-1"])
    final = cons.final_pass(
        artifact={"kind": "msg", "body": "hi"},
        downstream_action="publish",
        evidence_refs=["ref-1"],
    )
    outcome = cons.outcome_pass(side_effect_id="se-1", observed_outcome="ok")

    for r in (intake, plan, qa, final, outcome):
        assert r.result_kind == "mock", f"{r.stage} expected mock, got {r.result_kind}"
        assert r.value is not None
        assert r.confidence == 0.5, "mock confidence is the explicit 0.5 placeholder"
        assert r.credential_fingerprint == "", "mock paths MUST NOT carry a credential fingerprint"
        assert r.error is None
        assert r.timestamp.endswith("Z")
        assert r.task_id == "t-absent"

    summary = cons.summary()
    assert summary["consumed_total"] == 5
    assert summary["mock_calls"] == 5
    assert summary["real_calls"] == 0
    assert summary["cached_calls"] == 0
    assert summary["skipped_calls"] == 0
    assert summary["by_stage"]["intake"] == 1
    assert summary["by_stage"]["plan"] == 1
    assert summary["by_stage"]["intermediate_qa"] == 1
    assert summary["by_stage"]["final"] == 1
    assert summary["by_stage"]["outcome"] == 1


def test_consumer_disabled_skips_all_calls(monkeypatch_credential_absent: None) -> None:
    cons = _mp.multipass_consumer(task_id="t-disabled", enabled=False)
    intake = cons.intake_pass(evidence={"e": 1}, task="hi")
    assert intake.result_kind == "skipped"
    assert intake.value is None
    assert intake.confidence == 0.5
    assert cons.summary()["skipped_calls"] == 1


def test_mock_is_deterministic(monkeypatch_credential_absent: None) -> None:
    """Same input -> same answer. Required for reproducibility of fixture replays."""
    c1 = _mp.multipass_consumer(task_id="t-det")
    c2 = _mp.multipass_consumer(task_id="t-det")
    e = {"evidence_size": 42}
    r1 = c1.intake_pass(evidence=e, task="t-det")
    r2 = c2.intake_pass(evidence=e, task="t-det")
    assert r1.value == r2.value
    assert r1.confidence == r2.confidence == 0.5


def test_cache_returns_same_decision_id(monkeypatch_credential_absent: None) -> None:
    """Re-running the same stage within cache_window must reuse the cached answer
    AND the original decision_id (audit continuity), with kind='cached'."""
    cons = _mp.multipass_consumer(task_id="t-cache", cache_window_sec=60)
    r1 = cons.plan_pass(task="t-cache", options=["x", "y"])
    r2 = cons.plan_pass(task="t-cache", options=["x", "y"])
    assert r1.result_kind == "mock"
    assert r2.result_kind == "cached"
    assert r1.decision_id == r2.decision_id
    assert r1.value == r2.value
    # Cache should NOT count toward consumed network traffic — summary "real_calls" + "mock_calls"
    # counts only the original emission; cached is its own bucket.
    assert cons.summary()["cached_calls"] == 1
    assert cons.summary()["mock_calls"] == 1


def test_present_credential_emits_real_kind(stub_real_call: None, monkeypatch_credential_present: None) -> None:
    """PRESENT credential + stubbed real call -> kind='real' with non-mock confidence."""
    cons = _mp.multipass_consumer(task_id="t-present")
    r = cons.plan_pass(task="t-present", options=["a", "b"])
    assert r.result_kind == "real"
    assert r.credential_fingerprint == "abcdef012345", "PRESENT calls MUST carry the credential fingerprint (sha256[:12])"
    assert r.confidence == 0.9
    assert r.request_latency_sec >= 0.0
    assert r.error is None
    assert r.value == "a"  # first value from criteria dict


def test_present_real_call_records_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the canonical client returns success=False, the trace records error and confidence=0.5."""
    def failing_system_one(state: dict, questions: dict) -> _FakeResponse:
        return _FakeResponse(value=None, confidence=0.5, success=False, error="rate limited")

    monkeypatch.setattr(_ts, "credential_state", lambda: {
        "state": "PRESENT", "enabled": True, "source": "env:TYPESAFE_API_KEY",
        "fingerprint": "deadbeef0000", "model": "fake-jev", "pool_size": 1,
        "pool_fingerprints": ["deadbeef0000"],
    })
    monkeypatch.setattr(_ts, "typesafe_system_one", failing_system_one)
    monkeypatch.setattr(_ts, "_DEFAULT_MODEL", "fake-jev")

    cons = _mp.multipass_consumer(task_id="t-fail")
    r = cons.plan_pass(task="t-fail", options=["x"])
    assert r.result_kind == "real"
    assert r.error == "rate limited"
    assert r.value is None
    assert r.confidence == 0.5


def test_no_api_key_is_logged_in_any_record(monkeypatch_credential_present: None, stub_real_call: None) -> None:
    """Even on the real path, the record NEVER carries the key, only its sha256[:12]."""
    cons = _mp.multipass_consumer(task_id="t-no-key")
    cons.intake_pass(evidence={"k": "v"}, task="t-no-key")
    cons.plan_pass(task="t-no-key", options=["x"])
    for r in cons.consumed_calls:
        d = r.to_dict()
        # The credential_fingerprint field is the ONLY allowed audit signal — and
        # it must be exactly the 12-char hex from credential_state() (never the key).
        if r.result_kind == "real":
            assert d["credential_fingerprint"] == "abcdef012345"
        else:
            assert d["credential_fingerprint"] == ""
        # Double-check no 'sk-' / hex 32+ run made it into any field
        for k, v in d.items():
            if isinstance(v, str) and v.startswith("sk-"):
                pytest.fail(f"API key leaked into field {k}: {v[:8]}...")


def test_record_round_trip_to_dict(monkeypatch_credential_absent: None) -> None:
    cons = _mp.multipass_consumer(task_id="t-round")
    r = cons.intake_pass(evidence={"x": 1}, task="t-round")
    d = r.to_dict()
    # Re-serialise to make sure JSON encoding doesn't blow up (audit consumer hook)
    encoded = json.dumps(d)
    decoded = json.loads(encoded)
    assert decoded["task_id"] == "t-round"
    assert decoded["stage"] == "intake"
    assert decoded["result_kind"] == "mock"


def test_state_hash_is_deterministic_across_calls(monkeypatch_credential_absent: None) -> None:
    cons1 = _mp.multipass_consumer(task_id="t-hash")
    cons2 = _mp.multipass_consumer(task_id="t-hash")
    r1 = cons1.plan_pass(task="x", options=["a", "b"])
    r2 = cons2.plan_pass(task="x", options=["a", "b"])
    assert r1.state_hash == r2.state_hash
    assert len(r1.state_hash) == 16  # sha256[:16]


def test_summary_counts_only_emitted_records(monkeypatch_credential_absent: None) -> None:
    cons = _mp.multipass_consumer(task_id="t-summary")
    # distinct sizes so the cache_key (which uses evidence_size) actually differs
    cons.intake_pass(evidence={"e": "a"}, task="x")
    cons.intake_pass(evidence={"e": "a"}, task="x")  # cached
    cons.intake_pass(evidence={"e": "abcdefghij"}, task="x")  # different size -> new mock
    s = cons.summary()
    assert s["consumed_total"] == 3
    assert s["mock_calls"] == 2
    assert s["cached_calls"] == 1
