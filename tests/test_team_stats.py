"""team.stats() — per-agent success-rate rollup (degrade-detection KPI).

Pins the aggregation contract (success_rate = ok/total, last_run = max) and the
graceful no-DB path. Uses a fake DB so no real Postgres/AgentEvent rows needed —
the SQL GROUP BY tuples are simulated; we test the Python aggregation that turns
(member, status, count, last) rows into per-agent KPIs.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest


class _FakeQuery:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def filter(self, *a: Any, **k: Any) -> "_FakeQuery":
        return self

    def group_by(self, *a: Any, **k: Any) -> "_FakeQuery":
        return self

    def all(self) -> list[tuple[Any, ...]]:
        return self._rows


class _FakeDB:
    def __init__(self, rows: list[tuple[Any, ...]]) -> None:
        self._rows = rows

    def query(self, *a: Any, **k: Any) -> _FakeQuery:
        return _FakeQuery(self._rows)

    def close(self) -> None:
        pass


def test_team_stats_aggregates_success_rate(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import team

    rows = [
        ("isha", "ok", 8, datetime(2026, 6, 28, 7, 0, 0)),
        ("isha", "error", 2, datetime(2026, 6, 28, 6, 0, 0)),
        ("rohan", "ok", 5, datetime(2026, 6, 28, 10, 0, 0)),
    ]
    monkeypatch.setattr(team, "_db", lambda: _FakeDB(rows))

    out = team.stats(days=7)
    agents = {a["member"]: a for a in out["agents"]}

    assert agents["isha"]["total"] == 10
    assert agents["isha"]["ok"] == 8
    assert agents["isha"]["error"] == 2
    assert agents["isha"]["success_rate"] == 0.8  # 8/10
    assert agents["isha"]["last_run"] is not None
    assert agents["rohan"]["success_rate"] == 1.0  # 5/5

    assert out["overall"]["total"] == 15
    assert out["overall"]["ok"] == 13
    assert out["overall"]["success_rate"] == round(13 / 15, 3)
    assert out["overall"]["agent_count"] == 2


def test_team_stats_graceful_when_no_db(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.platform import team

    monkeypatch.setattr(team, "_db", lambda: None)
    out = team.stats(days=7)
    assert out == {"window_days": 7, "agents": [], "overall": {}}
