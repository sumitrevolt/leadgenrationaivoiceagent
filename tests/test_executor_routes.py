"""M020 — Tests for executor handshake routes.

The routes expose HMAC-authenticated endpoints for external desktop executors
to claim, heartbeat, and complete assigned tasks on the canonical
AutomationOrchestrator. The test suite verifies:

1. Authentication: missing secrets / bad signatures / unknown tools / replay
   are rejected with clear HTTP errors.
2. The public status endpoint reveals enrolled tools but no secrets.
3. The reference client (``scripts/executor_handshake.py``) can construct
   valid signatures that are accepted by the routes.

These tests use the canonical in-process FastAPI client + a per-test
fresh HMAC secret in env, so they don't require a live server.
"""

from __future__ import annotations

import json
import os
import secrets
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture
def hermes_secret(monkeypatch, tmp_path):
    """Configure a fresh HMAC secret for the ``hermes`` tool in env.

    Returns the secret string so each test can sign requests the same way.
    """
    data = tmp_path / "data"
    data.mkdir(parents=True, exist_ok=True)
    monkeypatch.chdir(tmp_path)
    secret = "lifecycle-test-" + secrets.token_hex(24)  # nosecret - randomized test-only fixture
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    monkeypatch.setenv("COORD_HUB_TOOL_HERMES_SECRET", secret)
    # NOTE on Agnes: per ``coordination_hub_auth._KNOWN_TOOLS``, the
    # registered HMAC tool list is (cursor, claude, monkeycode, opencode,
    # bolt, buzz, hermes, openclaw, workbuddy, codex, freebuff, verdant) —
    # Agnes is NOT in the list. Bringing Agnes under HMAC attestation
    # requires owner to extend ``_KNOWN_TOOLS`` first; see M020 §3 flag.
    return secret


