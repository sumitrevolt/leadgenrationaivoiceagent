"""Cancellation store unit tests — memory/file backends (no silent prod fallback)."""

from __future__ import annotations

import json
import time

import pytest

from app.platform import agent_runtime_cancellation as crc


@pytest.fixture(autouse=True)
def _mem_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "memory")
    crc.reset_memory_for_tests()
    yield
    crc.reset_memory_for_tests()


def test_request_creates_structured_record():
    out = crc.request("pranav", "art_abc123def456", requested_by="owner", reason="unit")
    assert out["ok"] is True
    assert out["newly_created"] is True
    assert out["cancellation_backend"] == "memory"
    rec = out["record"]
    assert rec["schema_version"] == 1
    assert rec["agent_id"] == "pranav"
    assert rec["runtime_run_id"] == "art_abc123def456"
    assert "secret" not in json.dumps(rec).lower()


def test_request_idempotent():
    a = crc.request("pranav", "art_abc123def456")
    b = crc.request("pranav", "art_abc123def456")
    assert a["newly_created"] is True
    assert b["already_requested"] is True
    assert b["ok"] is True


def test_isolation_two_runs_same_agent():
    crc.request("pranav", "art_run_aaaaaa")
    assert crc.is_requested("pranav", "art_run_aaaaaa").requested
    assert not crc.is_requested("pranav", "art_run_bbbbbb").requested


def test_isolation_two_agents():
    crc.request("pranav", "art_sharedid1234")
    assert crc.is_requested("pranav", "art_sharedid1234").requested
    assert not crc.is_requested("nikhil", "art_sharedid1234").requested


def test_clear_specific_run_only():
    crc.request("pranav", "art_run_aaaaaa")
    crc.request("pranav", "art_run_bbbbbb")
    crc.clear("pranav", "art_run_aaaaaa")
    assert not crc.is_requested("pranav", "art_run_aaaaaa").requested
    assert crc.is_requested("pranav", "art_run_bbbbbb").requested


def test_malformed_target():
    out = crc.request("pranav", "bad id with spaces")
    assert out["ok"] is False
    assert out["reason_code"] == "malformed_target"


def test_expired_record(monkeypatch):
    out = crc.request("pranav", "art_expire_me_01", ttl_s=1)
    assert out["ok"]
    key = out["key"]
    with crc._MEM_LOCK:
        payload, _ = crc._MEM[key]
        crc._MEM[key] = (payload, time.time() - 1)
    chk = crc.get("pranav", "art_expire_me_01")
    assert chk.status == "expired"
    assert not chk.requested


def test_file_backend_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / "cancel.json"
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "file")
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_FILE", str(path))
    out = crc.request("nikhil", "art_file_run_001")
    assert out["cancellation_backend"] == "file"
    chk = crc.is_requested("nikhil", "art_file_run_001")
    assert chk.requested
    crc.clear("nikhil", "art_file_run_001")
    assert not crc.is_requested("nikhil", "art_file_run_001").requested


def test_redis_unavailable_not_silent_not_cancelled(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "redis")

    def _boom():
        raise RuntimeError("redis down")

    monkeypatch.setattr(crc, "_sync_redis", _boom)
    out = crc.request("pranav", "art_fail_run_001")
    assert out["ok"] is False
    assert out["reason_code"] == "cancellation_store_unavailable"
    chk = crc.is_requested("pranav", "art_fail_run_001")
    assert chk.status == "store_unavailable"
    assert not chk.requested  # must NOT look like "not cancelled"


def test_backend_status_no_credentials():
    st = crc.backend_status()
    blob = json.dumps(st)
    assert "password" not in blob.lower()
    assert "redis://" not in blob
    assert "cancellation_backend" in st
    assert st.get("fallback_active") is True  # memory test backend


def test_no_production_memory_fallback_when_redis_selected(monkeypatch):
    """Production path must not silently write memory on Redis failure."""
    monkeypatch.setenv("AGENT_RUNTIME_CANCEL_BACKEND", "redis")
    monkeypatch.setattr(crc, "_sync_redis", lambda: (_ for _ in ()).throw(OSError("down")))
    out = crc.request("pranav", "art_nomem_fb_001")
    assert out["ok"] is False
    assert crc._MEM.get(crc.cancel_key("pranav", "art_nomem_fb_001")) is None
