"""Tests for centralized automation log service (ADR-064, 2026-07-09)."""

import os
import uuid

import pytest

from app.platform.automation_log_service import (
    get_logs,
    has_run_today,
    log_event,
)


def test_log_event_jsonl_fallback(tmp_path, monkeypatch):
    """log_event falls back to JSONL when DB is unavailable."""
    # get_db_session is imported inside log_event, so patch the source module
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: (_ for _ in ()).throw(Exception("no DB")),
    )
    log_file = tmp_path / "automation_logs.jsonl"
    monkeypatch.setattr("app.platform.automation_log_service._JSONL_PATH", str(log_file))

    log_id = log_event(job_type="content_generation", status="success", client_id="c1")
    assert log_id
    # JSONL fallback writes to disk; file should exist
    assert os.path.isfile(str(log_file))


def test_log_event_db_success(monkeypatch):
    """log_event writes to DB successfully."""

    class FakeDB:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def add(self, obj):
            self._added = obj

        def commit(self):
            pass

    fake_db = FakeDB()
    fake_db._added = None
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: fake_db,
    )
    log_id = log_event(
        job_type="test_job",
        status="running",
        client_id="c_test",
        triggered_by="scheduler",
    )
    assert log_id
    assert fake_db._added is not None
    assert fake_db._added.job_type == "test_job"
    assert fake_db._added.client_id == "c_test"


def test_has_run_today_jsonl(tmp_path, monkeypatch):
    """has_run_today detects duplicate run via JSONL fallback."""
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: (_ for _ in ()).throw(Exception("no DB")),
    )
    log_file = tmp_path / "automation_logs.jsonl"
    monkeypatch.setattr("app.platform.automation_log_service._JSONL_PATH", str(log_file))

    assert not has_run_today("c1", "job_x")
    log_event(job_type="job_x", status="success", client_id="c1")
    assert has_run_today("c1", "job_x")
    assert not has_run_today("c2", "job_x")


def test_get_logs_jsonl_empty(tmp_path, monkeypatch):
    """get_logs returns empty list when JSONL file doesn't exist."""
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: (_ for _ in ()).throw(Exception("no DB")),
    )
    monkeypatch.setattr(
        "app.platform.automation_log_service._JSONL_PATH",
        str(tmp_path / "nonexistent.jsonl"),
    )
    assert get_logs() == []


def test_log_event_never_raises(monkeypatch, tmp_path):
    """log_event never raises — returns ID even on catastrophic failure."""
    # Force all paths to fail
    monkeypatch.setattr(
        "app.models.base.get_db_session",
        lambda: (_ for _ in ()).throw(RuntimeError("all dead")),
    )
    # Point JSONL to an impossible path
    monkeypatch.setattr(
        "app.platform.automation_log_service._JSONL_PATH",
        str(tmp_path / "impossible" / "dir" / "log.jsonl"),
    )
    # Should not raise
    result = log_event(job_type="x", status="ok")
    assert isinstance(result, str)  # always returns a string ID


def test_admin_automation_logs_endpoint(client):
    """GET /api/admin/automation-logs is admin-gated and returns data for admins."""
    from app.api.auth_deps import get_current_user, require_admin
    from app.main import app

    saved_admin = app.dependency_overrides.pop(require_admin, None)
    saved_user = app.dependency_overrides.pop(get_current_user, None)
    try:
        assert client.get("/api/admin/automation-logs").status_code in (401, 403)
        app.dependency_overrides[require_admin] = lambda: {
            "username": "test-admin",
            "role": "admin",
        }
        resp = client.get("/api/admin/automation-logs")
        assert resp.status_code == 200
        body = resp.json()
        assert body.get("ok") is True
        assert "logs" in body
    finally:
        app.dependency_overrides.pop(require_admin, None)
        if saved_admin is not None:
            app.dependency_overrides[require_admin] = saved_admin
        if saved_user is not None:
            app.dependency_overrides[get_current_user] = saved_user
