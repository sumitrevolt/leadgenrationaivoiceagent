"""Tests — team status 3-tier window + team_pulse heartbeat. Hermetic:
log_event + DB stubbed, monitors run real cheap fns (defensive). Never-raise.

FIX 2026-06-25: automation_health.health() DB call pe hang hota tha —
ab automation_health module hi stubbed hai (team_pulse ke _kavya call ko
rokkar). Isliye yeh test fast + deterministic hai.
"""

from __future__ import annotations

import pytest


@pytest.mark.timeout(10)  # 10s safety — agar hang bhi ho to fail fast
def test_team_pulse_logs_and_never_raises(monkeypatch):
    from app.platform import team

    logged: list[tuple] = []
    monkeypatch.setattr(
        team, "log_event", lambda m, a, d="", status="ok", meta=None: logged.append((m, a))
    )
    # team_status DB-dependent — stub recency to deterministic
    monkeypatch.setattr(
        team,
        "team_status",
        lambda: {
            "members": [
                {"key": "kavya", "last_active_mins": 500},
                {"key": "tara", "last_active_mins": 10},
                {"key": "arjun", "last_active_mins": None},
                {"key": "meera", "last_active_mins": 300},
            ]
        },
    )
    # FIX: _kavya monitor (nested fn) automation_health.health() ko call karta hai
    # jo ek DB call karta → offline test me HANG. Source ko hi stub karo (kavya
    # nested hai, usko directly monkeypatch nahi kar sakte).
    from app.platform import automation_health

    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"ok": True, "overdue": [], "never_ran": [], "jobs": []},
    )

    res = team.team_pulse(max_members=3)
    assert res["count"] >= 1 and res["count"] <= 3
    # least-recently-active (arjun None=1e9, kavya 500) pehle pulse hon
    pulsed = {m for m, _ in logged}
    assert "arjun" in pulsed or "kavya" in pulsed
    # har logged event ka action *_pulse hai
    assert all(a.endswith("_pulse") for _, a in logged)


@pytest.mark.timeout(10)  # 10s safety — agar hang bhi ho to fail fast
def test_team_pulse_monitor_failure_isolated(monkeypatch):
    from app.platform import team

    logged = []
    monkeypatch.setattr(
        team, "log_event", lambda m, a, d="", status="ok", meta=None: logged.append(m)
    )
    monkeypatch.setattr(team, "team_status", lambda: {"members": []})
    # ek monitor module import-fail kare to bhi baaki pulse hon (defensive _safe)
    res = team.team_pulse(max_members=6)
    assert isinstance(res, dict) and "pulsed" in res


@pytest.mark.timeout(10)
def test_arya_pulse_does_not_duplicate_mcp_health_prefix(monkeypatch):
    """Regression 2026-07-01: live feed showed "MCP health 90/100 · MCP health
    90/100 — all green" — _arya() was re-prepending "MCP health X/100 · " onto
    a summary string that already starts with the exact same phrase."""
    from app.platform import team

    logged: list[tuple] = []
    monkeypatch.setattr(
        team, "log_event", lambda m, a, d="", status="ok", meta=None: logged.append((m, a, d))
    )
    monkeypatch.setattr(
        team,
        "team_status",
        lambda: {"members": [{"key": "arya", "last_active_mins": None}]},
    )
    monkeypatch.setenv("MCP_ENGINEER", "1")

    from app.platform import automation_health, mcp_engineer

    monkeypatch.setattr(
        mcp_engineer,
        "health_score",
        lambda: {"score": 90.0, "summary": "MCP health 90/100 — all green"},
    )
    # _kavya (also in the rotation) hits automation_health.health() (DB) — stub
    # it so this test stays hermetic/fast, same as the file's other tests.
    monkeypatch.setattr(
        automation_health,
        "health",
        lambda: {"ok": True, "overdue": [], "never_ran": [], "jobs": []},
    )

    # max_members large enough to cover the whole rotation (23 monitors today)
    # regardless of tie-break order — every unlisted member defaults to the
    # SAME recency as arya here, and arya is last in the list literal.
    team.team_pulse(max_members=30)
    arya_events = [d for m, a, d in logged if m == "arya"]
    assert arya_events, "arya monitor did not fire"
    detail = arya_events[0]
    assert detail.count("MCP health") == 1, f"prefix duplicated: {detail!r}"
    assert detail == "MCP health 90/100 — all green"


def test_status_window_constants():
    from app.platform import team

    # working window ab 2-min se bada (realism), active-today bada offline-gate
    assert team._WORKING_AFTER_MIN >= 15
    assert team._ACTIVE_TODAY_MIN >= 8 * 60
    assert team._IDLE_AFTER_MIN == team._ACTIVE_TODAY_MIN  # backward-compat alias
