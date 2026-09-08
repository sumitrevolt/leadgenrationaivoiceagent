"""A lease must expire in the FUTURE, on every host, in every timezone.

This is the test that was missing. The bug it pins was live and invisible:
`store.claim()` / `heartbeat()` / `recover_stale()` each took a naive UTC
datetime from `datetime.utcnow()` and called `.timestamp()` on it. Python
interprets a naive datetime as LOCAL time, so on the IST hosts this project runs
on every lease epoch landed 5h30m in the past. With a 45-minute TTL the stored
`lease_expiry` sat 4h45m BEHIND `last_heartbeat` — observed live on mission
msn_dcb0e15e8e8a4892 while it was still running.

Nothing caught it because the CAS backend compares `cur.until > now` with both
sides produced by the same shifted call, so the layer that would have detected
the error shared it. What actually broke was `Mission.lease_active()`, which
compares the rendered `lease_expiry` against a correct `utcnow()` — and so
reported EVERY live lease as expired, which is an invitation for a second runner
to claim a mission that is still executing.

The assertions below are deliberately about the observable contract (expiry is
after the heartbeat; a fresh lease is active; a live mission is not recoverable)
rather than about epoch arithmetic, because the arithmetic is what was wrong and
a test written in its terms would have agreed with it.
"""

from __future__ import annotations

import calendar
from datetime import datetime, timedelta, timezone

import pytest

from app.dev_control.external_agents import cas, store
from app.dev_control.external_agents.schema import Mission, MissionState, RiskClass

TTL = 2700  # 45 min — the value the live runner uses


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path, monkeypatch):
    monkeypatch.setenv("EXTERNAL_MISSION_DIR", str(tmp_path / "missions"))
    monkeypatch.setenv("EXTERNAL_MISSION_CAS", "filelock")
    monkeypatch.setenv("EXTERNAL_AGENT_COORDINATION_BACKEND", "local-file")
    cas.reset_backend()
    yield
    cas.reset_backend()


def _mission() -> Mission:
    m = Mission(
        mission_id="msn_leasetest0000",
        title="lease epoch",
        executor="cursor",
        reviewer="claude",
        risk_class=RiskClass.GREEN,
        idempotency_key="lease-epoch-test",
        allowed_paths=["tests/"],
        prohibited_paths=[".env"],
    )
    m.status = MissionState.RUNNING
    store.save(m)
    return m


def test_utc_epoch_interprets_a_naive_datetime_as_utc_not_local():
    """Host-timezone independent: compare against calendar.timegm, not .timestamp()."""
    dt = datetime(2026, 7, 28, 6, 35, 33)  # naive, holding UTC
    assert store._utc_epoch(dt) == pytest.approx(calendar.timegm(dt.timetuple()), abs=1)


def test_a_fresh_lease_expires_after_the_heartbeat_that_set_it():
    """The live symptom: expiry was 4h45m BEHIND last_heartbeat on an IST host."""
    m = _mission()
    assert store.claim(m.mission_id, "runner:test", ttl_s=TTL)["claimed"] is True
    got = store.get(m.mission_id)
    expiry = datetime.fromisoformat(got.lease_expiry)
    beat = datetime.fromisoformat(got.last_heartbeat)
    assert expiry > beat, f"lease_expiry {expiry} is not after last_heartbeat {beat}"
    # Approximate, not exact: `lease_expiry` derives from the CAS backend's epoch
    # and `last_heartbeat` from a separate `utcnow()` call, so they are sampled a
    # few hundred microseconds apart. Asserting equality here would be asserting
    # that two clock reads happen at the same instant.
    assert (expiry - beat).total_seconds() == pytest.approx(TTL, abs=5)


def test_a_fresh_lease_reads_as_active():
    """`lease_active()` compares the rendered expiry against a correct utcnow()."""
    m = _mission()
    store.claim(m.mission_id, "runner:test", ttl_s=TTL)
    assert store.get(m.mission_id).lease_active() is True


def test_heartbeat_keeps_the_lease_active_and_moves_expiry_forward():
    m = _mission()
    store.claim(m.mission_id, "runner:test", ttl_s=TTL)
    first = datetime.fromisoformat(store.get(m.mission_id).lease_expiry)
    assert store.heartbeat(m.mission_id, "runner:test", ttl_s=TTL) is True
    after = store.get(m.mission_id)
    assert after.lease_active() is True
    assert datetime.fromisoformat(after.lease_expiry) >= first


def test_a_live_mission_is_not_reclaimed_as_stale():
    """The consequence that matters: two runners in one worktree.

    With the shifted epoch every RUNNING mission looked unleased, so stale
    recovery would hand an actively-executing mission to a second runner.
    """
    m = _mission()
    store.claim(m.mission_id, "runner:test", ttl_s=TTL)
    assert [r for r in store.recover_stale() if r.get("mission_id") == m.mission_id] == []


def test_a_genuinely_expired_lease_IS_still_reclaimed():
    """Anti-vacuity: the fix must not disable recovery, only correct its clock."""
    m = _mission()
    store.claim(m.mission_id, "runner:test", ttl_s=1)
    future = datetime.utcnow() + timedelta(hours=1)
    recovered = store.recover_stale(now=future)
    assert [r for r in recovered if r.get("mission_id") == m.mission_id], recovered


def test_the_epoch_is_wrong_by_the_utc_offset_under_the_old_implementation():
    """Names the defect so a revert cannot pass silently.

    `.timestamp()` on a naive datetime differs from the correct UTC epoch by
    exactly the host's UTC offset. On a UTC host the difference is zero and this
    assertion is vacuous — which is precisely why the bug survived on machines
    where it mattered, so the test states that explicitly instead of pretending
    to prove something everywhere.
    """
    dt = datetime(2026, 7, 28, 6, 35, 33)
    naive_wrong = dt.timestamp()
    correct = store._utc_epoch(dt)
    offset = dt.astimezone().utcoffset() or timedelta(0)
    assert correct - naive_wrong == pytest.approx(offset.total_seconds(), abs=1)
    if offset.total_seconds() == 0:
        pytest.skip("host is UTC — this defect is invisible here by construction")
    assert correct != naive_wrong
