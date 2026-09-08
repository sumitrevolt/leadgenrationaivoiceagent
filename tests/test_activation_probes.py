"""Activation probes — Qdrant + Track B admin flags."""

from app.api import activation as ax


def test_qdrant_unset_is_warn():
    r = ax._qdrant_rag()
    assert r["status"] == "WARN"
    assert not r["checks"]["url_set"]


def test_qdrant_localhost_trap(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://127.0.0.1:6333")
    r = ax._qdrant_rag()
    assert r["status"] == "WARN"
    assert r["checks"]["docker_localhost_trap"]


def test_qdrant_ok_when_host_gateway(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "http://host.docker.internal:6333")
    r = ax._qdrant_rag()
    assert r["status"] == "OK"


def test_track_b_neutral_off_production(monkeypatch):
    monkeypatch.delenv("REVENUE_TRENDS", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    r = ax._track_b_admin()
    assert r["status"] == "NEUTRAL"


def test_track_b_warn_when_prod_flags_off(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("REVENUE_TRENDS", raising=False)
    monkeypatch.delenv("CLIENT_TIMELINE", raising=False)
    monkeypatch.delenv("SYS_HEALTH_DETAIL", raising=False)
    r = ax._track_b_admin()
    assert r["status"] == "WARN"
    assert "vps_enable_readiness_flags" in r["action"]
