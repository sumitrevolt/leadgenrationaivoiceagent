"""platform_dial — daily self-sale AI cold-call batch (Swara, gated PLATFORM_DIAL_DAILY).

6-layer wiring parity + gating behaviour + the niche-filter unlock in
run_campaign_task (platform campaigns can now dial the whole harvested pool
with niche="all" instead of only 'ai_marketing'-tagged leads).
"""

from unittest.mock import MagicMock

import pytest


def test_platform_dial_in_staff_jobs():
    from app.tasks.staff_jobs import STAFF_JOBS

    assert "platform_dial" in STAFF_JOBS


def test_platform_dial_in_scheduler_and_health():
    from app.platform import automation_health, team_scheduler

    assert "platform_dial" in team_scheduler._last_ran
    assert "platform_dial" in automation_health.EXPECTED_GAP_MIN


def test_platform_dial_in_worker_beat():
    from app.worker import celery_app

    beat = celery_app.conf.beat_schedule
    assert "staff-platform-dial-daily" in beat
    assert beat["staff-platform-dial-daily"]["args"] == ("platform_dial",)


def test_platform_dial_flag_registered():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "PLATFORM_DIAL_DAILY" in AUTOMATION_FLAGS


@pytest.mark.asyncio
async def test_platform_dial_noop_when_flag_off(monkeypatch, tmp_path):
    """Flag OFF (default, no config file) -> branch no-ops: no lock check, no enqueue."""
    import app.tasks.calling as calling
    from app.platform import team_scheduler

    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(tmp_path / "absent.json"))
    touched = {}
    monkeypatch.setattr(calling, "campaign_lock_held", lambda: touched.setdefault("lock", True))
    await team_scheduler._run_job("platform_dial")
    assert "lock" not in touched


def test_platform_dial_config_file_fallback(monkeypatch, tmp_path):
    """Env unset -> data-file enables (recreate-proof toggle); env '0' = hard kill."""
    import json

    from app.platform import platform_dial as pd

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": True, "limit": 9, "niche": "coaching"}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.delenv("PLATFORM_DIAL_LIMIT", raising=False)
    monkeypatch.delenv("PLATFORM_DIAL_NICHE", raising=False)
    assert pd.enabled() is True
    assert pd.dial_limit() == 9
    assert pd.dial_niche() == "coaching"
    # env explicit "0" beats the file — hard kill-switch
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    assert pd.enabled() is False
    # env limit/niche override the file when set
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "3")
    monkeypatch.setenv("PLATFORM_DIAL_NICHE", "all")
    assert pd.dial_limit() == 3
    assert pd.dial_niche() == "all"


@pytest.mark.asyncio
async def test_platform_dial_skips_when_lock_held(monkeypatch):
    """Campaign lock held (manual launch running) -> skip + visible warn event."""
    import app.tasks.calling as calling
    import app.worker as worker
    from app.platform import team, team_scheduler

    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.setattr(calling, "campaign_lock_held", lambda: True)
    sent: list = []
    events: list = []
    monkeypatch.setattr(worker.celery_app, "send_task", lambda *a, **k: sent.append(a))
    monkeypatch.setattr(team, "log_event", lambda *a, **k: events.append(a))
    await team_scheduler._run_job("platform_dial")
    assert sent == []
    assert any("platform_campaign" in str(e) for e in events)


@pytest.mark.asyncio
async def test_platform_dial_enqueues_campaign(monkeypatch):
    """Flag ON + lock free -> run_campaign_task queued with platform=True + env knobs."""
    import app.tasks.calling as calling
    import app.worker as worker
    from app.platform import team, team_scheduler

    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "7")
    monkeypatch.setenv("PLATFORM_DIAL_NICHE", "all")
    monkeypatch.setattr(calling, "campaign_lock_held", lambda: False)
    monkeypatch.setattr(calling, "acquire_campaign_lock", lambda ttl_s=400: True)
    sent: dict = {}
    monkeypatch.setattr(
        worker.celery_app,
        "send_task",
        lambda name, kwargs=None, **kw: sent.update({"name": name, "kwargs": kwargs}),
    )
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)
    await team_scheduler._run_job("platform_dial")
    assert sent["name"] == "app.tasks.calling.run_campaign_task"
    assert sent["kwargs"]["platform"] is True
    assert sent["kwargs"]["limit"] == 7
    assert sent["kwargs"]["niche"] == "all"
    assert sent["kwargs"]["dry_run"] is False


def _chained_query_mock():
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    db = MagicMock()
    db.query.return_value = q
    return db, q


def test_campaign_prospects_all_skips_niche_filter():
    """niche='all' -> no niche filter (2 base filters); real niche -> 3 filters."""
    from app.tasks.calling import _get_campaign_prospects

    db, q = _chained_query_mock()
    _get_campaign_prospects(db, 10, "all")
    assert q.filter.call_count == 2

    db, q = _chained_query_mock()
    _get_campaign_prospects(db, 10, "coaching")
    assert q.filter.call_count == 3


def test_platform_niche_override_in_source():
    """platform=True + explicit niche must override the ai_marketing default."""
    import inspect

    from app.tasks import calling

    src = inspect.getsource(calling.run_campaign_task)
    assert '(niche or "ai_marketing") if platform else niche' in src
