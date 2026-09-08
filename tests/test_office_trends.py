"""W4.2 — Office HQ made trend-aware: day-over-day pipeline momentum.

The Office snapshot was rich but purely point-in-time (next_best_actions, boss_brief,
priority_actions… all "right now"). `build_trends` adds momentum — hot/warm/stuck vs the
most recent prior day — so the founder sees direction, not just a number. Fully
try-wrapped/fail-open (never blanks the page); derived-metrics history persisted like the
existing revenue_snapshots pattern.
"""

from __future__ import annotations

import datetime as _dt
import json

from app.platform import office_hq


def test_build_trends_day_over_day(monkeypatch, tmp_path):
    p = tmp_path / "office_trends.json"
    monkeypatch.setattr(office_hq, "_TRENDS_PATH", str(p))
    monkeypatch.setattr(office_hq, "_now", lambda: _dt.datetime(2026, 7, 6, 12, 0, 0))
    p.write_text(json.dumps({"2026-07-05": {"hot": 5, "warm": 10, "stuck": 2}}), encoding="utf-8")

    snap = {"pipeline": [{"hot_count": 8, "warm_count": 6, "stuckCount": 3}, {"stuckCount": 2}]}
    res = office_hq.build_trends(snap)

    assert res["asof"] == "2026-07-06"
    d = res["day_over_day"]
    assert d["hot"] == {"now": 8, "prev": 5, "delta": 3}
    assert d["warm"] == {"now": 6, "prev": 10, "delta": -4}
    assert d["stuck"] == {"now": 5, "prev": 2, "delta": 3}  # 3 + 2 stuck across stages
    hist = json.loads(p.read_text(encoding="utf-8"))
    assert hist["2026-07-06"] == {"hot": 8, "warm": 6, "stuck": 5}  # today persisted


def test_build_trends_no_history_prev_zero(monkeypatch, tmp_path):
    monkeypatch.setattr(office_hq, "_TRENDS_PATH", str(tmp_path / "t.json"))
    monkeypatch.setattr(office_hq, "_now", lambda: _dt.datetime(2026, 7, 6))
    res = office_hq.build_trends({"pipeline": [{"hot_count": 4, "stuckCount": 1}]})
    assert res["day_over_day"]["hot"]["delta"] == 4  # no prior day → prev 0
    assert res["day_over_day"]["stuck"]["now"] == 1


def test_build_trends_never_raises_on_bad_input(monkeypatch, tmp_path):
    monkeypatch.setattr(office_hq, "_TRENDS_PATH", str(tmp_path / "t.json"))
    assert office_hq.build_trends({}) == {} or "day_over_day" in office_hq.build_trends({})
    assert isinstance(office_hq.build_trends(None), dict)  # never raises
