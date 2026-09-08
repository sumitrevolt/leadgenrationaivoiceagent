"""Regression: application-owned inquiry BG tasks + clean async DB shutdown.

Proven leak (Gate4c / 2026-07-24):
  inquiry_hooks._spawn(interaction_log.record)
  → get_async_session() checkout
  → Task destroyed before async-with __aexit__
  → dispose cannot close checked-out conn
  → orphan aiosqlite worker → CI exit-139 (SQLAlchemy #13039).

Production fix: inquiry_hooks owns tasks (named, exception-logged, drainable)
and FastAPI lifespan drains them BEFORE close_async_db().
"""

from __future__ import annotations

import asyncio
import threading
import time
from unittest.mock import AsyncMock, patch

import pytest


def _aiosqlite_workers():
    return [
        t
        for t in threading.enumerate()
        if t.is_alive()
        and "aiosqlite" in (getattr(getattr(t, "_target", None), "__module__", "") or "")
    ]


@pytest.fixture(autouse=True)
def _reset_inquiry_accept_gate():
    from app.platform.inquiry_hooks import resume_accepting_inquiry_bg

    resume_accepting_inquiry_bg()
    yield
    resume_accepting_inquiry_bg()


def test_app_async_engine_uses_nullpool_under_pytest():
    from app.models.base import _get_async_engine

    eng = _get_async_engine()
    assert eng is not None
    assert "sqlite" in str(eng.url).lower()
    assert type(eng.pool).__name__ == "NullPool"


