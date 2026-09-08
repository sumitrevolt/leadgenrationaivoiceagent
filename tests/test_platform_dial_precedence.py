"""platform_dial effective precedence — the "10 vs 100" cap question, pinned.

Task: prove which value actually reaches the daily 11:30 IST auto-dial loop when
``PLATFORM_DIAL_LIMIT=100`` is set in prod.

Chain (beat → scheduler → task → loop):
  worker.py beat "staff-platform-dial-daily" -> run_staff_job("platform_dial")
  team_scheduler._run_job_inner("platform_dial") -> _pd.enabled() gate, then
      ``_limit = _pd.dial_limit()`` -> send_task("app.tasks.calling.run_campaign_task",
      kwargs={"limit": _limit, ...})
  run_campaign_task(limit=...) -> _get_campaign_prospects(db, limit, niche)
      -> ``q.limit(max(1, min(limit, 200)))``

So the EFFECTIVE per-run cap is ``dial_limit()`` — env ``PLATFORM_DIAL_LIMIT``,
else data-file ``limit``, else ``_DEFAULT_LIMIT = 15`` — clamped to 1..200.

The "10" a reader may see is ``run_campaign_task``'s signature default
(``limit: int = 10``). The scheduler never relies on it: it passes
``dial_limit()`` explicitly. These tests pin that the default is dead on the
scheduler path and that env/file precedence is env-first.

See docs/dlq/DLQ_NO_REPLAY_PACKET_2026-08-08.md for the historical-dead-record
side of this workstream.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


def _chained_query_mock():
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = []
    db = MagicMock()
    db.query.return_value = q
    return db, q


# --------------------------------------------------------------------------- #
# dial_limit() precedence — env first, then file, then the 15 default
# --------------------------------------------------------------------------- #


def test_env_limit_wins_over_file(monkeypatch, tmp_path):
    import json

    from app.platform import platform_dial as pd

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": True, "limit": 10}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "100")
    # The daily path: prod sets 100; a stale data-file "10" must NOT win.
    assert pd.dial_limit() == 100


def test_file_limit_used_when_env_unset(monkeypatch, tmp_path):
    import json

    from app.platform import platform_dial as pd

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": True, "limit": 10}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.delenv("PLATFORM_DIAL_LIMIT", raising=False)
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    assert pd.dial_limit() == 10


def test_default_limit_is_15_not_10(monkeypatch):
    """The real fallback default is 15 (``_DEFAULT_LIMIT``), never the task-arg 10."""
    from app.platform import platform_dial as pd

    monkeypatch.delenv("PLATFORM_DIAL_LIMIT", raising=False)
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.setattr(pd, "_file_cfg", lambda: {})
    assert pd.dial_limit() == 15


def test_limit_clamped_1_200(monkeypatch):
    from app.platform import platform_dial as pd

    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "99999")
    assert pd.dial_limit() == 200
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "-5")
    assert pd.dial_limit() == 1
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "0")
    assert pd.dial_limit() == 1


def test_unparseable_limit_falls_back_to_default(monkeypatch):
    from app.platform import platform_dial as pd

    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "banana")
    assert pd.dial_limit() == 15


# --------------------------------------------------------------------------- #
# enabled() precedence — env boolean/number first, file only when env unset
# --------------------------------------------------------------------------- #


def test_env_count_turns_on_even_if_file_disabled(monkeypatch, tmp_path):
    """PLATFORM_DIAL_DAILY=100 (count) -> ON even when the file says disabled."""
    import json

    from app.platform import platform_dial as pd

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": False}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "100")
    assert pd.enabled() is True


def test_env_zero_is_hard_kill_switch_even_if_file_enabled(monkeypatch, tmp_path):
    import json

    from app.platform import platform_dial as pd

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": True}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    assert pd.enabled() is False


# --------------------------------------------------------------------------- #
# The daily path — scheduler passes dial_limit() explicitly, never the default
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_scheduler_sends_env_limit_not_the_task_default(monkeypatch):
    """The '10' default in run_campaign_task is dead on the scheduler path.

    With PLATFORM_DIAL_LIMIT=100 the beat-fired job must enqueue with
    kwargs['limit'] == 100 — proving the effective cap is dial_limit(), not the
    ``limit: int = 10`` signature default of run_campaign_task.
    """
    import app.tasks.calling as calling
    import app.worker as worker
    from app.platform import team, team_scheduler

    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "1")
    monkeypatch.setenv("PLATFORM_DIAL_LIMIT", "100")
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
    assert sent["kwargs"]["limit"] == 100


@pytest.mark.asyncio
async def test_scheduler_uses_file_limit_when_env_unset(monkeypatch, tmp_path):
    """No PLATFORM_DIAL_LIMIT -> the data-file cap (10) is what gets enqueued."""
    import json

    import app.tasks.calling as calling
    import app.worker as worker
    from app.platform import team, team_scheduler

    cfg = tmp_path / "platform_dial.json"
    cfg.write_text(json.dumps({"enabled": True, "limit": 10}))
    monkeypatch.setenv("PLATFORM_DIAL_CONFIG", str(cfg))
    monkeypatch.delenv("PLATFORM_DIAL_DAILY", raising=False)
    monkeypatch.delenv("PLATFORM_DIAL_LIMIT", raising=False)
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
    assert sent["kwargs"]["limit"] == 10


# --------------------------------------------------------------------------- #
# Loop layer — _get_campaign_prospects enforces max(1, min(limit, 200))
# --------------------------------------------------------------------------- #


def test_loop_clamps_high_env_limit_to_200():
    from app.tasks.calling import _get_campaign_prospects

    db, q = _chained_query_mock()
    _get_campaign_prospects(db, 200, "all")
    q.limit.assert_called_once_with(200)

    db, q = _chained_query_mock()
    _get_campaign_prospects(db, 99999, "all")
    q.limit.assert_called_once_with(200)


def test_loop_keeps_100_through_the_clamp():
    from app.tasks.calling import _get_campaign_prospects

    db, q = _chained_query_mock()
    _get_campaign_prospects(db, 100, "all")
    q.limit.assert_called_once_with(100)


def test_task_signature_default_is_10_but_scheduler_overrides():
    """Document the '10' source: the signature default — never reached on the
    scheduler path (team_scheduler always passes dial_limit() via kwargs)."""
    import inspect

    from app.tasks import calling

    src = inspect.getsource(calling.run_campaign_task)
    assert "limit: int = 10" in src
