"""W1.1 — scheduler single-instance lock must FAIL-CLOSED on a lock-fs error.

Old behaviour (bug): `_acquire_lock()` outer `except` set `_have_lock=True; return
True`. `_acquire_lock()` runs boot-once (single call site, `start_scheduler`), so if
BOTH uvicorn workers hit the same filesystem error (same disk) they BOTH started the
scheduler loop → every job double-fired (double emails/content/spend + ban risk).

Fail-closed: on a lock-fs error, claim NO lock (return False) so a broken-FS boot
skips the scheduler on this worker instead of double-firing. Loud warn log = the
recovery signal (there is no next-tick retry — acquire is boot-once).
"""

from __future__ import annotations

import os
from unittest import mock

import pytest

import app.platform.team_scheduler as ts


@pytest.fixture(autouse=True)
def _isolate_lock_state(monkeypatch, tmp_path):
    """Never touch the real data/.scheduler.lock; always start from a clean global."""
    monkeypatch.setattr(ts, "_LOCK_PATH", str(tmp_path / ".scheduler.lock"))
    saved = ts._have_lock
    ts._have_lock = False
    yield
    ts._have_lock = saved


def test_acquire_lock_fail_closed_on_fs_error():
    """A genuine lock-fs failure must NOT hand this worker the lock (fail-closed)."""
    with mock.patch("os.makedirs", side_effect=OSError("simulated lock-fs failure")):
        got = ts._acquire_lock()
    assert got is False, "lock-fs error must FAIL-CLOSED (no lock), not fail-open"
    assert ts._have_lock is False, "_have_lock must stay False after a fail-closed error"


def test_acquire_lock_succeeds_on_clean_fs(tmp_path):
    """Sanity: on a healthy FS the first caller acquires and writes its pid."""
    got = ts._acquire_lock()
    assert got is True
    assert ts._have_lock is True
    lock = tmp_path / ".scheduler.lock"
    assert lock.exists()
    assert lock.read_text().strip() == str(os.getpid())


# --------------------------------------------------------------------------- #
# Reclaim-path fail-closed (W1.1 backlog item): steal ONLY on a PROVEN-stale
# (old mtime = no heartbeat) or PROVEN-dead owner. An unreadable or empty lock
# file is NOT proof — an empty file is exactly the startup-race window between
# the other worker's os.open(O_EXCL) and os.write(pid). Stealing there put BOTH
# workers in the scheduler loop (double emails/content) with no FS error at all.
# --------------------------------------------------------------------------- #


def test_no_steal_on_unreadable_lock(tmp_path):
    """Existing lock whose mtime/content can't be READ must NOT be stolen.

    Only the read path is broken here (write still works), so the old code's
    `except: age, pid = 9999, 0` would "prove" staleness and successfully steal.
    """
    lock = tmp_path / ".scheduler.lock"
    lock.write_text("12345")
    real_open = open

    def read_broken_open(file, mode="r", *args, **kwargs):
        if "w" not in mode:
            raise OSError("unreadable")
        return real_open(file, mode, *args, **kwargs)

    with (
        mock.patch("os.path.getmtime", side_effect=OSError("unreadable")),
        mock.patch("builtins.open", side_effect=read_broken_open),
    ):
        got = ts._acquire_lock()
    assert got is False, "unreadable lock = no proof of stale/dead → must NOT steal"
    assert ts._have_lock is False


def test_no_steal_on_empty_fresh_lock(tmp_path):
    """Fresh empty lock = the other worker is mid-write (open→write race) → skip."""
    lock = tmp_path / ".scheduler.lock"
    lock.write_text("")
    got = ts._acquire_lock()
    assert got is False, "fresh empty lock must NOT be stolen (startup-race window)"
    assert ts._have_lock is False


def test_steal_on_proven_stale_mtime(tmp_path):
    """Reclaim still works: no heartbeat for > _LOCK_STALE_S → steal (even if empty)."""
    lock = tmp_path / ".scheduler.lock"
    lock.write_text("")
    old = lock.stat().st_mtime - (ts._LOCK_STALE_S + 60)
    os.utime(lock, (old, old))
    got = ts._acquire_lock()
    assert got is True, "proven-stale lock (crashed-mid-write owner) must be reclaimed"
    assert lock.read_text().strip() == str(os.getpid())


def test_steal_on_proven_dead_pid(tmp_path, monkeypatch):
    """Fresh mtime but the recorded owner pid is dead → steal immediately."""
    lock = tmp_path / ".scheduler.lock"
    lock.write_text("54321")
    monkeypatch.setattr(ts, "_pid_alive", lambda pid: False)
    got = ts._acquire_lock()
    assert got is True
    assert lock.read_text().strip() == str(os.getpid())


def test_no_steal_on_live_owner(tmp_path, monkeypatch):
    """Fresh lock owned by a live pid stays with its owner."""
    lock = tmp_path / ".scheduler.lock"
    lock.write_text("54321")
    monkeypatch.setattr(ts, "_pid_alive", lambda pid: True)
    got = ts._acquire_lock()
    assert got is False
    assert ts._have_lock is False
