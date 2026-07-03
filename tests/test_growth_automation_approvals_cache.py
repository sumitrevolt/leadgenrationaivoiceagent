"""Regression test — Office HQ Approvals panel "click nahi hora" bug (2026-07-03).

Root cause: build_approvals()/build_approval_queue() is embedded in office_hq's
18s Redis-backed snapshot cache. Every OTHER office_hq mutation (pause/resume/
assign/next-action/move) calls office_hq.invalidate_snapshot_cache() after
writing, so the admin's own action is reflected on their very next fetch. The
three approve/reject decide endpoints reused from growth_automation.py (draft
decide, patch status, self-improve approve/reject) were never wired to that
same invalidation, so a decide would persist correctly but the Approvals panel
kept re-serving the stale cached queue for up to 18s — indistinguishable from
the click doing nothing.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.growth_automation import (
    DraftDecideIn,
    PatchStatusIn,
    approve_selfimprove_task,
    approvals_draft_decide,
    reject_selfimprove_task,
    upgrader_patch_status,
)

_USER = SimpleNamespace(email="admin@test.local")


@pytest.mark.asyncio
async def test_draft_decide_invalidates_office_snapshot_cache(monkeypatch):
    from app.platform import approvals_bridge, office_hq

    monkeypatch.setattr(
        approvals_bridge, "decide", lambda *a, **k: {"ok": True, "status": "approved"}
    )
    invalidate = AsyncMock()
    monkeypatch.setattr(office_hq, "invalidate_snapshot_cache", invalidate)

    result = await approvals_draft_decide(
        "coordinator", "x1", DraftDecideIn(decision="approve"), _user=_USER
    )

    assert result == {"ok": True, "status": "approved"}
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_status_invalidates_office_snapshot_cache(monkeypatch):
    from app.agents import code_upgrader
    from app.platform import office_hq

    monkeypatch.setattr(
        code_upgrader, "set_status", lambda *a, **k: {"ok": True, "status": "approved"}
    )
    invalidate = AsyncMock()
    monkeypatch.setattr(office_hq, "invalidate_snapshot_cache", invalidate)

    result = await upgrader_patch_status(
        "p1", PatchStatusIn(status="approved", note=""), _user=_USER
    )

    assert result == {"ok": True, "status": "approved"}
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_selfimprove_approve_invalidates_office_snapshot_cache(monkeypatch):
    from app.agents import self_improve
    from app.platform import office_hq

    fake_queue = SimpleNamespace(approve=lambda task_id: True)
    monkeypatch.setattr(self_improve, "_get_approval_queue", lambda: fake_queue)
    invalidate = AsyncMock()
    monkeypatch.setattr(office_hq, "invalidate_snapshot_cache", invalidate)

    result = await approve_selfimprove_task("t1", None, current_user=_USER)

    assert result == {"status": "approved", "task_id": "t1"}
    invalidate.assert_awaited_once()


@pytest.mark.asyncio
async def test_selfimprove_reject_invalidates_office_snapshot_cache(monkeypatch):
    from app.agents import self_improve
    from app.platform import office_hq

    fake_queue = SimpleNamespace(reject=lambda task_id, reason="": True)
    monkeypatch.setattr(self_improve, "_get_approval_queue", lambda: fake_queue)
    invalidate = AsyncMock()
    monkeypatch.setattr(office_hq, "invalidate_snapshot_cache", invalidate)

    from app.api.growth_automation import ApprovalActionIn

    result = await reject_selfimprove_task("t1", ApprovalActionIn(reason="nah"), current_user=_USER)

    assert result == {"status": "rejected", "task_id": "t1", "reason": "nah"}
    invalidate.assert_awaited_once()
