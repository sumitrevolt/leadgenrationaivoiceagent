"""Loop-social-14 (2026-07-11): Phase 8 completeness — backoff, per-platform
QPM rate limit, stale-job recovery.
"""

from __future__ import annotations

import datetime
import time

import pytest

from app.social_engine import scheduling as sch


def test_backoff_ladder_ascends_and_caps():
    assert sch.next_retry_delay(0) == 30
    assert sch.next_retry_delay(1) == 60
    assert sch.next_retry_delay(2) == 120
    assert sch.next_retry_delay(5) == 1800
    assert sch.next_retry_delay(50) == 3600  # capped


def test_next_ready_at_zero_for_non_retry():
    assert sch.next_ready_at({"status": "queued"}) == 0.0
    assert sch.next_ready_at({"status": "published"}) == 0.0


def test_next_ready_at_for_retry_row():
    ts = "2026-07-11T10:00:00"
    when = sch.next_ready_at(
        {
            "status": "retry",
            "attempts": 2,
            "updated_at": ts,
        }
    )
    # attempts=2 → 120s backoff — should be exactly 120s past parsed ts.
    # Store writes UTC ISO; production parses naive-as-UTC so timestamp() is
    # timezone-safe on IST machines (see scheduling.next_ready_at).
    import datetime as _dt

    expected = _dt.datetime.fromisoformat(ts).replace(tzinfo=_dt.timezone.utc).timestamp() + 120
    assert when == pytest.approx(expected, abs=1)


def test_is_ready_for_retry_true_when_past():
    old = (datetime.datetime.utcnow() - datetime.timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%S")
    assert sch.is_ready_for_retry({"status": "retry", "attempts": 3, "updated_at": old}) is True


def test_is_ready_for_retry_false_when_within_backoff():
    now = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    assert sch.is_ready_for_retry({"status": "retry", "attempts": 3, "updated_at": now}) is False


# --------------------------------------------------------------------------- #
# Per-platform QPM                                                             #
# --------------------------------------------------------------------------- #
def test_qpm_allows_within_cap():
    sch._clear_qpm_state()
    for _ in range(3):
        ok, used, cap = sch.check_platform_qpm("x")
        assert ok is True
    assert used == 3
    assert cap == 5


def test_qpm_blocks_at_cap():
    sch._clear_qpm_state()
    for _ in range(5):
        sch.check_platform_qpm("x")
    ok, used, cap = sch.check_platform_qpm("x")
    assert ok is False
    assert used == 5
    assert cap == 5


def test_qpm_per_platform_isolation():
    sch._clear_qpm_state()
    for _ in range(5):
        sch.check_platform_qpm("x")
    # x is capped now but facebook is not affected.
    ok, _, _ = sch.check_platform_qpm("facebook")
    assert ok is True


# --------------------------------------------------------------------------- #
# Stale-job recovery                                                           #
# --------------------------------------------------------------------------- #
def test_recover_stale_processing(monkeypatch, tmp_path):
    from app.social_engine import store

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)

    jid = store.enqueue({"client_id": "c1", "platform": "facebook", "caption": "hi"})
    # Force processing with an old claimed_at.
    old_iso = (datetime.datetime.utcnow() - datetime.timedelta(minutes=30)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    store.mark(jid, "processing", claimed_at=old_iso)
    assert store.get(jid)["status"] == "processing"

    out = sch.recover_stale_processing(store, older_than_min=15)
    assert out["recovered"] == 1
    assert store.get(jid)["status"] == "queued"


def test_recover_leaves_recent_processing_alone(monkeypatch, tmp_path):
    from app.social_engine import store

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)

    jid = store.enqueue({"client_id": "c1", "platform": "facebook", "caption": "hi"})
    recent = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S")
    store.mark(jid, "processing", claimed_at=recent)

    out = sch.recover_stale_processing(store, older_than_min=15)
    assert out["recovered"] == 0
    assert store.get(jid)["status"] == "processing"
