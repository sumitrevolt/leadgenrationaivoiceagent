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
    for k in ("cpu_pct", "mem_pct", "disk_pct", "redis_ping_ms",
              "celery_queue_depth", "worker_alive", "health_ready"):
        assert k in d
