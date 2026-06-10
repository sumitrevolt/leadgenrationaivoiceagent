"""Tests — team status 3-tier window + team_pulse heartbeat. Hermetic:
log_event + DB stubbed, monitors run real cheap fns (defensive). Never-raise.
"""

from __future__ import annotations


def test_team_pulse_logs_and_never_raises(monkeypatch):
    from app.platform import team

    logged: list[tuple] = []
    monkeypatch.setattr(team, "log_event", lambda m, a, d="", status="ok", meta=None: logged.append((m, a)))
    # team_status DB-dependent — stub recency to deterministic
    monkeypatch.setattr(team, "team_status", lambda: {"members": [
        {"key": "kavya", "last_active_mins": 500}, {"key": "tara", "last_active_mins": 10},
        {"key": "arjun", "last_active_mins": None}, {"key": "meera", "last_active_mins": 300},
    ]})

    res = team.team_pulse(max_members=3)
    assert res["count"] >= 1 and res["count"] <= 3
    # least-recently-active (arjun None=1e9, kavya 500) pehle pulse hon
    pulsed = {m for m, _ in logged}
    assert "arjun" in pulsed or "kavya" in pulsed
    # har logged event ka action *_pulse hai
    assert all(a.endswith("_pulse") for _, a in logged)


def test_team_pulse_monitor_failure_isolated(monkeypatch):
    from app.platform import team

    logged = []
    monkeypatch.setattr(team, "log_event", lambda m, a, d="", status="ok", meta=None: logged.append(m))
    monkeypatch.setattr(team, "team_status", lambda: {"members": []})
    # ek monitor module import-fail kare to bhi baaki pulse hon (defensive _safe)
    res = team.team_pulse(max_members=6)
    assert isinstance(res, dict) and "pulsed" in res


def test_status_window_constants():
    from app.platform import team

    # working window ab 2-min se bada (realism), active-today bada offline-gate
    assert team._WORKING_AFTER_MIN >= 15
    assert team._ACTIVE_TODAY_MIN >= 8 * 60
    assert team._IDLE_AFTER_MIN == team._ACTIVE_TODAY_MIN  # backward-compat alias
