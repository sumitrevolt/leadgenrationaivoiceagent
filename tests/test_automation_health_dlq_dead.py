"""ADR-104 Phase B (2026-07-15) — automation_health.health()'s overall
status/ok must factor in dead/retryable_failed (dlq:dead / dlq:failed_tasks),
not just live-queue backlog.

Bug fixed: queue_depth() already tracked `dlq`/`dead` counts correctly, but
health()'s `backlogged`/`status`/`ok` computation only ever looked at
`celery`/`heavy` — meaning a Reliability Console reading straight off this
function could show "healthy"/ok=True while dlq:dead held retry-exhausted
tasks needing manual attention (the exact "at-a-glance said zero and
healthy, Reliability Console showed exhausted dead tasks" discrepancy).

These tests monkeypatch `queue_depth()` directly (no live Redis needed) and
isolate the heartbeat file via `_BEATS`, mirroring the existing pattern in
tests/test_infra_observability.py.
"""

from __future__ import annotations

import json

from app.platform import automation_health as ah


def _empty_beats(tmp_path, monkeypatch):
    monkeypatch.setattr(ah, "_BEATS", lambda: str(tmp_path / "beats.json"))
    with open(ah._BEATS(), "w", encoding="utf-8") as f:
        json.dump({}, f)
    monkeypatch.setattr(
        ah,
        "engine_skip_summary",
        lambda hours=48: {"total": 0, "by_engine": {}, "by_job": {}, "latest": []},
    )
    monkeypatch.setattr(ah, "stale_outputs", lambda: [])


def test_dead_tasks_present_marks_degraded_even_with_no_backlog(tmp_path, monkeypatch):
    """The exact regression case from the user's brief: retryable_failed=0,
    dead=4 (retry-exhausted, sitting in dlq:dead) — celery/heavy queues are
    empty (no backlog), yet this MUST be degraded/ok=False, not healthy."""
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 4})
    h = ah.health()
    assert h["dead_tasks_present"] is True
    assert h["retryable_failed_present"] is False
    assert h["ok"] is False
    assert h["status"] == "degraded"


def test_retryable_failed_present_marks_degraded(tmp_path, monkeypatch):
    """Terminal failures sitting in dlq:failed_tasks (awaiting dlq_retry sweep,
    or stuck because the sweep is disabled/deferred) must also degrade the
    verdict, independent of dead."""
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 3, "dead": 0})
    h = ah.health()
    assert h["dead_tasks_present"] is False
    assert h["retryable_failed_present"] is True
    assert h["ok"] is False
    assert h["status"] == "degraded"


def test_zero_dead_and_dlq_with_no_backlog_stays_healthy(tmp_path, monkeypatch):
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0})
    h = ah.health()
    assert h["dead_tasks_present"] is False
    assert h["retryable_failed_present"] is False
    assert h["ok"] is True
    # empty beats fixture => every job is "never_ran" (no heartbeat ever
    # recorded in this hermetic test) => "warming_up", not "healthy" — that's
    # correct/expected per health()'s own precedence (degraded > warming_up >
    # healthy); `ok` staying True is the actual thing this test is pinning.
    assert h["status"] in ("healthy", "warming_up")


def test_redis_unreachable_unknown_dlq_dead_does_not_falsely_degrade(tmp_path, monkeypatch):
    """-1 == "unknown" (Redis unreachable) must NOT be read as "dead present"
    — that would be a different false signal, not a fix. Absence of proof is
    not proof of absence, but it also must not fabricate an incident."""
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(
        ah, "queue_depth", lambda: {"celery": -1, "heavy": -1, "dlq": -1, "dead": -1}
    )
    h = ah.health()
    assert h["dead_tasks_present"] is False
    assert h["retryable_failed_present"] is False
    assert h["ok"] is True
    assert h["status"] in ("healthy", "warming_up")
    # ADR-114: surface unknown honestly so UI does not paint celery/dlq as 0.
    assert h["queue_available"] is False


def test_queue_available_true_when_redis_answers(tmp_path, monkeypatch):
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0})
    h = ah.health()
    assert h["queue_available"] is True


def test_both_dead_and_retryable_failed_present_still_single_degraded_status(tmp_path, monkeypatch):
    _empty_beats(tmp_path, monkeypatch)
    monkeypatch.setattr(ah, "queue_depth", lambda: {"celery": 0, "heavy": 0, "dlq": 2, "dead": 1})
    h = ah.health()
    assert h["dead_tasks_present"] is True
    assert h["retryable_failed_present"] is True
    assert h["ok"] is False
    assert h["status"] == "degraded"
