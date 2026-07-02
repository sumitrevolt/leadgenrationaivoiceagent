"""Optional bearer-token gate on /metrics + /health/deep (production audit
2026-07-01, low-severity finding): both endpoints returned real business/
operational counts with no auth, and reachability from outside the Docker
network depended on reverse-proxy config that couldn't be verified from this
session. METRICS_TOKEN is opt-in — unset means unchanged (open) behavior,
since internal Prometheus scraping (monitoring/prometheus.yml) has no token
configured by default.
"""

from __future__ import annotations

from starlette.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_open_by_default(monkeypatch):
    monkeypatch.delenv("METRICS_TOKEN", raising=False)
    assert client.get("/metrics").status_code == 200
    assert client.get("/health/deep").status_code == 200


def test_metrics_rejects_no_token_when_armed(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-secret-abc")
    assert client.get("/metrics").status_code == 401
    assert client.get("/health/deep").status_code == 401


def test_metrics_rejects_wrong_token_when_armed(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-secret-abc")
    resp = client.get("/metrics", headers={"Authorization": "Bearer wrong-token"})
    assert resp.status_code == 401


def test_metrics_accepts_bearer_token_when_armed(monkeypatch):
    monkeypatch.setenv("METRICS_TOKEN", "test-secret-abc")
    resp = client.get("/metrics", headers={"Authorization": "Bearer test-secret-abc"})
    assert resp.status_code == 200


def test_health_deep_accepts_x_metrics_token_header_when_armed(monkeypatch):
    """Prometheus's bearer_token_file only sets Authorization — the X-Metrics-Token
    fallback is for manual/curl checks, both must work once armed."""
    monkeypatch.setenv("METRICS_TOKEN", "test-secret-abc")
    resp = client.get("/health/deep", headers={"X-Metrics-Token": "test-secret-abc"})
    assert resp.status_code == 200
