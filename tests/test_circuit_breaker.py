"""Circuit breaker — gated pass-through + CLOSED→OPEN→HALF_OPEN→CLOSED transitions.

docs/GAP_ANALYSIS_SaaS_Infra_Upgrade_2026.md §3.3. Master gate CIRCUIT_BREAKER
(default OFF) = allow() ALWAYS True (zero behaviour change). Logic is in-memory,
never-raises. free_ai (LLM) has its own breaker; this is for the other externals.
"""

import pytest

import app.infrastructure.circuit_breaker as cb


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("CIRCUIT_BREAKER", raising=False)
    cb._REGISTRY.clear()
    yield
    cb._REGISTRY.clear()


def test_disabled_passthrough_never_blocks():
    # gate OFF (default): allow() True even after many failures (byte-identical behaviour)
    br = cb.get_breaker("svc", fail_threshold=2)
    for _ in range(10):
        br.record_failure()
    assert cb.enabled() is False
    assert br.allow() is True


def test_trips_open_after_threshold(monkeypatch):
    monkeypatch.setenv("CIRCUIT_BREAKER", "1")
    br = cb.get_breaker("svc", fail_threshold=3, reset_after_s=60)
    assert br.allow() is True
    br.record_failure()
    br.record_failure()
    assert br.allow() is True  # still below threshold
    br.record_failure()  # 3rd failure → trip
    assert br.state == "open"
    assert br.allow() is False  # fast-fail while OPEN


def test_half_open_then_close_on_success(monkeypatch):
    monkeypatch.setenv("CIRCUIT_BREAKER", "1")
    clock = {"t": 1000.0}
    monkeypatch.setattr(cb.time, "monotonic", lambda: clock["t"])
    br = cb.get_breaker("svc", fail_threshold=1, reset_after_s=30)
    br.record_failure()  # OPEN
    assert br.allow() is False
    clock["t"] += 31  # cooldown elapsed
    assert br.allow() is True  # one HALF_OPEN trial granted
    assert br.state == "half_open"
    assert br.allow() is False  # only half_open_max=1 trial
    br.record_success()
    assert br.state == "closed"
    assert br.allow() is True


def test_half_open_failure_reopens(monkeypatch):
    monkeypatch.setenv("CIRCUIT_BREAKER", "1")
    clock = {"t": 0.0}
    monkeypatch.setattr(cb.time, "monotonic", lambda: clock["t"])
    br = cb.get_breaker("svc", fail_threshold=1, reset_after_s=10)
    br.record_failure()  # OPEN
    clock["t"] += 11
    assert br.allow() is True  # HALF_OPEN trial
    br.record_failure()  # trial fails → OPEN again
    assert br.state == "open"
    assert br.allow() is False


def test_success_resets_failures(monkeypatch):
    monkeypatch.setenv("CIRCUIT_BREAKER", "1")
    br = cb.get_breaker("svc", fail_threshold=3)
    br.record_failure()
    br.record_failure()
    br.record_success()
    assert br.state == "closed"
    assert br.snapshot()["fails"] == 0


def test_registry_same_instance():
    a = cb.get_breaker("dup")
    b = cb.get_breaker("dup")
    assert a is b
    assert any(s["name"] == "dup" for s in cb.all_breakers())
