"""listings_presence.get_status must return the NEWEST save even when two saves
share an updated_at timestamp (coarse-clock tie — e.g. Windows ~15ms tick).

Regression: get_status used sort(updated_at, reverse=True)[0]; on a timestamp tie
the stable sort kept append order and returned the OLDER record, so two rapid
status saves could surface a STALE status (real correctness bug, surfaced as a
full-suite test flake). Fix: ascending sort + last row (append order is
chronological) => newest always wins, tie or not.
"""

from app.marketing import listings_presence as lp


def test_latest_wins_on_timestamp_tie(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "_STATUS_FILE", str(tmp_path / "s.jsonl"))
    # Force BOTH saves to share an identical timestamp — the coarse-clock tie.
    monkeypatch.setattr(lp, "_now", lambda: "2026-06-20T00:00:00+00:00")

    r1 = lp.save_status("c1", {"google_business": True, "justdial": True})  # 2 dirs
    r2 = lp.save_status("c1", {"google_business": True})  # 1 dir — NEWER, must win

    got = lp.get_status("c1")
    assert got["ok"] is True
    # Despite identical updated_at, the most recent save wins:
    assert got["status"]["present"] == {"google_business": True}
    assert got["score"] == r2["saved"]["score"]
    assert r2["saved"]["score"] < r1["saved"]["score"]  # sanity: the two differ
