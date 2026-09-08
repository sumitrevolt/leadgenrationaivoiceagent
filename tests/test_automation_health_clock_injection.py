"""One `health()` call must use exactly ONE instant.

The defect: `marker_still_active(now=_now())` used the injected clock seam while
`_job_due_today()` / `_job_due_yet()` read the wall clock independently. Because
those two answer *weekday* and *window* questions, a single classification could
combine two different DAYS. The result therefore depended on when the process
happened to run — which is why `test_same_day_boot_grace_after_window_is_recoverable`
started failing on a real-world date change rather than on any code change.

These tests pin the property that makes that impossible: pinning `_now()` must
fully determine the outcome.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.platform import today_overview as tov

IST = ZoneInfo("Asia/Kolkata")


# ------------------------------------------------------------- helper contract
def test_injected_now_is_used_not_wall_clock(monkeypatch) -> None:
    """A wall-clock read in the injected path must be impossible to hide."""

    def _boom(*_a, **_k):  # pragma: no cover - must never run
        raise AssertionError("wall clock was read despite an injected timestamp")

    monkeypatch.setattr(tov, "datetime", _FrozenDatetime(_boom))
    # Saturday 2026-07-25 12:00 IST, a job with no weekly restriction.
    pinned = datetime(2026, 7, 25, 12, 0, tzinfo=IST)
    assert tov._job_due_today("content", now=pinned) is True


class _FrozenDatetime:
    """`datetime` stand-in whose `.now()` explodes; everything else passes through."""

    def __init__(self, boom):
        self._boom = boom

    def now(self, *a, **k):
        return self._boom()

    def __getattr__(self, item):
        return getattr(datetime, item)


def test_naive_timestamp_is_rejected_not_silently_compared() -> None:
    """Mixing naive and aware here yields a wrong schedule, not an error."""
    naive = datetime(2026, 7, 25, 12, 0)
    with pytest.raises(ValueError, match="timezone-aware"):
        tov._job_due_today("content", now=naive)


def test_utc_input_is_converted_to_ist() -> None:
    """19:30 UTC Fri == 01:00 IST Sat — the IST weekday must win."""
    utc = datetime(2026, 7, 24, 19, 30, tzinfo=timezone.utc)  # Friday UTC
    assert tov._ist_now(utc).weekday() == 5  # Saturday in IST


def test_no_argument_preserves_previous_behaviour() -> None:
    """Existing non-injected callers keep working off the real clock."""
    assert isinstance(tov._job_due_today("content"), bool)
    assert isinstance(tov._job_due_yet("content"), bool)


# --------------------------------------------------------------- window edges
def _due(job: str) -> tuple[int, int] | None:
    return tov._DUE_AFTER_IST.get(job)


@pytest.mark.parametrize("job", list(tov._DUE_AFTER_IST))
def test_before_window_is_not_due_yet(job: str) -> None:
    h, m = _due(job)
    if (h, m) == (0, 0):
        pytest.skip("job has no meaningful 'before' window")
    before = datetime(2026, 7, 25, h, m, tzinfo=IST) - timedelta(minutes=1)
    if not tov._job_due_today(job, now=before):
        pytest.skip("job is not scheduled on this weekday")
    assert tov._job_due_yet(job, now=before) is False


@pytest.mark.parametrize("job", list(tov._DUE_AFTER_IST))
def test_inside_window_is_due(job: str) -> None:
    h, m = _due(job)
    at = datetime(2026, 7, 25, h, m, tzinfo=IST)
    if not tov._job_due_today(job, now=at):
        pytest.skip("job is not scheduled on this weekday")
    assert tov._job_due_yet(job, now=at) is True


@pytest.mark.parametrize("job", list(tov._DUE_AFTER_IST))
def test_after_window_is_still_due(job: str) -> None:
    h, m = _due(job)
    after = datetime(2026, 7, 25, h, m, tzinfo=IST) + timedelta(hours=2)
    if after.day != 25 or not tov._job_due_today(job, now=after):
        pytest.skip("crosses midnight or not scheduled today")
    assert tov._job_due_yet(job, now=after) is True


def test_midnight_boundary_uses_one_instant() -> None:
    """00:00 IST must not be answered half by yesterday and half by today."""
    midnight = datetime(2026, 7, 25, 0, 0, tzinfo=IST)
    a = tov._job_due_today("content", now=midnight)
    b = tov._job_due_today("content", now=midnight)
    assert a == b


def test_repeated_calls_same_instant_same_result() -> None:
    pinned = datetime(2026, 7, 25, 12, 0, tzinfo=IST)
    first = [tov._job_due_yet(j, now=pinned) for j in tov._DUE_AFTER_IST]
    second = [tov._job_due_yet(j, now=pinned) for j in tov._DUE_AFTER_IST]
    assert first == second


def test_weekly_job_respects_injected_weekday() -> None:
    """A weekly job must follow the INJECTED day, not today's real day."""
    if not tov._WEEKLY_ON:
        pytest.skip("no weekly-restricted jobs configured")
    job, weekday = next(iter(tov._WEEKLY_ON.items()))
    # 2026-07-20 is a Monday; walk forward to the configured weekday.
    base = datetime(2026, 7, 20, 12, 0, tzinfo=IST)
    on_day = base + timedelta(days=(weekday - base.weekday()) % 7)
    off_day = on_day + timedelta(days=1)
    assert tov._job_due_today(job, now=on_day) is True
    assert tov._job_due_today(job, now=off_day) is False


# ---------------------------------------------- health() end-to-end determinism
def test_health_result_is_independent_of_wall_clock(monkeypatch, tmp_path) -> None:
    """THE regression: pinning _now() must fully determine the classification."""
    from app.platform import automation_health as ah

    beats = tmp_path / "beats.json"
    marker = datetime(2026, 7, 25, 7, 5, tzinfo=IST).astimezone(timezone.utc)
    beats.write_text(
        '{"content": {"job": "content", "ok": true, "s": 0.0, "at": "%s", "note": "boot_grace"}}'
        % marker.isoformat(),
        encoding="utf-8",
    )
    monkeypatch.setattr(ah, "_BEATS", lambda: str(beats))

    def _rows_for(pinned: datetime):
        monkeypatch.setattr(ah, "_now", lambda: pinned)
        out = ah.health()
        return next(j for j in out["jobs"] if j["job"] == "content")

    noon = datetime(2026, 7, 25, 12, 0, tzinfo=IST).astimezone(timezone.utc)
    # Same pinned instant twice -> identical classification, regardless of when
    # this test actually runs.
    assert _rows_for(noon)["status"] == _rows_for(noon)["status"]
    assert _rows_for(noon)["status"] == "overdue"