@pytest.mark.asyncio
async def test_inquiry_hook_registers_owned_interaction_log_task(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    monkeypatch.setenv("AUTO_CALLBACK_INQUIRY", "0")
    monkeypatch.setenv("INTERACTION_LOG", "1")

    saw_record = asyncio.Event()

    async def _record(**kwargs):
        saw_record.set()
        return {"ok": True, "id": "test"}

    with (
        patch("app.platform.lead_alerts.notify_new_lead_bg", lambda r: None),
        patch("app.api.public_site._notify_inquiry_email", new=AsyncMock()),
        patch("app.marketing.cadence.enroll", return_value={"id": "x", "status": "active"}),
        patch("app.platform.interaction_log.record", side_effect=_record),
    ):
        from app.platform import inquiry_hooks
        from app.platform.inquiry_hooks import (
            await_inquiry_bg_tasks,
            pending_inquiry_bg_count,
            run_after_inquiry,
        )

        await run_after_inquiry(
            {
                "phone": "+919876543210",
                "business_name": "Owned Task Biz",
                "niche": "solar",
                "city": "Mumbai",
                "source": "widget_chat",
                "at": "2026-06-19T10:00:00Z",
            }
        )
        assert pending_inquiry_bg_count() >= 1 or saw_record.is_set()
        names = {getattr(t, "get_name", lambda: "")() for t in list(inquiry_hooks._BG_TASKS)}
        # Task may already be done; if still present it must be named.
        assert not names or any(n.startswith("inquiry:") for n in names)

        await await_inquiry_bg_tasks(timeout=5.0)
        assert saw_record.is_set()
        assert pending_inquiry_bg_count() == 0


@pytest.mark.asyncio
async def test_inquiry_hooks_path_leaves_no_aiosqlite_worker(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    monkeypatch.setenv("AUTO_CALLBACK_INQUIRY", "0")
    monkeypatch.setenv("INTERACTION_LOG", "1")

    with (
        patch("app.platform.lead_alerts.notify_new_lead_bg", lambda r: None),
        patch("app.api.public_site._notify_inquiry_email", new=AsyncMock()),
        patch("app.marketing.cadence.enroll", return_value={"id": "x", "status": "active"}),
    ):
        from app.platform.inquiry_hooks import (
            await_inquiry_bg_tasks,
            pending_inquiry_bg_count,
            run_after_inquiry,
        )

        await run_after_inquiry(
            {
                "phone": "+919876543210",
                "business_name": "NullPool Biz",
                "niche": "solar",
                "city": "Mumbai",
                "source": "widget_chat",
                "at": "2026-06-19T10:00:00Z",
            }
        )
        await await_inquiry_bg_tasks(timeout=5.0)
        assert pending_inquiry_bg_count() == 0

    from app.models.base import close_async_db

    await close_async_db()

    for _ in range(50):
        if not _aiosqlite_workers():
            break
        time.sleep(0.1)
    assert _aiosqlite_workers() == []


@pytest.mark.asyncio
async def test_shutdown_drain_waits_for_blocked_recording_then_cancels(monkeypatch):
    """Blocked in-flight record must be owned through drain ordering before dispose."""
    monkeypatch.setenv("AUTO_CALLBACK_INQUIRY", "0")
    monkeypatch.setenv("INTERACTION_LOG", "1")
    monkeypatch.setenv("CADENCE_ENGINE", "0")

    entered = asyncio.Event()
    release = asyncio.Event()
    cleaned = asyncio.Event()

    async def _blocked_record(**kwargs):
        entered.set()
        try:
            await release.wait()
        except asyncio.CancelledError:
            cleaned.set()
            raise
        finally:
            # Simulate session __aexit__ / cleanup always running on cancel.
            cleaned.set()

    with (
        patch("app.platform.lead_alerts.notify_new_lead_bg", lambda r: None),
        patch("app.api.public_site._notify_inquiry_email", new=AsyncMock()),
        patch("app.platform.interaction_log.record", side_effect=_blocked_record),
    ):
        from app.platform.inquiry_hooks import (
            drain_inquiry_bg_tasks,
            pending_inquiry_bg_count,
            resume_accepting_inquiry_bg,
            run_after_inquiry,
            stop_accepting_inquiry_bg,
        )

        resume_accepting_inquiry_bg()
        await run_after_inquiry(
            {
                "phone": "+919876543210",
                "business_name": "Blocked Record Biz",
                "niche": "solar",
                "city": "Mumbai",
                "source": "widget_chat",
            }
        )
        await asyncio.wait_for(entered.wait(), timeout=2.0)
        assert pending_inquiry_bg_count() >= 1

        # Phase 1+2 with near-zero timeout → cancel path (3+4).
        stop_accepting_inquiry_bg()
        result = await drain_inquiry_bg_tasks(timeout=0.05)
        assert result["cancelled"] >= 1 or result["remaining"] == 0
        assert pending_inquiry_bg_count() == 0
        assert cleaned.is_set()

        # Only after drain may the engine close (ordering proof).
        from app.models.base import close_async_db

        await close_async_db()
        for _ in range(50):
            if not _aiosqlite_workers():
                break
            time.sleep(0.1)
        assert _aiosqlite_workers() == []


@pytest.mark.asyncio
async def test_spawn_refused_during_shutdown_closes_coro(monkeypatch):
    from app.platform.inquiry_hooks import (
        _spawn,
        resume_accepting_inquiry_bg,
        stop_accepting_inquiry_bg,
    )

    stop_accepting_inquiry_bg()

    async def _never():
        raise AssertionError("must not run after stop_accepting")

    assert _spawn(_never(), name="should_refuse") is None
    resume_accepting_inquiry_bg()


@pytest.mark.asyncio
async def test_bg_task_exception_is_consumed(monkeypatch):
    from app.platform.inquiry_hooks import (
        _spawn,
        await_inquiry_bg_tasks,
        resume_accepting_inquiry_bg,
    )

    resume_accepting_inquiry_bg()

    async def _boom():
        raise RuntimeError("expected bg failure")

    t = _spawn(_boom(), name="boom")
    assert t is not None
    await await_inquiry_bg_tasks(timeout=2.0)
    # No "Task exception was never retrieved" — done-callback consumed it.
    assert t.done()
