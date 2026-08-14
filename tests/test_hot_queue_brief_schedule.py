"""Council-picked Hot Queue Revenue Brief scheduled-path contracts."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app.platform import office_briefing as ob

ROOT = Path(__file__).resolve().parents[1]


def _run(coro):
    return asyncio.run(coro)


def test_scheduled_brief_is_inert_when_flag_is_off(monkeypatch):
    monkeypatch.delenv("HOT_QUEUE_BRIEF_DAILY", raising=False)

    async def _must_not_build(*, force=False):  # pragma: no cover - assertion path
        raise AssertionError("disabled scheduled brief must not generate")

    monkeypatch.setattr(ob, "build_briefing", _must_not_build)

    out = _run(ob.run_scheduled())

    assert out == {"ok": True, "enabled": False, "skipped": "disabled"}


def test_scheduled_brief_skips_safely_when_automation_is_unhealthy(monkeypatch):
    """Fail-closed (no LLM) but do NOT report job failure → avoids DLQ death spiral."""
    monkeypatch.setenv("HOT_QUEUE_BRIEF_DAILY", "1")
    monkeypatch.setattr(
        ob,
        "_scheduler_health",
        lambda: {
            "ok": False,
            "status": "degraded",
            "overdue": ["ops"],
            "queue_backlogged": True,
        },
    )
    built = []
    events = []

    async def _fake_build(*, force=False):
        built.append(force)
        return {"ok": True}

    monkeypatch.setattr(ob, "build_briefing", _fake_build)
    monkeypatch.setattr(
        ob, "_log_scheduled_event", lambda status, detail: events.append((status, detail))
    )

    out = _run(ob.run_scheduled())

    assert out["ok"] is True
    assert out["skipped"] == "automation_unhealthy"
    assert out["health_status"] == "degraded"
    assert built == []
    assert events and events[0][0] == "warn"
    assert "ops" in events[0][1]


def test_scheduled_brief_reuses_daily_cache_and_notifies_owner_once(tmp_path, monkeypatch):
    from app.integrations import ntfy

    monkeypatch.setenv("HOT_QUEUE_BRIEF_DAILY", "true")
    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    monkeypatch.setattr(
        ob,
        "_scheduler_health",
        lambda: {"ok": True, "status": "healthy", "overdue": [], "queue_backlogged": False},
    )
    force_args = []
    events = []
    pushes = []

    async def _fake_build(*, force=False):
        force_args.append(force)
        return {
            "ok": True,
            "date": "2026-07-10",
            "text": "Hot Queue me 3 pending.",
            "cached": bool(force_args[1:]),
        }

    async def _fake_push(title, message, **kwargs):
        pushes.append((title, message, kwargs))
        return True

    monkeypatch.setattr(ob, "build_briefing", _fake_build)
    monkeypatch.setattr(
        ob, "_log_scheduled_event", lambda status, detail: events.append((status, detail))
    )
    monkeypatch.setattr(ntfy, "push", _fake_push)

    first = _run(ob.run_scheduled())
    second = _run(ob.run_scheduled())

    assert first["ok"] is True and second["ok"] is True
    assert force_args == [False, False]
    assert first["owner_notification"]["sent"] is True
    assert second["owner_notification"]["skipped"] == "already_notified"
    assert len(pushes) == 1
    assert pushes[0][2]["actions"][0]["url"].endswith("/app/inbox")
    assert all(status == "ok" for status, _detail in events)
    assert not hasattr(ob, "send_email")
    assert not hasattr(ob, "send_whatsapp")
    assert not hasattr(ob, "place_call")


def test_owner_notification_retries_then_releases_claim(tmp_path, monkeypatch):
    from app.integrations import ntfy

    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    pushes = []

    async def _failed_push(*args, **kwargs):
        pushes.append((args, kwargs))
        return False

    monkeypatch.setattr(ntfy, "push", _failed_push)

    out = _run(
        ob._notify_owner_once(
            {"date": "2026-08-14", "text": "Do payment follow-ups owner action me pending hain."}
        )
    )

    assert out == {"sent": False, "attempts": 2, "skipped": "notify_failed"}
    assert len(pushes) == 2
    assert not Path(ob._notification_path("2026-08-14")).exists()


@pytest.mark.parametrize(
    ("health", "expected_ok"),
    [
        (
            {
                "ok": True,
                "status": "healthy",
                "overdue": [],
                "queue_backlogged": False,
                "queue": {"celery": -1, "heavy": -1, "dlq": -1, "dead": -1},
                "jobs": [],
            },
            False,
        ),
        (
            {
                "ok": True,
                "status": "healthy",
                "overdue": [],
                "queue_backlogged": False,
                "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0},
                "jobs": [{"job": "ops", "status": "last_failed"}],
            },
            False,
        ),
        (
            {
                "ok": True,
                "status": "healthy",
                "overdue": [],
                "queue_backlogged": False,
                "queue": {"celery": 0, "heavy": 0, "dlq": 0, "dead": 0},
                "jobs": [{"job": "hot_queue_brief", "status": "last_failed"}],
            },
            True,
        ),
    ],
)
def test_scheduler_health_treats_unknown_queue_and_other_recent_failure_as_unsafe(
    monkeypatch, health, expected_ok
):
    from app.platform import automation_health

    monkeypatch.setattr(automation_health, "health", lambda: health)

    out = ob._scheduler_health()

    assert out["ok"] is expected_ok


def test_concurrent_builds_generate_once(tmp_path, monkeypatch):
    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    monkeypatch.setattr(
        ob,
        "_collect_numbers",
        lambda: {
            "overdue_jobs": 0,
            "failed_jobs": 0,
            "dlq_depth": 0,
            "hot_queue": 7,
            "new_leads": 0,
            "qualified_leads": 0,
            "top_agents": [],
        },
    )
    compose_calls = []

    async def _compose(_nums):
        compose_calls.append(1)
        await asyncio.sleep(0.05)
        return "Hot Queue me 7 pending."

    async def _tts(text, path):
        await asyncio.sleep(0.05)
        Path(path).write_bytes(b"audio")
        return True

    monkeypatch.setattr(ob, "_compose_text", _compose)
    monkeypatch.setattr(ob, "_tts_to_file", _tts)

    async def _both():
        return await asyncio.gather(ob.build_briefing(), ob.build_briefing())

    first, second = _run(_both())

    assert first["ok"] is True and second["ok"] is True
    assert len(compose_calls) == 1
    assert {bool(first.get("cached")), bool(second.get("cached"))} == {False, True}


def test_cache_write_failure_is_reported_and_claim_released(tmp_path, monkeypatch):
    from app.utils import file_lock

    monkeypatch.setattr(ob, "_DIR", str(tmp_path))
    monkeypatch.setattr(ob, "_collect_numbers", lambda: {})
    monkeypatch.setattr(file_lock, "locked_rewrite", lambda *_a, **_k: False)

    async def _compose(_nums):
        return "Hot Queue ready."

    async def _tts(_text, path):
        Path(path).write_bytes(b"audio")
        return True

    monkeypatch.setattr(ob, "_compose_text", _compose)
    monkeypatch.setattr(ob, "_tts_to_file", _tts)

    out = _run(ob.build_briefing(force=True))

    assert out["ok"] is False
    assert out["error"] == "briefing cache write failed"
    assert not Path(ob._claim_path(out["date"])).exists()


def test_run_job_returns_failure_for_celery_wrapper(monkeypatch):
    from app.platform import (
        automation_health,
        automation_log_service,
        scheduler_config,
        team_scheduler,
    )

    async def _failed(_job):
        return False

    monkeypatch.setattr(team_scheduler, "_run_job_inner", _failed)
    monkeypatch.setattr(scheduler_config, "is_enabled", lambda _job: True)
    monkeypatch.setattr(automation_health, "record_run", lambda *a, **k: None)
    monkeypatch.setattr(automation_log_service, "log_event", lambda *a, **k: "")

    out = _run(team_scheduler._run_job("hot_queue_brief"))

    assert out is False


def test_celery_wrapper_retries_reported_job_failure(monkeypatch):
    from app.platform import boot_grace
    from app.tasks import staff_jobs

    class RetryCalled(Exception):
        pass

    def _run_false(coro):
        coro.close()
        return False

    monkeypatch.setattr(boot_grace, "should_skip_boot_grace", lambda _job: False)
    monkeypatch.setattr(staff_jobs, "_run_async", _run_false)
    monkeypatch.setattr(
        staff_jobs.run_staff_job,
        "retry",
        lambda **_kwargs: (_ for _ in ()).throw(RetryCalled()),
    )

    with pytest.raises(RetryCalled):
        staff_jobs.run_staff_job.run("hot_queue_brief")


def test_hot_queue_brief_has_both_scheduler_paths_and_loop_passport():
    scheduler = (ROOT / "app/platform/team_scheduler.py").read_text(encoding="utf-8")
    staff_jobs = (ROOT / "app/tasks/staff_jobs.py").read_text(encoding="utf-8")
    worker = (ROOT / "app/worker.py").read_text(encoding="utf-8")
    health = (ROOT / "app/platform/automation_health.py").read_text(encoding="utf-8")
    boot_grace = (ROOT / "app/platform/boot_grace.py").read_text(encoding="utf-8")
    overview = (ROOT / "app/platform/today_overview.py").read_text(encoding="utf-8")
    flags = (ROOT / "app/api/automation_flags.py").read_text(encoding="utf-8")

    assert '"hot_queue_brief": None' in scheduler
    assert 'job == "hot_queue_brief"' in scheduler
    assert 'await _run_job("hot_queue_brief")' in scheduler
    assert '"hot_queue_brief"' in staff_jobs
    assert '"staff-hot-queue-brief-daily"' in worker
    assert '"args": ("hot_queue_brief",)' in worker
    assert '"hot_queue_brief": 30 * 60' in health
    assert '"hot_queue_brief": ((8, 15), (9, 15))' in boot_grace
    assert '"hot_queue_brief": (8, 15)' in overview
    assert '"HOT_QUEUE_BRIEF_DAILY"' in flags
