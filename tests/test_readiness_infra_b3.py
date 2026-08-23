"""B3 - system-health drill-down endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.api.auth_deps import require_admin
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_auth():
    app.dependency_overrides[require_admin] = lambda: {"id": "admin", "role": "super_admin"}
    yield
    app.dependency_overrides.pop(require_admin, None)


def test_health_detail_flag_off(monkeypatch):
    monkeypatch.delenv("SYS_HEALTH_DETAIL", raising=False)
    r = client.get("/api/admin/system-health-detail")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


def test_health_detail_shape(monkeypatch):
    monkeypatch.setenv("SYS_HEALTH_DETAIL", "1")
    r = client.get("/api/admin/system-health-detail")
    assert r.status_code == 200
    d = r.json()
    for k in (
        "cpu_pct",
        "mem_pct",
        "disk_pct",
        "redis_ping_ms",
        "celery_queue_depth",
        "worker_alive",
        "health_ready",
    ):
        assert k in d


def test_health_detail_admin_friendly_grade(monkeypatch):
    """B3 admin-friendly layer: graded rows + overall status + Hinglish summary."""
    monkeypatch.setenv("SYS_HEALTH_DETAIL", "1")
    d = client.get("/api/admin/system-health-detail").json()
    assert isinstance(d.get("rows"), list) and d["rows"]
    keys = {row["key"] for row in d["rows"]}
    assert {"cpu", "mem", "disk", "redis", "queue", "worker"} <= keys
    for row in d["rows"]:
        assert row["status"] in ("ok", "warn", "bad", "unknown")
        assert "label" in row and "value" in row and "hint" in row
    assert d["status"] in ("ok", "warn", "bad", "unknown")
    assert isinstance(d.get("summary"), str) and d["summary"]


def test_grade_thresholds():
    """Pure grader: known inputs -> expected status (no env/HTTP needed)."""
    from app.api.system_health import _grade

    # all healthy
    g = _grade(
        {"cpu_pct": 10, "mem_pct": 20, "disk_pct": 30},
        {"celery_queue_depth": 5, "worker_alive": "ok"},
        2,
    )
    assert g["status"] == "ok"
    # disk full + queue backlog -> bad overall
    g2 = _grade(
        {"cpu_pct": 10, "mem_pct": 20, "disk_pct": 95},
        {"celery_queue_depth": 900, "worker_alive": "ok"},
        2,
    )
    assert g2["status"] == "bad"
    disk_row = next(r for r in g2["rows"] if r["key"] == "disk")
    assert disk_row["status"] == "bad" and disk_row["hint"]
    # redis down (-1) -> bad redis row
    g3 = _grade(
        {"cpu_pct": 10, "mem_pct": 20, "disk_pct": 30},
        {"celery_queue_depth": 5, "worker_alive": "ok"},
        -1,
    )
    redis_row = next(r for r in g3["rows"] if r["key"] == "redis")
    assert redis_row["status"] == "bad"
    # missing data (-1 pct) -> unknown row, not a crash
    g4 = _grade(
        {"cpu_pct": -1, "mem_pct": -1, "disk_pct": -1},
        {"celery_queue_depth": -1, "worker_alive": "unknown"},
        2,
    )
    cpu_row = next(r for r in g4["rows"] if r["key"] == "cpu")
    assert cpu_row["status"] == "unknown"
