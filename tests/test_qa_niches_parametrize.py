"""W2.2 — QA agent's niche set is parametrized (was 3 hardcoded).

`run_qa()` (no args, how the scheduler calls it) tested only `SCRIPTS.keys()` — solar /
real_estate / insurance — so QA coverage of the actual client niches never widened
without a code change. Fix: `_qa_default_niches()` reads a comma-separated `QA_NICHES`
env (falling back to the 3 defaults); niches without a script already fall back to
`_GENERIC_TURNS`, so any niche is testable.
"""

from __future__ import annotations

import asyncio

import app.agents.staff as staff
from app.platform import team


def test_qa_default_niches_env_override(monkeypatch):
    monkeypatch.delenv("QA_NICHES", raising=False)
    assert staff._qa_default_niches() == list(staff.SCRIPTS.keys())
    monkeypatch.setenv("QA_NICHES", "gym, salon ,")
    assert staff._qa_default_niches() == ["gym", "salon"]  # trimmed, blanks dropped


def test_run_qa_honours_env_niches(monkeypatch):
    class _StubBrain:
        def __init__(self, niche=""):
            self.niche = niche

        async def reply(self, history, turn):
            return "theek hai ji, boliye kya chahiye"

    monkeypatch.setattr("app.voice_agent.telecaller_brain.TelecallerBrain", _StubBrain)
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    monkeypatch.setenv("QA_NICHES", "gym,salon")  # 2 niches, no scripts → 4 generic turns each

    res = asyncio.run(staff.run_qa())
    assert res.get("turns") == 8, "run_qa must test the env-configured niches, not the 3 defaults"
