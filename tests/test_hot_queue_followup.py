"""Hot Queue owner follow-up reminder contracts."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.platform import hot_queue_followup as followup


def _run(coro):
    return asyncio.run(coro)


def _card(*, hours_old: int) -> dict:
    return {
        "hq_id": f"hq-{hours_old}",
        "at": (datetime.now(timezone.utc) - timedelta(hours=hours_old)).isoformat(),
    }


def test_no_pending_cards_is_noop(monkeypatch):
    monkeypatch.setattr("app.platform.reply_agent.hot_queue", lambda **_kw: [])
    out = _run(followup.check_followup())
    assert out == {"status": "no_pending", "pending": 0, "stale": 0}


def test_only_stale_pending_cards_trigger_awaited_notification(monkeypatch):
    monkeypatch.setattr(
        "app.platform.reply_agent.hot_queue",
        lambda **_kw: [_card(hours_old=2), _card(hours_old=25), _card(hours_old=72)],
    )
    monkeypatch.setattr("app.integrations.ntfy.enabled", lambda: True)
    calls = []

    async def _push(title, message, **kwargs):
        calls.append((title, message, kwargs))
        return True

    monkeypatch.setattr("app.integrations.ntfy.push", _push)
    out = _run(followup.check_followup())

    assert out["status"] == "followup_sent"
    assert out["pending"] == 3
    assert out["stale"] == 2
    assert len(calls) == 1
    assert "2" in calls[0][1]


def test_notification_disabled_or_failed_is_not_reported_as_queued(monkeypatch):
    monkeypatch.setattr(
        "app.platform.reply_agent.hot_queue", lambda **_kw: [_card(hours_old=48)]
    )
    monkeypatch.setattr("app.integrations.ntfy.enabled", lambda: False)
    disabled = _run(followup.check_followup())
    assert disabled["status"] == "notification_disabled"

    monkeypatch.setattr("app.integrations.ntfy.enabled", lambda: True)

    async def _failed(*_args, **_kwargs):
        return False

    monkeypatch.setattr("app.integrations.ntfy.push", _failed)
    failed = _run(followup.check_followup())
    assert failed["status"] == "followup_failed"


def test_scheduler_dispatches_hot_queue_followup(monkeypatch):
    from app.platform import team_scheduler

    called = []

    async def _check():
        called.append(True)
        return {"status": "no_pending"}

    monkeypatch.setattr("app.platform.hot_queue_followup.check_followup", _check)
    assert _run(team_scheduler._run_job_inner("hot_queue_followup")) is True
    assert called == [True]
