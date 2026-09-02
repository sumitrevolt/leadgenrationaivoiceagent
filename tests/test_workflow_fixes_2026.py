"""Workflow parity fixes — inquiry hooks, boot-grace, process revive, speed-to-lead."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_inquiry_hooks_runs_cadence_when_enabled(monkeypatch):
    monkeypatch.setenv("CADENCE_ENGINE", "1")
    monkeypatch.setenv("AUTO_CALLBACK_INQUIRY", "0")
    enroll_calls: list[dict] = []

    def _enroll(lead):
        enroll_calls.append(dict(lead))
        return {"id": "x", "status": "active"}

    with (
        patch("app.platform.lead_alerts.notify_new_lead_bg", lambda r: None),
        patch("app.api.public_site._notify_inquiry_email", new=AsyncMock()),
        patch("app.marketing.cadence.enroll", side_effect=_enroll),
    ):
        from app.platform.inquiry_hooks import run_after_inquiry

        rec = {
            "phone": "+919876543210",
            "business_name": "Test Biz",
            "niche": "solar",
            "city": "Mumbai",
            "source": "widget_chat",
            "at": "2026-06-19T10:00:00Z",
        }
        await run_after_inquiry(rec)
        # Await application-owned registry (determinism) — ownership lives in app.
        from app.platform.inquiry_hooks import await_inquiry_bg_tasks

        await await_inquiry_bg_tasks(timeout=5.0)
    assert enroll_calls
    assert enroll_calls[0]["source"] == "widget_chat"


def test_boot_grace_skips_qa_in_window(monkeypatch):
    from app.platform import boot_grace

    monkeypatch.setattr(boot_grace, "_WORKER_START", __import__("time").time())
    monkeypatch.setattr(
        boot_grace,
        "datetime",
        type(
            "DT",
            (),
            {
                "now": staticmethod(
                    lambda tz: type(
                        "HM",
                        (),
                        {"hour": 3, "minute": 0},
                    )()
                )
            },
        ),
    )
    assert boot_grace.should_skip_boot_grace("qa") is True
    assert boot_grace.should_skip_boot_grace("growth") is False
    ds = boot_grace.defer_seconds("qa")
    assert ds >= 120


def test_process_engine_ensure_alive_revives_stale():
    from app.agents import process_engine

    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = os.path.join(tmp, "process_runs")
        os.makedirs(runs_dir, exist_ok=True)
        run_id = "testrun123"
        with open(os.path.join(runs_dir, f"{run_id}.jsonl"), "w", encoding="utf-8") as f:
            f.write(
                '{"run_id":"testrun123","type":"run_started","data":{"process":"demo"},'
                '"at":"2020-01-01T00:00:00+00:00"}\n'
            )
        with open(os.path.join(runs_dir, "index.jsonl"), "w", encoding="utf-8") as f:
            f.write('{"run_id":"testrun123","process":"demo","at":"2020-01-01T00:00:00+00:00"}\n')

        with (
            patch.object(process_engine, "_RUNS_DIR", runs_dir),
            patch.object(process_engine, "_INDEX", os.path.join(runs_dir, "index.jsonl")),
            patch("app.tasks.staff_jobs.process_tick") as mock_tick,
        ):
            mock_tick.delay = lambda rid: {"queued": rid}
            out = process_engine.ensure_alive(stale_minutes=1)
        assert out.get("ok") is True
        assert "testrun123" in out.get("revived", [])


def test_dag_ensure_alive_skips_engine_mismatch(monkeypatch):
    """F-2: stale run whose engine_for is not dag must NOT enqueue process_tick."""
    from app.agents import dag_engine, process_engine

    monkeypatch.setattr(
        dag_engine,
        "list_runs",
        lambda limit=50: [{"run_id": "dagbad001", "status": "running"}],
    )
    monkeypatch.setattr(
        dag_engine,
        "_read_events",
        lambda _rid: [
            {
                "type": "run_started",
                "data": {"process": "flow:x"},
                "at": "2020-01-01T00:00:00+00:00",
            }
        ],
    )
    monkeypatch.setattr(
        "app.agents.flow_dispatch.engine_for",
        lambda _rid: process_engine,  # mismatch → skip revive
    )
    delayed: list[str] = []
    with patch("app.tasks.staff_jobs.process_tick") as mock_tick:
        mock_tick.delay = lambda rid: delayed.append(rid)
        out = dag_engine.ensure_alive(stale_minutes=1)
    assert out.get("ok") is True
    assert delayed == []
    assert "dagbad001" not in out.get("revived", [])


def test_speed_to_lead_callback_touch(tmp_path, monkeypatch):
    from app.platform import speed_to_lead as stl

    cb = tmp_path / "callback_touches.jsonl"
    monkeypatch.setattr(stl, "_CALLBACK_FILE", str(cb))
    stl.log_callback_touch("+919876543210", placed=True)
    ev = stl._evidence_epochs()
    assert "9876543210" in ev
    assert any(v[1] == "ai_callback" for v in ev["9876543210"])
