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
