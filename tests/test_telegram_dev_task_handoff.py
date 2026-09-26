from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.integrations.telegram_dev_task_handoff import run_canonical_handoff
from app.models.base import Base
from app.models.dev_task import DevTask
from app.models.dev_worker import DevWorker

EXPECTED = (
    ("cli_operations", "operations"),
    ("cli_engineering", "engineering"),
    ("cli_platform", "platform"),
    ("cli_guardian", "guardian"),
    ("cli_sales", "sales"),
    ("cli_success", "success"),
)


def _maker():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    maker = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, maker


def _seed(maker, now, *, omit: str | None = None):
    with maker() as db:
        for wid, supervisor in EXPECTED:
            if wid == omit:
                continue
            db.add(
                DevWorker(
                    worker_id=wid,
                    kind="cli",
                    supervisor_bot=supervisor,
                    capabilities="[]",
                    version="test",
                    started_at=now,
                    heartbeat_ts=now,
                    health="healthy",
                    pid_host="test",
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()


def test_real_canonical_handoff_completes_with_six_live_cli_workers():
    engine, maker = _maker()
    now = datetime(2026, 9, 26, 8, 0, 0)
    _seed(maker, now)

    out = run_canonical_handoff(session_factory=maker, now=now)

    assert out["ok"] is True
    assert out["state"] == "completed"
    assert out["worker_id"] == "api_telegram_jarvis"
    assert out["live_cli_count"] == 6
    assert out["missing_cli_workers"] == []

    with maker() as db:
        task = db.get(DevTask, out["task_id"])
        api_worker = db.get(DevWorker, "api_telegram_jarvis")
        assert task is not None
        assert task.state == "completed"
        assert task.lease_owner is None
        assert task.worker_report
        assert task.test_evidence
        assert api_worker is not None
        assert api_worker.kind == "api"
        assert api_worker.current_task_id is None
        assert api_worker.success_count == 1

    engine.dispose()


def test_real_canonical_handoff_fails_honestly_when_cli_worker_missing():
    engine, maker = _maker()
    now = datetime(2026, 9, 26, 8, 0, 0)
    _seed(maker, now, omit="cli_engineering")

    out = run_canonical_handoff(session_factory=maker, now=now)

    assert out["ok"] is False
    assert out["state"] == "failed"
    assert out["missing_cli_workers"] == ["cli_engineering"]

    with maker() as db:
        task = db.get(DevTask, out["task_id"])
        api_worker = db.get(DevWorker, "api_telegram_jarvis")
        assert task is not None
        assert task.state == "failed"
        assert "cli_engineering" in (task.blocked_reason or "")
        assert api_worker is not None
        assert api_worker.failure_count == 1

    engine.dispose()
