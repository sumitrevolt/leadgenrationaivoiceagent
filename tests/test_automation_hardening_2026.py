"""Hermetic tests for automation/loop hardening (audit 2026-07-07).

Covers the concrete fixes made in this audit:
  - orchestrator_pipeline DND scrub is FAIL-CLOSED (CLAUDE.md §5): missing checker
    ya per-lead lookup error = promotional contact BLOCK (pehle fail-OPEN tha).
  - orchestrator_pipeline._within_calling_window IST-aware + explicit-now respect.
  - automation_health.health() additive `ok` key (team_pulse._kavya false-healthy fix)
    — `ok` MUST invert the degraded condition (overdue/queue-backlog).

Dependency-light by design: pipeline instance `object.__new__` se banta hai (heavy
dep builders skip), aur async method `asyncio.run` se drive hoti (no pytest-asyncio
dependency). Module import fail ho to `importorskip` skip — suite kabhi nahi tootegi.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import pytest


class _Lead:
    def __init__(self, phone):
        self.phone = phone


class _Result:
    def __init__(self):
        self.skipped_dnd = 0


def _bare_pipeline():
    """LeadGenPipeline instance BINA __init__ ke — sirf DND-scrub path chahiye,
    heavy builders (scraper/voice/telephony) na chalein."""
    op = pytest.importorskip("app.automation.orchestrator_pipeline")
    return object.__new__(op.LeadGenPipeline)


def test_calling_window_explicit_now():
    op = pytest.importorskip("app.automation.orchestrator_pipeline")
    P = op.LeadGenPipeline
    # Explicit `now` diya to as-is respect (tz-conversion nahi).
    assert P._within_calling_window(datetime(2026, 7, 7, 10, 0)) is True
    assert P._within_calling_window(datetime(2026, 7, 7, 2, 0)) is False  # 2 AM = illegal
    assert P._within_calling_window(datetime(2026, 7, 7, 22, 0)) is False
    # boundaries (09:00 / 21:00 inclusive)
    assert P._within_calling_window(datetime(2026, 7, 7, 9, 0)) is True
    assert P._within_calling_window(datetime(2026, 7, 7, 21, 0)) is True


def test_dnd_fail_closed_missing_checker():
    pipe = _bare_pipeline()
    pipe.dnd_checker = None  # checker unavailable
    res = _Result()
    leads = [_Lead("9876543210"), _Lead("9123456780"), _Lead(None)]
    kept = asyncio.run(pipe._stage_dnd_scrub(leads, res))
    assert kept == []  # §5: cannot prove non-DND => promotional contact blocked
    assert res.skipped_dnd == 2  # 2 phone-bearing leads blocked; phoneless not counted


def test_dnd_fail_closed_on_lookup_error():
    pipe = _bare_pipeline()

    class _Boom:
        async def check_single(self, phone):
            raise RuntimeError("DND API down")

    pipe.dnd_checker = _Boom()
    res = _Result()
    kept = asyncio.run(pipe._stage_dnd_scrub([_Lead("9876543210")], res))
    assert kept == []  # lookup fail => number BLOCKED (fail-closed, not allowed)
    assert res.skipped_dnd == 1


def test_automation_health_has_ok_key_inverting_degraded():
    ah = pytest.importorskip("app.platform.automation_health")
    h = ah.health()
    assert "ok" in h, "health() must expose additive `ok` boolean (false-healthy fix)"
    # ADR-104 Phase B (2026-07-15): `ok` also inverts dead/retryable_failed now
    # (previously only overdue/backlog — dead-letter tasks could sit unaddressed
    # while this claimed "healthy"). See automation_health.health() docstring.
    degraded = (
        bool(h.get("overdue"))
        or bool(h.get("queue_backlogged"))
        or bool(h.get("dead_tasks_present"))
        or bool(h.get("retryable_failed_present"))
    )
    assert h["ok"] is (not degraded)
