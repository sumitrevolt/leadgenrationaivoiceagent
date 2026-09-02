"""Unit tests for app/platform/mcp_engineer.py (Arya)."""

from __future__ import annotations
import json
import os
import time
from pathlib import Path
import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import importlib
    from app.platform import mcp_engineer

    importlib.reload(mcp_engineer)
    yield mcp_engineer


def test_run_mcp_disabled_by_default(_isolate_data_dir, monkeypatch):
    monkeypatch.delenv("MCP_ENGINEER", raising=False)
    r = _isolate_data_dir.run_mcp()
    assert r["status"] == "disabled"
    assert r["score"] is None
    assert "MCP_ENGINEER" in r["summary"]


def test_run_mcp_disabled_when_zero(_isolate_data_dir, monkeypatch):
    monkeypatch.setenv("MCP_ENGINEER", "0")
    assert _isolate_data_dir.run_mcp()["status"] == "disabled"


def test_probe_dependency_returns_score(_isolate_data_dir):
    s, k = _isolate_data_dir._probe_dependency()
    assert s in (0.0, 100.0)
    assert "fastapi_mcp_installed" in k


def test_probe_expose_gate_off_when_no_env(_isolate_data_dir, monkeypatch):
    monkeypatch.delenv("FASTAPI_MCP_TOKEN", raising=False)
    monkeypatch.delenv("MCP_IP_ALLOWLIST", raising=False)
    s, k = _isolate_data_dir._probe_expose_gate()
    assert s == 0.0
    assert k["mcp_endpoint_gated"] is False


def test_probe_expose_gate_on_with_token(_isolate_data_dir, monkeypatch):
    monkeypatch.setenv("FASTAPI_MCP_TOKEN", "test-token-32-chars-or-longer-aaa")
    s, k = _isolate_data_dir._probe_expose_gate()
    assert s == 100.0
    assert k["mcp_endpoint_gated"] is True
    assert k["token_configured"] is True


def test_probe_expose_gate_on_with_allowlist(_isolate_data_dir, monkeypatch):
    monkeypatch.delenv("FASTAPI_MCP_TOKEN", raising=False)
    monkeypatch.setenv("MCP_IP_ALLOWLIST", "1.2.3.4,5.6.7.8")
    s, k = _isolate_data_dir._probe_expose_gate()
    assert s == 100.0
    assert k["ip_allowlist_set"] is True


def test_probe_auth_failures_empty(_isolate_data_dir):
    s, k = _isolate_data_dir._probe_auth_failures()
    assert s == 100.0
    assert k["auth_failures_24h"] == 0


def test_probe_auth_failures_counted_under_threshold(_isolate_data_dir):
    for _ in range(3):
        _isolate_data_dir.log_auth_failure("bad_key", ip="1.1.1.1", path="/mcp/x")
    s, k = _isolate_data_dir._probe_auth_failures()
    assert k["auth_failures_24h"] == 3
    assert s == 80.0


def test_probe_auth_failures_alert_threshold(_isolate_data_dir, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_FAIL_ALERT", "5")
    import importlib
    from app.platform import mcp_engineer as m

    importlib.reload(m)
    for _ in range(6):
        m.log_auth_failure("brute_force_probe", ip="1.1.1.1", path="/mcp/x")
    s, k = m._probe_auth_failures()
    assert k["auth_failures_24h"] == 6
    assert s < 100


def test_probe_a2a_card_has_capabilities(_isolate_data_dir):
    s, k = _isolate_data_dir._probe_a2a_card()
    assert s in (0.0, 50.0, 60.0, 100.0)
    assert isinstance(k, dict)
    assert any(key in k for key in ("capabilities", "reason", "error", "a2a_card_valid"))


def test_run_mcp_full_pass_when_enabled(_isolate_data_dir, monkeypatch):
    monkeypatch.setenv("MCP_ENGINEER", "1")
    r = _isolate_data_dir.run_mcp()
    assert r["status"] == "ok"
    assert isinstance(r["score"], float)
    assert 0 <= r["score"] <= 100
    for p in (
        "dependency",
        "expose_gate",
        "product_armed",
        "keys",
        "rotation",
        "auth_failures",
        "a2a_card",
    ):
        assert p in r["kpis"]


def test_run_mcp_writes_last_run_file(_isolate_data_dir, monkeypatch, tmp_path):
    monkeypatch.setenv("MCP_ENGINEER", "1")
    _isolate_data_dir.run_mcp()
    lf = tmp_path / "mcp_engineer_last.json"
    assert lf.exists()
    assert json.loads(lf.read_text())["role"] == "mcp"


def test_audit_mcp_security_returns_checklist(_isolate_data_dir):
    a = _isolate_data_dir.audit_mcp_security()
    expected = {
        "fastapi_mcp_dep",
        "mcp_endpoint_gated",
        "mcp_product_armed",
        "no_rotation_overdue",
        "no_auth_attack",
        "a2a_card_valid",
        "all_green",
    }
    assert expected.issubset(a.keys())
    assert isinstance(a["all_green"], bool)


def test_health_score_never_ran(_isolate_data_dir):
    assert _isolate_data_dir.health_score()["status"] == "never_ran"


def test_health_score_after_run(_isolate_data_dir, monkeypatch):
    monkeypatch.setenv("MCP_ENGINEER", "1")
    _isolate_data_dir.run_mcp()
    snap = _isolate_data_dir.health_score()
    assert snap["role"] == "mcp"
    assert snap["status"] == "ok"
    assert snap["last_run_age_s"] >= 0


def test_log_auth_failure_persists(_isolate_data_dir, tmp_path):
    _isolate_data_dir.log_auth_failure("test_reason", ip="9.9.9.9", path="/mcp/abc")
    lf = tmp_path / "mcp_auth_failures.jsonl"
    assert lf.exists()
    rec = json.loads(lf.read_text().strip())
    assert rec["reason"] == "test_reason"
    assert rec["ip"] == "9.9.9.9"
    assert rec["path"] == "/mcp/abc"
