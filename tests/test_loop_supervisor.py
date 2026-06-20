"""Tests for loop_supervisor (SP3 single-loop SPOF hardening).

Pure-python: no network/DB/real-LLM. We monkeypatch the task object and the
ntfy/heartbeat sinks so nothing touches the outside world.
"""

from __future__ import annotations

import asyncio

import pytest

from app.platform import loop_supervisor as ls


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeTask:
    def __init__(self, *, done=False, cancelled=False, exc=None):
        self._done = done
        self._cancelled = cancelled
        self._exc = exc

    def done(self):
        return self._done

    def cancelled(self):
        return self._cancelled

    def exception(self):
        if self._cancelled:
            raise asyncio.CancelledError()
        return self._exc


class _State:
    pass


class _App:
    def __init__(self):
        self.state = _State()


class _FakeCM:
    def __init__(self):
        self.spawned = 0

    async def start_call_processor(self):
        self.spawned += 1
        # never returns in real life; here we just return so create_task finishes
        return None


@pytest.fixture(autouse=True)
def _quiet(monkeypatch):
    """Capture alerts + heartbeats instead of touching ntfy / disk."""
    alerts: list[tuple] = []
    beats: list[tuple] = []
    monkeypatch.setattr(ls, "_alert", lambda title, body, **kw: alerts.append((title, body)))
    monkeypatch.setattr(
        ls, "_heartbeat", lambda job, ok=True, note="": beats.append((job, ok, note))
    )
    # reset in-process cooldowns between tests
    ls._last_alert.clear()
    return {"alerts": alerts, "beats": beats}


# --------------------------------------------------------------------------- #
# enabled() flag gate
# --------------------------------------------------------------------------- #
def test_disabled_by_default(monkeypatch):
    monkeypatch.delenv("LOOP_SUPERVISOR", raising=False)
    assert ls.enabled() is False


def test_enabled_with_flag(monkeypatch):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    assert ls.enabled() is True


def test_ensure_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("LOOP_SUPERVISOR", raising=False)
    res = ls.ensure_call_processor_alive(_App())
    assert res == {"ok": True, "reason": "disabled"}


def test_boot_grace_noop_when_disabled(monkeypatch):
    monkeypatch.delenv("LOOP_SUPERVISOR", raising=False)
    res = ls.alert_boot_grace_skip("qa")
    assert res == {"alerted": False, "reason": "disabled"}


# --------------------------------------------------------------------------- #
# _task_is_dead_non_cancel
# --------------------------------------------------------------------------- #
def test_dead_detect_none():
    assert ls._task_is_dead_non_cancel(None) is True


def test_dead_detect_running():
    assert ls._task_is_dead_non_cancel(_FakeTask(done=False)) is False


def test_dead_detect_cancelled_is_not_dead():
    # cancellation = intentional shutdown, must NOT be treated as dead
    assert ls._task_is_dead_non_cancel(_FakeTask(done=True, cancelled=True)) is False


def test_dead_detect_errored():
    t = _FakeTask(done=True, exc=RuntimeError("boom"))
    assert ls._task_is_dead_non_cancel(t) is True


def test_dead_detect_returned():
    # finished cleanly (loop exited) = dead, needs re-spawn
    assert ls._task_is_dead_non_cancel(_FakeTask(done=True, exc=None)) is True


# --------------------------------------------------------------------------- #
# ensure_call_processor_alive
# --------------------------------------------------------------------------- #
def test_no_call_manager(monkeypatch):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    res = ls.ensure_call_processor_alive(_App())
    assert res["reason"] == "no_call_manager"


def test_alive_task_not_respawned(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    app = _App()
    cm = _FakeCM()
    app.state.call_manager = cm
    app.state.call_processor_task = _FakeTask(done=False)
    res = ls.ensure_call_processor_alive(app)
    assert res["reason"] == "alive"
    assert cm.spawned == 0
    assert any(b[0] == "call_processor" and b[1] is True for b in _quiet["beats"])


def test_no_running_loop_reports(monkeypatch):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    app = _App()
    app.state.call_manager = _FakeCM()
    app.state.call_processor_task = None  # dead
    # called from sync context => no running loop
    res = ls.ensure_call_processor_alive(app)
    assert res["reason"] == "no_running_loop"


@pytest.mark.asyncio
async def test_respawn_dead_task(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    app = _App()
    cm = _FakeCM()
    app.state.call_manager = cm
    app.state.call_processor_task = _FakeTask(done=True, exc=RuntimeError("died"))
    res = ls.ensure_call_processor_alive(app)
    assert res["reason"] == "respawned"
    # new task stored back on state
    assert app.state.call_processor_task is not None
    assert isinstance(app.state.call_processor_task, asyncio.Task)
    await app.state.call_processor_task  # let it finish
    assert cm.spawned == 1
    # alert fired (urgent re-spawn)
    assert any("re-spawned" in a[0] for a in _quiet["alerts"])


@pytest.mark.asyncio
async def test_respawn_alert_cooldown(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    app = _App()
    cm = _FakeCM()
    app.state.call_manager = cm

    # First dead -> respawn + alert
    app.state.call_processor_task = _FakeTask(done=True, exc=RuntimeError("x"))
    ls.ensure_call_processor_alive(app)
    t1 = app.state.call_processor_task
    await t1

    # Force dead again immediately -> respawn but alert suppressed by cooldown
    app.state.call_processor_task = _FakeTask(done=True, exc=RuntimeError("y"))
    ls.ensure_call_processor_alive(app)
    t2 = app.state.call_processor_task
    await t2

    assert cm.spawned == 2
    respawn_alerts = [a for a in _quiet["alerts"] if "re-spawned" in a[0]]
    assert len(respawn_alerts) == 1  # cooldown collapsed the 2nd


# --------------------------------------------------------------------------- #
# alert_boot_grace_skip
# --------------------------------------------------------------------------- #
def test_boot_grace_alert(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    res = ls.alert_boot_grace_skip("qa")
    assert res == {"alerted": True, "job": "qa"}
    assert any("Boot-grace skip" in a[0] and "qa" in a[0] for a in _quiet["alerts"])
    assert any(b[0] == "boot_grace_skip:qa" for b in _quiet["beats"])


def test_boot_grace_alert_cooldown(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    ls.alert_boot_grace_skip("blog")
    res2 = ls.alert_boot_grace_skip("blog")
    assert res2["reason"] == "cooldown"
    blog_alerts = [a for a in _quiet["alerts"] if "blog" in a[0]]
    assert len(blog_alerts) == 1


def test_boot_grace_distinct_jobs_both_alert(monkeypatch, _quiet):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    assert ls.alert_boot_grace_skip("qa")["alerted"] is True
    assert ls.alert_boot_grace_skip("content")["alerted"] is True


# --------------------------------------------------------------------------- #
# supervisor_loop cancellation
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_supervisor_loop_cancellable(monkeypatch):
    monkeypatch.setenv("LOOP_SUPERVISOR", "1")
    app = _App()
    app.state.call_manager = _FakeCM()
    app.state.call_processor_task = _FakeTask(done=False)
    task = asyncio.create_task(ls.supervisor_loop(app, interval_s=15))
    await asyncio.sleep(0.05)
    task.cancel()
    await task  # should exit cleanly, not raise
    assert task.done()
