"""team._latest_events_per_member — the N+1 fix (Sentry PYTHON-S).

`team_status()` used to resolve "last activity" for every STAFF member with no
event today via `query(...).filter(member == m).first()` INSIDE A LOOP. STAFF has
31 members, so a quiet roster meant up to 31 round trips per
`GET /api/admin/agents` (1428ms transaction in prod). It degraded as the system
got QUIETER — the opposite of where anyone looks for a slow query.

These tests use a REAL in-memory SQLite session and COUNT the SQL statements
actually executed, because a fake DB cannot prove "one query instead of N" — the
query count IS the regression being pinned.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.models.agent_event import AgentEvent
from app.models.base import Base
from app.platform.team import _latest_events_per_member


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[AgentEvent.__table__])
    session = sessionmaker(bind=engine)()
    session.info["sql_count"] = 0

    @event.listens_for(engine, "before_cursor_execute")
    def _count(conn, cursor, statement, params, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            session.info["sql_count"] += 1

    try:
        yield session
    finally:
        session.close()


def _seed(db, member: str, n: int, base: datetime) -> None:
    """n events for `member`, oldest→newest, so .desc() has a clear winner."""
    for i in range(n):
        db.add(
            AgentEvent(
                id=f"{member}-{i}",
                member=member,
                action="event",
                detail=f"{member} event {i}",
                status="ok",
                created_at=base + timedelta(minutes=i),
            )
        )
    db.commit()


def test_returns_only_the_latest_event_per_member(db):
    base = datetime(2026, 7, 1, 10, 0, 0)
    _seed(db, "swara", 5, base)
    _seed(db, "arjun", 3, base)

    rows = _latest_events_per_member(db, AgentEvent, ["swara", "arjun"])

    by_member = {r.member: r for r in rows}
    assert set(by_member) == {"swara", "arjun"}
    # newest = highest index (created_at ascending in _seed)
    assert by_member["swara"].detail == "swara event 4"
    assert by_member["arjun"].detail == "arjun event 2"


def test_one_query_regardless_of_member_count(db):
    """THE pin: 10 members must cost ONE SELECT, not ten."""
    base = datetime(2026, 7, 1, 10, 0, 0)
    members = [f"m{i}" for i in range(10)]
    for m in members:
        _seed(db, m, 4, base)

    db.info["sql_count"] = 0
    rows = _latest_events_per_member(db, AgentEvent, members)

    assert len(rows) == 10, "one row per member"
    assert db.info["sql_count"] == 1, (
        f"N+1 regression: {db.info['sql_count']} SELECTs for {len(members)} members "
        "(the old per-member .first() loop would issue one each)"
    )


def test_the_old_loop_really_did_cost_n_queries(db, monkeypatch):
    """Proves the pin above DISCRIMINATES. The fallback path IS the pre-fix
    per-member loop, so forcing it must reproduce the N+1 (10 SELECTs for 10
    members). Without this, `sql_count == 1` could pass for the wrong reason
    (e.g. counter wired up wrong) and the regression pin would be decorative."""
    base = datetime(2026, 7, 1, 10, 0, 0)
    members = [f"m{i}" for i in range(10)]
    for m in members:
        _seed(db, m, 4, base)

    import sqlalchemy

    monkeypatch.setattr(
        sqlalchemy, "select", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("force fallback"))
    )

    db.info["sql_count"] = 0
    rows = _latest_events_per_member(db, AgentEvent, members)

    assert len(rows) == 10, "fallback must still be correct"
    assert db.info["sql_count"] == 10, (
        "the old per-member loop should issue one SELECT per member — if this is "
        "not 10, the sql counter is not measuring what the fix claims to improve"
    )


def test_empty_members_costs_nothing(db):
    db.info["sql_count"] = 0
    assert _latest_events_per_member(db, AgentEvent, []) == []
    assert db.info["sql_count"] == 0


def test_members_with_no_events_are_simply_absent(db):
    base = datetime(2026, 7, 1, 10, 0, 0)
    _seed(db, "swara", 2, base)

    rows = _latest_events_per_member(db, AgentEvent, ["swara", "ghost"])

    assert [r.member for r in rows] == ["swara"]


def test_falls_back_to_per_member_loop_when_window_path_breaks(db, monkeypatch):
    """Behaviour must be identical if the window query raises — the caller's
    best-effort contract predates this fix and must survive it."""
    base = datetime(2026, 7, 1, 10, 0, 0)
    _seed(db, "swara", 3, base)
    _seed(db, "arjun", 2, base)

    import sqlalchemy

    def _boom(*a, **k):
        raise RuntimeError("simulated window-function unavailability")

    monkeypatch.setattr(sqlalchemy, "select", _boom)

    rows = _latest_events_per_member(db, AgentEvent, ["swara", "arjun"])

    by_member = {r.member: r for r in rows}
    assert by_member["swara"].detail == "swara event 2"
    assert by_member["arjun"].detail == "arjun event 1"


def test_never_raises_when_everything_fails(db, monkeypatch):
    import sqlalchemy

    monkeypatch.setattr(
        sqlalchemy, "select", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x"))
    )

    class _DeadDB:
        def query(self, *a, **k):
            raise RuntimeError("db gone")

    assert _latest_events_per_member(_DeadDB(), AgentEvent, ["swara"]) == []
