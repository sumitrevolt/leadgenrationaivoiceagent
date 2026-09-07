"""Hermetic tests for the local OmniRoute Docker memory guard."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import scripts.omniroute_self_healing_watchdog as wd


@pytest.fixture(autouse=True)
def _isolate_watchdog_log(monkeypatch, tmp_path):
    monkeypatch.setattr(wd, "WATCHDOG_LOG", tmp_path / "watchdog.log")
    monkeypatch.setattr(wd, "WATCHDOG_LOG_BACKUP", tmp_path / "watchdog.log.1")


def test_memory_bytes_parses_docker_units():
    assert wd._memory_bytes("1.5GiB") == int(1.5 * 1024**3)
    assert wd._memory_bytes("900MiB") == 900 * 1024**2
    assert wd._memory_bytes("bad") == 0


def test_memory_guard_accepts_bounded_headroom(monkeypatch):
    outputs = iter(
        [
            SimpleNamespace(returncode=0, stdout="2147483648\n"),
            SimpleNamespace(returncode=0, stdout="900MiB / 2GiB\n"),
        ]
    )
    monkeypatch.setattr(wd.subprocess, "run", lambda *args, **kwargs: next(outputs))
    assert wd.check_container_memory() is True


def test_memory_guard_rejects_unlimited_or_high_usage(monkeypatch):
    outputs = iter(
        [
            SimpleNamespace(returncode=0, stdout="0\n"),
            SimpleNamespace(returncode=0, stdout="1900MiB / 2GiB\n"),
        ]
    )
    monkeypatch.setattr(wd.subprocess, "run", lambda *args, **kwargs: next(outputs))
    assert wd.check_container_memory() is False


def test_watchdog_log_rotates_before_append(monkeypatch, tmp_path):
    log = tmp_path / "watchdog.log"
    backup = tmp_path / "watchdog.log.1"
    log.write_bytes(b"x" * wd.WATCHDOG_LOG_MAX_BYTES)
    monkeypatch.setattr(wd, "WATCHDOG_LOG", log)
    monkeypatch.setattr(wd, "WATCHDOG_LOG_BACKUP", backup)
    wd.log("rotation-test")
    assert backup.read_bytes() == b"x" * wd.WATCHDOG_LOG_MAX_BYTES
    assert "rotation-test" in log.read_text(encoding="utf-8")


def test_gateway_recovery_starts_only_stopped_container(monkeypatch):
    outputs = iter(
        [
            SimpleNamespace(returncode=0, stdout="false\n", stderr=""),
            SimpleNamespace(returncode=0, stdout="leadgen_omniroute\n", stderr=""),
        ]
    )
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return next(outputs)

    monkeypatch.setattr(wd, "_docker_binary", lambda: "docker")
    monkeypatch.setattr(wd.subprocess, "run", fake_run)
    assert wd.recover_stopped_gateway() is True
    assert calls[0][1:3] == ["inspect", "leadgen_omniroute"]
    assert calls[1][1:3] == ["start", "leadgen_omniroute"]


def test_gateway_recovery_does_not_restart_running_container(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stdout="true\n", stderr="")

    monkeypatch.setattr(wd, "_docker_binary", lambda: "docker")
    monkeypatch.setattr(wd.subprocess, "run", fake_run)
    assert wd.recover_stopped_gateway() is True
    assert len(calls) == 1
