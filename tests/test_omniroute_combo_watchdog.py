"""Tests for scripts/omniroute_combo_watchdog.py strike/alert/recovery logic.

Hermetic: probes and ntfy are stubbed — no gateway, no network, no real state.
The live gateway path (real /v1/responses per combo) is exercised manually via
the script; these tests pin the state machine: 3 consecutive failures alert
exactly once, recovery clears state and sends a recovery ping, and a single
blip never alerts.
"""

from __future__ import annotations

import pytest

import scripts.omniroute_combo_watchdog as wd

COMBOS = ["leadsgen combo 1", "leadsgen combo 2", "leadsgen combo 3"]


def _ok(combo):
    return {"ok": True, "code": 200, "ms": 400, "error": None, "model": "nemotron-free"}


def _fail(combo, code=200, error="empty_output"):
    return {"ok": False, "code": code, "ms": 700, "error": error, "model": None}


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(wd, "STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setattr(wd, "discover_combos", lambda base, key: list(COMBOS))
    alerts = []
    monkeypatch.setattr(wd, "_alert", lambda title, body, priority="high": alerts.append((title, body)))
    return alerts


class TestWatchdogStateMachine:
    def test_single_blip_never_alerts(self, env, monkeypatch):
        calls = {"n": 0}

        def flaky(base, key, combo, timeout):
            calls["n"] += 1
            return _fail(combo) if calls["n"] == 1 else _ok(combo)

        monkeypatch.setattr(wd, "probe_combo", flaky)
        # Pass 1: one blip records a strike but stays below threshold.
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 0
        assert env == []
        # Pass 2: everything healthy → all strike counters reset to 0.
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 0
        assert env == []
        state = wd._load_state()
        assert all(s["fails"] == 0 for s in state.values())

    def test_three_consecutive_failures_alert_once_then_exit_1(self, env, monkeypatch):
        def only_down(b, k, c, t):
            return _fail(c) if c == "leadsgen combo 2" else _ok(c)

        monkeypatch.setattr(wd, "probe_combo", only_down)
        # Pass 1 and 2: strikes accumulate below threshold → exit 0, no alert.
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 0
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 0
        assert env == []
        # Pass 3: combo 2 hits 3 strikes → alert + exit 1.
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 1
        assert len(env) == 1
        assert "DOWN" in env[0][0]
        assert "leadsgen combo 2" in env[0][1]
        # Pass 4: still failing → already alerted, no re-alert (no spam).
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 1
        assert len(env) == 1

    def test_recovery_clears_state_and_alerts_recovered(self, env, monkeypatch):
        # Drive combo 2 down to 3 strikes first.
        monkeypatch.setattr(wd, "probe_combo", lambda b, k, c, t: _fail(c) if c == "leadsgen combo 2" else _ok(c))
        wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True)
        wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True)
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 1
        assert len(env) == 1

        # Combo 2 recovers → recovery alert, its state cleared; combo 1 now fails.
        monkeypatch.setattr(
            wd, "probe_combo", lambda b, k, c, t: _fail(c) if c == "leadsgen combo 1" else _ok(c)
        )
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 0
        assert len(env) == 2
        assert "recovered" in env[1][0].lower() or "recovered" in env[1][1].lower()
        state = wd._load_state()
        assert state["leadsgen combo 2"]["fails"] == 0
        assert state["leadsgen combo 2"]["alerted"] is False
        # Drive the new failure (combo 1) to threshold → exit 1 + its own alert.
        wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True)
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 1
        assert len(env) == 3
        assert "leadsgen combo 1" in env[2][1]

    def test_gateway_unreachable_exit_2_and_urgent_alert(self, env, monkeypatch):
        monkeypatch.setattr(wd, "discover_combos", lambda base, key: None)
        assert wd.run_once("http://x/v1", "k", 5, strikes=3, workers=2, quiet=True) == 2
        assert len(env) == 1
        assert "DOWN" in env[0][0]
