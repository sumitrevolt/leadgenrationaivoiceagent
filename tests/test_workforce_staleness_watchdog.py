"""Tests for scripts/workforce_staleness_watchdog.py alert/recovery logic.

Hermetic: file mtimes are synthetic and ntfy is stubbed — no real daemon, no
network, no real state. These tests pin the state machine: fresh status never
alerts, stale status alerts exactly once (then keeps exit 1 without re-alert),
recovery clears state and sends a recovery ping, and a missing status file is
a distinct config-style failure (exit 2).
"""

from __future__ import annotations

import os

import pytest

import scripts.workforce_staleness_watchdog as wd

NOW = 1_800_000_000.0


def _touch(path, age_s: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"cycle": 1}', encoding="utf-8")
    os.utime(path, (NOW - age_s, NOW - age_s))


@pytest.fixture
def env(tmp_path):
    status = tmp_path / "runtime" / "workforce_live_status.json"
    state = tmp_path / "state" / "workforce_staleness_state.json"
    alerts = []
    sink = lambda title, body, priority="high": alerts.append((title, priority))  # noqa: E731
    return status, state, alerts, sink


class TestStalenessStateMachine:
    def test_fresh_status_never_alerts(self, env):
        status, state, alerts, sink = env
        _touch(status, age_s=30)
        assert wd.run_once([status], state, max_age_s=900, alert_sink=sink, now=NOW) == 0
        assert alerts == []

    def test_stale_alerts_once_then_exit_1_without_realert(self, env):
        status, state, alerts, sink = env
        _touch(status, age_s=1200)
        assert wd.run_once([status], state, max_age_s=900, alert_sink=sink, now=NOW) == 1
        assert len(alerts) == 1 and "STALE" in alerts[0][0]
        # Pass 2: still stale — exit stays 1, but NO second alert.
        assert wd.run_once([status], state, max_age_s=900, alert_sink=sink, now=NOW) == 1
        assert len(alerts) == 1

    def test_recovery_after_alert_sends_recovery_ping(self, env):
        status, state, alerts, sink = env
        _touch(status, age_s=1200)
        wd.run_once([status], state, max_age_s=900, alert_sink=sink, now=NOW)
        assert len(alerts) == 1
        # Orchestrator resumed writing — fresh file now.
        _touch(status, age_s=20)
        assert wd.run_once([status], state, max_age_s=900, alert_sink=sink, now=NOW) == 0
        assert len(alerts) == 2 and alerts[1][0].startswith("✅")
        assert wd._load_state(state)["alerted"] is False

    def test_missing_status_file_is_exit_2_with_alert(self, env, tmp_path):
        status, state, alerts, sink = env
        missing = tmp_path / "nowhere" / "workforce_live_status.json"
        assert wd.run_once([missing], state, max_age_s=900, alert_sink=sink, now=NOW) == 2
        assert len(alerts) == 1 and "MISSING" in alerts[0][0] and alerts[0][1] == "urgent"

    def test_newest_of_dual_writes_wins(self, env):
        status, state, alerts, sink = env
        old = status
        new = status.parent / "data" / "workforce_live_status.json"
        _touch(old, age_s=5000)  # would be stale alone
        _touch(new, age_s=30)  # fresh copy — newest wins
        assert wd.run_once([old, new], state, max_age_s=900, alert_sink=sink, now=NOW) == 0
        assert alerts == []


class TestCli:
    def test_main_one_shot_fresh_exits_zero(self, env, capsys):
        status, state, _alerts, _sink = env
        _touch(status, age_s=30)
        # Drive main() via argv to pin the CLI contract.
        import sys

        argv = sys.argv
        sys.argv = [
            "wd",
            "--status-file",
            str(status),
            "--state-file",
            str(state),
            "--max-age-s",
            "900",
        ]
        try:
            assert wd.main() == 0
        finally:
            sys.argv = argv
        assert "[OK]" in capsys.readouterr().out