def _client():
    """Build a TestClient with the executor router included."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from app.api.executor_routes import router as executor_router

    app = FastAPI()
    app.include_router(executor_router)
    return TestClient(app), app


def _sign_headers(secret: str, tool_id: str, event_type: str, body_bytes: bytes):
    """Build the canonical HMAC headers for a request."""
    from app.platform import coordination_hub_auth as auth

    issued_at = int(time.time())
    nonce = secrets.token_urlsafe(24)
    body_sha = auth.body_sha256(body_bytes)
    sig = auth.build_tool_signature(
        secret=secret,
        tool_id=tool_id,
        event_type=event_type,
        body_sha256=body_sha,
        issued_at=issued_at,
        nonce=nonce,
    )
    return {
        "Content-Type": "application/json",
        "X-Tool-Id": tool_id,
        "X-Event-Type": event_type,
        "X-Body-Sha256": body_sha,
        "X-Issued-At": str(issued_at),
        "X-Nonce": nonce,
        "X-Signature": sig,
    }


def test_status_endpoint_lists_tools_no_secrets(hermes_secret) -> None:
    client, _app = _client()
    r = client.get("/api/executor/handshake/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["hub_enabled"] is True
    assert "hermes" in body["known_tools"]
    assert "cursor" in body["known_tools"]  # canonical 12-tool whitelist
    # M020 owner-authorized: Agnes enrolled under HMAC attestation per directive P1.
    assert "agnes" in body["known_tools"]
    assert body["tools_configured"]["hermes"] is True
    # Agnes has its COORD_HUB_TOOL_AGNES_SECRET pre-provisioned by the test fixture
    # in some tests, but NOT in this one — so we check it independently per fixture.
    # Critical: no secrets / fingerprints leak
    for v in body.values():
        assert not isinstance(v, dict) or "secret" not in v


def test_status_endpoint_lists_agnes_when_enrolled() -> None:
    """Agnes-specific HMAC enrollment: she appears in known_tools and is
    configurable via COORD_HUB_TOOL_AGNES_SECRET in env."""
    from app.platform import coordination_hub_auth as auth

    assert "agnes" in auth._KNOWN_TOOLS
    # Without a secret configured for agnes in env, tools_configured['agnes'] is False
    os.environ.pop("COORD_HUB_TOOL_AGNES_SECRET", None)
    status = auth.tool_auth_status()
    assert status["tools_configured"]["agnes"] is False  # no secret → not configured
    os.environ["COORD_HUB_TOOL_AGNES_SECRET"] = "x" * 64
    status = auth.tool_auth_status()
    assert status["tools_configured"]["agnes"] is True  # secret set → configured
    del os.environ["COORD_HUB_TOOL_AGNES_SECRET"]


def test_agnes_secret_env_name_lookup() -> None:
    """The dedicated env var COORD_HUB_TOOL_AGNES_SECRET is the source for agnes."""
    from app.platform import coordination_hub_auth as auth

    assert auth._secret_env_name("agnes") == "COORD_HUB_TOOL_AGNES_SECRET"
    # buzz keeps its special name (per existing coord_hub_auth convention)
    assert auth._secret_env_name("buzz") == "COORD_HUB_BUZZ_SECRET"


def test_status_endpoint_returns_503_when_hub_disabled(monkeypatch) -> None:
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "0")
    client, _app = _client()
    r = client.get("/api/executor/handshake/status")
    assert r.status_code == 503


def test_next_task_rejects_unknown_tool(hermes_secret) -> None:
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    headers = _sign_headers(hermes_secret, "nonexistent_tool", "executor.next_task", body)
    r = client.post(
        "/api/executor/nonexistent_tool/next-task",
        content=body,
        headers=headers,
    )
    assert r.status_code == 404
    assert "unknown_tool_id" in r.text


def test_next_task_rejects_unconfigured_secret(monkeypatch, tmp_path) -> None:
    """Tool known but secret not configured in env → 503 not 401."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("COORDINATION_HUB_ENABLED", "1")
    # Note: no COORD_HUB_TOOL_HERMES_SECRET set
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    # Sign with a fake secret — auth layer will refuse on config missing,
    # not on signature mismatch.
    headers = _sign_headers("dummy", "hermes", "executor.next_task", body)
    r = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    # Config-missing error fires BEFORE signature verification in the route's
    # _check_secret_configured step, so we get 503.
    assert r.status_code == 503
    assert "secret_unconfigured" in r.text


def test_next_task_with_valid_signature_returns_no_task_yet(hermes_secret) -> None:
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    headers = _sign_headers(hermes_secret, "hermes", "executor.next_task", body)
    r = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r.status_code == 200
    body_j = r.json()
    assert body_j["ok"] is True
    # No READY tasks exist yet for hermes — tool_id and candidate_roles are returned
    assert body_j["tool_id"] == "hermes"
    # task_id may be None (no task right now)
    assert "task_id" in body_j


def test_invalid_signature_rejected(hermes_secret) -> None:
    """Same-shape headers with the WRONG signature must be 401."""
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    headers = _sign_headers(hermes_secret, "hermes", "executor.next_task", body)
    headers["X-Signature"] = "0" * 64  # corrupt the signature
    r = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r.status_code == 401
    assert "signature_invalid" in r.text


def test_body_hash_is_bound_to_actual_request_bytes(hermes_secret) -> None:
    """A valid signature for one body must not authorize different JSON bytes."""
    client, _app = _client()
    original = json.dumps({"task_id": "safe-task"}).encode("utf-8")
    tampered = json.dumps({"task_id": "different-task"}).encode("utf-8")
    headers = _sign_headers(hermes_secret, "hermes", "executor.claim", original)

    r = client.post("/api/executor/hermes/claim", content=tampered, headers=headers)

    assert r.status_code == 400
    assert "body_sha256_mismatch" in r.text


