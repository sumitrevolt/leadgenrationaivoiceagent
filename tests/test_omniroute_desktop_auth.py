"""Honest readiness contracts for desktop OmniRoute authentication."""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.omniroute_self_healing_watchdog as watchdog


@pytest.fixture(autouse=True)
def _isolate_watchdog_log(monkeypatch, tmp_path):
    monkeypatch.setattr(watchdog, "WATCHDOG_LOG", tmp_path / "watchdog.log")
    monkeypatch.setattr(watchdog, "WATCHDOG_LOG_BACKUP", tmp_path / "watchdog.log.1")
    monkeypatch.setattr(watchdog, "DESKTOP_AUTH_STATE", tmp_path / "auth-state.json")


def _write_required_config(home: Path) -> None:
    config = home / "AppData" / "Roaming" / "Verdant" / "config.json"
    config.parent.mkdir(parents=True)
    config.write_text(
        '{"provider": {"apiKeyEnv": "OMNIROUTE_API_KEY"}}',
        encoding="utf-8",
    )


def test_desktop_auth_fails_closed_when_required_key_is_missing(monkeypatch, tmp_path):
    _write_required_config(tmp_path)
    monkeypatch.setattr(watchdog.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.delenv("OMNIROUTE_API_KEY", raising=False)

    assert watchdog.check_desktop_auth_readiness() is False


def test_desktop_auth_accepts_presence_without_reading_or_logging_value(monkeypatch, tmp_path):
    _write_required_config(tmp_path)
    monkeypatch.setattr(watchdog.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("OMNIROUTE_API_KEY", "test-presence-only")

    assert watchdog.check_desktop_auth_readiness() is True


def test_desktop_auth_missing_alerts_once_and_persists_state(tmp_path):
    alerts: list[tuple[str, str, str]] = []
    state_path = tmp_path / "auth-state.json"

    assert watchdog.record_desktop_auth_transition(
        False,
        state_path=state_path,
        alert_sink=lambda title, body, priority: alerts.append((title, body, priority)),
    ) is False
    assert watchdog.record_desktop_auth_transition(
        False,
        state_path=state_path,
        alert_sink=lambda title, body, priority: alerts.append((title, body, priority)),
    ) is False

    assert len(alerts) == 1
    assert alerts[0][2] == "urgent"
    assert '"alerted": true' in state_path.read_text(encoding="utf-8")


def test_desktop_auth_recovery_alerts_once_and_clears_state(tmp_path):
    alerts: list[tuple[str, str, str]] = []
    state_path = tmp_path / "auth-state.json"
    state_path.write_text('{"alerted": true, "fails": 3}', encoding="utf-8")

    assert watchdog.record_desktop_auth_transition(
        True,
        state_path=state_path,
        alert_sink=lambda title, body, priority: alerts.append((title, body, priority)),
    ) is True
    assert watchdog.record_desktop_auth_transition(
        True,
        state_path=state_path,
        alert_sink=lambda title, body, priority: alerts.append((title, body, priority)),
    ) is True

    assert len(alerts) == 1
    assert "recovered" in alerts[0][0].lower()
    assert alerts[0][2] == "default"
    assert '"alerted": false' in state_path.read_text(encoding="utf-8")


def test_desktop_auth_transition_never_exposes_credential_value(tmp_path):
    forbidden_marker = "".join(("must", "-never", "-appear"))
    alerts: list[tuple[str, str, str]] = []

    watchdog.record_desktop_auth_transition(
        False,
        state_path=tmp_path / "auth-state.json",
        alert_sink=lambda title, body, priority: alerts.append((title, body, priority)),
    )

    assert forbidden_marker not in repr(alerts)


def test_cycle_does_not_claim_all_healthy_when_desktop_auth_is_missing(monkeypatch):
    lines: list[str] = []
    monkeypatch.setattr(watchdog, "log", lines.append)
    monkeypatch.setattr(watchdog, "check_gateway_health", lambda: True)
    monkeypatch.setattr(watchdog, "check_container_memory", lambda: True)
    monkeypatch.setattr(
        watchdog,
        "verify_desktop_apps_configs",
        lambda: dict.fromkeys(
            ("hermes", "claude", "workbuddy", "openclaw", "verdant"), True
        ),
    )
    monkeypatch.setattr(watchdog, "check_desktop_auth_readiness", lambda: False)
    monkeypatch.setattr(watchdog, "check_canary_inference", lambda _combo: True)

    assert watchdog.run_cycle() is False
    assert any("DesktopAuth=False" in line and "ALL_HEALTHY=False" in line for line in lines)
