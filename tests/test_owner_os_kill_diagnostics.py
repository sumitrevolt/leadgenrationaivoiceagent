"""Owner OS read-only diagnostics for the voice kill switch.

`kill_switch_board()` reported only a boolean. "engaged: false" reads the same
whether the operator deliberately disengaged it or the authority file is
missing — and those are very different situations for whoever is on call. The
board now carries source + reason alongside the existing flag.

Read-only: no set_kill, no ENV mutation, no file repair.
"""

from __future__ import annotations

import pytest

from app.platform import owner_os
from app.telephony import voice_launch as vl


@pytest.fixture
def kill_file(tmp_path, monkeypatch):
    p = tmp_path / "voice_launch_kill.json"
    monkeypatch.setenv("VOICE_LAUNCH_KILL_FILE", str(p))
    monkeypatch.delenv("VOICE_LAUNCH_KILL", raising=False)
    return p


def _entry():
    return owner_os.kill_switch_board()["voice_launch_kill"]


def test_env_true(kill_file, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "true")
    e = _entry()
    assert e["engaged"] is True
    assert e["source"] == "ENV"
    assert e["reason"] == "ENV_ENGAGED"


def test_env_false(kill_file, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "false")
    e = _entry()
    assert e["engaged"] is False
    assert e["source"] == "ENV"
    assert e["reason"] == "ENV_DISENGAGED"


def test_env_invalid_engages(kill_file, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "maybe")
    e = _entry()
    assert e["engaged"] is True
    assert e["reason"] == "INVALID_ENV_VALUE"


@pytest.mark.parametrize(
    ("payload", "engaged", "reason"),
    [
        ('{"kill": true}', True, "FILE_ENGAGED"),
        ('{"kill": false}', False, "FILE_DISENGAGED"),
        ('{"kill": tru', True, "MALFORMED"),
        ("{}", True, "INVALID_SCHEMA"),
    ],
)
def test_file_states(kill_file, payload, engaged, reason):
    kill_file.write_text(payload, encoding="utf-8")
    e = _entry()
    assert e["engaged"] is engaged
    assert e["source"] == "FILE"
    assert e["reason"] == reason


def test_missing_file_is_reported_as_missing_not_merely_disengaged(kill_file):
    """The whole point: "false" and "we cannot tell" must look different."""
    assert not kill_file.exists()
    e = _entry()
    assert e["engaged"] is True
    assert e["source"] == "FILE"
    assert e["reason"] == "MISSING"


def test_legacy_boolean_field_is_preserved(kill_file, monkeypatch):
    """Existing consumers read `engaged`; it must stay a real bool."""
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "1")
    e = _entry()
    assert "engaged" in e
    assert isinstance(e["engaged"], bool)
    assert e["can_toggle"] is True


def test_status_is_evaluated_once_per_snapshot(kill_file, monkeypatch):
    calls: list = []
    real = vl.admin_kill_status

    def spy():
        calls.append(1)
        return real()

    monkeypatch.setattr(vl, "admin_kill_status", spy)
    owner_os.kill_switch_board()
    assert calls == [1], f"status evaluated {len(calls)} times"


def test_board_never_leaks_raw_values(kill_file, monkeypatch):
    monkeypatch.setenv("VOICE_LAUNCH_KILL", "s3cr3t-token-value")
    blob = repr(owner_os.kill_switch_board())
    assert "s3cr3t-token-value" not in blob
    assert str(kill_file) not in blob
    assert "voice_launch_kill.json" not in blob
    assert ".tmp_kill" not in blob


def test_board_does_not_leak_file_contents(kill_file):
    kill_file.write_text('{"kill": false, "note": "internal-operator-note"}', encoding="utf-8")
    blob = repr(owner_os.kill_switch_board())
    assert "internal-operator-note" not in blob


def test_owner_os_never_uses_status_object_truthiness():
    """`bool(AdminKillStatus(engaged=False, ...))` is True — a real trap.

    AdminKillStatus deliberately has no __bool__, so any caller that tests the
    object instead of `.engaged` would report "engaged" forever.
    """
    import pathlib

    src = pathlib.Path(owner_os.__file__).read_text(encoding="utf-8")
    assert "bool(admin_kill_status()" not in src
    assert "if admin_kill_status()" not in src
    assert "bool(vl.admin_kill_status" not in src


def test_kill_switch_board_performs_no_mutation(kill_file, monkeypatch):
    """The DIAGNOSTIC surface is read-only.

    Owner OS does have a pre-existing operator toggle elsewhere that calls
    set_kill(); this batch neither added nor touched it. What must hold is that
    merely *rendering the board* never writes.
    """
    called: list = []
    monkeypatch.setattr(vl, "set_kill", lambda on: called.append(on) or True)
    owner_os.kill_switch_board()
    assert called == [], "rendering the board mutated the kill authority"
    assert not kill_file.exists()