def test_replay_nonce_rejected(hermes_secret) -> None:
    """Replay the same nonce twice — second call rejected."""
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    headers = _sign_headers(hermes_secret, "hermes", "executor.next_task", body)
    r1 = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r1.status_code == 200, r1.text
    # Same headers = same nonce, must be rejected as replay
    r2 = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r2.status_code == 409, r2.text
    assert "nonce_replay" in r2.text


def test_expired_token_rejected(hermes_secret) -> None:
    """Token issued more than 300s ago must be rejected."""
    from app.platform import coordination_hub_auth as auth

    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    body_sha = auth.body_sha256(body)
    issued_at = int(time.time()) - 600  # 10 min ago
    nonce = secrets.token_urlsafe(24)
    sig = auth.build_tool_signature(
        secret=hermes_secret,
        tool_id="hermes",
        event_type="executor.next_task",
        body_sha256=body_sha,
        issued_at=issued_at,
        nonce=nonce,
    )
    headers = {
        "Content-Type": "application/json",
        "X-Tool-Id": "hermes",
        "X-Event-Type": "executor.next_task",
        "X-Body-Sha256": body_sha,
        "X-Issued-At": str(issued_at),
        "X-Nonce": nonce,
        "X-Signature": sig,
    }
    r = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r.status_code == 401
    assert "timestamp_outside_window" in r.text


def test_heartbeat_requires_task_id_in_body(hermes_secret) -> None:
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")  # empty body
    headers = _sign_headers(hermes_secret, "hermes", "executor.heartbeat", body)
    r = client.post("/api/executor/hermes/heartbeat", content=body, headers=headers)
    assert r.status_code == 400
    assert "task_id_required_in_body" in r.text


def test_tool_id_mismatch_rejected(hermes_secret) -> None:
    """Path tool_id must match the identity from the HMAC headers."""
    client, _app = _client()
    body = json.dumps({}).encode("utf-8")
    # Signature says tool_id="hermes" but path is "agnes"
    headers = _sign_headers(hermes_secret, "hermes", "executor.next_task", body)
    r = client.post("/api/executor/agnes/next-task", content=body, headers=headers)
    assert r.status_code == 403
    assert "tool_id_mismatch" in r.text


def test_task_assignment_is_fail_closed_and_supports_explicit_role_mapping(monkeypatch) -> None:
    from types import SimpleNamespace

    from fastapi import HTTPException

    from app.api.executor_routes import _require_task_assignment

    with pytest.raises(HTTPException) as exc:
        _require_task_assignment(SimpleNamespace(assigned_agent="engineering"), "hermes")
    assert exc.value.status_code == 403

    monkeypatch.setenv("EXECUTOR_HERMES_ALLOWED_AGENTS", "engineering,qa")
    _require_task_assignment(SimpleNamespace(assigned_agent="engineering"), "hermes")
    _require_task_assignment(SimpleNamespace(assigned_agent="hermes"), "hermes")


def test_reference_client_script_runs_smoke(monkeypatch, tmp_path, hermes_secret) -> None:
    """End-to-end: the reference handshake client constructs valid signed
    requests against the route handlers (without an HTTP round-trip — same
    process). Validates protocol consistency between the two files."""
    monkeypatch.chdir(tmp_path)
    # Import the reference client
    sys.path.insert(0, str(ROOT))
    # Build headers the same way the client would
    import time as t

    from scripts import executor_handshake as ref

    body = json.dumps({}).encode("utf-8")
    headers = ref._build_headers("hermes", "executor.next_task", body, hermes_secret)
    assert headers["X-Tool-Id"] == "hermes"
    assert headers["X-Event-Type"] == "executor.next_task"
    assert len(headers["X-Nonce"]) >= 16
    assert len(headers["X-Signature"]) == 64  # SHA-256 hex

    # Verify these headers work against the route
    client, _app = _client()
    r = client.post("/api/executor/hermes/next-task", content=body, headers=headers)
    assert r.status_code == 200, r.text
