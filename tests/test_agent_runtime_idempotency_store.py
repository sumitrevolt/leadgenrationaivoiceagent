"""Agent Runtime idempotency store unit tests."""

from __future__ import annotations

import json
import time

import pytest

from app.platform import agent_runtime_idempotency as arid


@pytest.fixture(autouse=True)
def _mem(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "memory")
    arid.reset_memory_for_tests()
    yield
    arid.reset_memory_for_tests()


def test_claim_atomic_and_duplicate():
    a = arid.claim("pranav", "run_owned_workflow", "k-1", runtime_run_id="art_aaa111111111")
    assert a.claimed and a.ok
    b = arid.claim("pranav", "run_owned_workflow", "k-1", runtime_run_id="art_bbb222222222")
    assert b.duplicate and b.reason_code == "duplicate_in_progress"
    assert b.original_run_id == "art_aaa111111111"


def test_complete_success_then_duplicate_suppressed():
    arid.claim("pranav", "run_owned_workflow", "k-ok", runtime_run_id="art_ok1")
    arid.complete(
        "pranav", "run_owned_workflow", "k-ok", status="succeeded", runtime_run_id="art_ok1"
    )
    d = arid.claim("pranav", "run_owned_workflow", "k-ok")
    assert d.duplicate and d.reason_code == "duplicate_suppressed"
    assert d.original_status == "succeeded"


def test_tenant_isolation():
    arid.claim("pranav", "run_owned_workflow", "same", tenant_id="tA", runtime_run_id="art_a")
    b = arid.claim("pranav", "run_owned_workflow", "same", tenant_id="tB", runtime_run_id="art_b")
    assert b.claimed  # different scope


def test_capability_isolation():
    arid.claim("nikhil", "scan_delivery_assurance", "same", runtime_run_id="art_n1")
    b = arid.claim("nikhil", "other_action", "same", runtime_run_id="art_n2")
    # other_action may fail capability canon if invalid chars — use valid
    assert b.claimed or b.reason_code == "malformed_idempotency_key"
    c = arid.claim("nikhil", "run_owned_workflow", "same", runtime_run_id="art_n3")
    assert c.claimed


def test_release_allows_retry_after_block():
    arid.claim("pranav", "run_owned_workflow", "rel-1", runtime_run_id="art_r1")
    arid.release("pranav", "run_owned_workflow", "rel-1")
    again = arid.claim("pranav", "run_owned_workflow", "rel-1", runtime_run_id="art_r2")
    assert again.claimed


def test_redis_unavailable_fail_closed(monkeypatch):
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "redis")
    monkeypatch.setattr(arid, "_sync_redis", lambda: (_ for _ in ()).throw(OSError("down")))
    out = arid.claim("pranav", "run_owned_workflow", "fail-1")
    assert out.store_unavailable
    assert out.reason_code == "idempotency_store_unavailable"
    assert arid._MEM.get(arid.idem_key("pranav", "run_owned_workflow", "fail-1") or "") is None


def test_backend_status_no_secrets():
    st = arid.backend_status()
    blob = json.dumps(st)
    assert "password" not in blob.lower()
    assert "redis://" not in blob
    assert st["fail_open_on_redis_error"] is False
    assert st["fallback_active"] is True  # memory test backend


def test_ttl_expiry_allows_new_claim(monkeypatch):
    out = arid.claim("pranav", "run_owned_workflow", "ttl-1", ttl_s=60)
    key = out.redis_key
    with arid._MEM_LOCK:
        payload, _ = arid._MEM[key]
        arid._MEM[key] = (payload, time.time() - 1)
    again = arid.claim("pranav", "run_owned_workflow", "ttl-1")
    assert again.claimed


def test_malformed_key():
    out = arid.claim("pranav", "run_owned_workflow", "bad\nkey")
    assert not out.ok
    assert out.reason_code == "malformed_idempotency_key"


def test_file_backend(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_BACKEND", "file")
    monkeypatch.setenv("AGENT_RUNTIME_IDEM_FILE", str(tmp_path / "idem.json"))
    a = arid.claim("nikhil", "scan_delivery_assurance", "file-1", runtime_run_id="art_f1")
    assert a.claimed and a.backend == "file"
    arid.complete(
        "nikhil", "scan_delivery_assurance", "file-1", status="succeeded", runtime_run_id="art_f1"
    )
    d = arid.claim("nikhil", "scan_delivery_assurance", "file-1")
    assert d.duplicate and d.original_status == "succeeded"
