"""W3.4 — team_pulse must complete quickly (regression guard for the full-suite hang).

The full suite historically hung in the team_pulse area (CLAUDE.md §3). The pytest
config already carries the safety net (`timeout = 120`, `timeout_method = "thread"` in
pyproject — a hang now FAILS instead of blocking CI forever). This adds a tight,
explicit guard: `team_pulse` runs cheap non-LLM monitors and must return a dict fast;
a 20s per-test cap turns any reintroduced blocking monitor into a fast failure.
"""

from __future__ import annotations

import pytest

from app.platform import team


@pytest.mark.timeout(20)
def test_team_pulse_returns_quickly_without_hanging():
    res = team.team_pulse(max_members=4)
    assert isinstance(res, dict)
    assert "pulsed" in res and isinstance(res["pulsed"], list)
