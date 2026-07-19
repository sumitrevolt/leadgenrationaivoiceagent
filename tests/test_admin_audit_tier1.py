"""Tier-1 governance — regression tests for the centralized admin audit helper.

Covers request-metadata capture, redaction, actor extraction, row construction for
success + rejected results, and the fail-open-but-loud vs fail-closed persistence
policy. Deliberately DB-config-independent: async paths use asyncio.run and a fake
session, so these run under any pytest configuration.
"""

import asyncio

from app.platform import admin_audit


class _FakeHeaders(dict):
    def get(self, k, default=None):  # case-insensitive like Starlette Headers
        return super().get(k.lower(), default)


class _FakeClient:
    host = "203.0.113.9"


class _FakeRequest:
    def __init__(self, headers=None, client=True):
        self.headers = _FakeHeaders(headers or {})
        self.client = _FakeClient() if client else None

        class _S:
            pass

        self.state = _S()


class _Role:
    def __init__(self, v):
        self.value = v


class _FakeUser:
    def __init__(self, uid="u-123", role="super_admin"):
        self.id = uid
        self.role = _Role(role)


def test_redact_removes_sensitive_keys():
    out = admin_audit._redact(
        {
            "email": "a@b.com",
            "password": "PLACEHOLDER_PW",  # pragma: allowlist secret
            "nested": {"api_key": "PLACEHOLDER_KEY", "ok": 1},  # pragma: allowlist secret
        }
    )
    assert out["email"] == "a@b.com"
    assert out["password"] == "***REDACTED***"
    assert out["nested"]["api_key"] == "***REDACTED***"
    assert out["nested"]["ok"] == 1


def test_request_meta_prefers_xff_and_request_id_header():
    req = _FakeRequest(
        {
            "x-request-id": "req-abc",
            "x-forwarded-for": "198.51.100.7, 10.0.0.1",
            "user-agent": "UA/1.0",
        }
    )
    meta = admin_audit.request_meta(req)
    assert meta["request_id"] == "req-abc"
    assert meta["ip"] == "198.51.100.7"  # first XFF hop, not the proxy
    assert meta["user_agent"] == "UA/1.0"


def test_request_meta_falls_back_to_client_host_and_generates_request_id():
    req = _FakeRequest({"user-agent": "UA/2.0"})
    meta = admin_audit.request_meta(req)
    assert meta["ip"] == "203.0.113.9"
    assert meta["user_agent"] == "UA/2.0"
    assert meta["request_id"] and len(meta["request_id"]) >= 8  # generated uuid


def test_build_audit_row_success_populates_all_metadata():
    req = _FakeRequest({"x-request-id": "rid-1", "user-agent": "Mozilla/5"})
    row, (actor_id, actor_role, meta) = admin_audit.build_audit_row(
        request=req,
        actor=_FakeUser(),
        action="client.delete",
        target_type="client",
        target_id="jiya-makeover",
        tenant="jiya-makeover",
        after={"deleted": True},
        result="success",
        idempotency_key="idem-9",
    )
    assert row.action == "client.delete"
    assert row.user_id == "u-123"
    assert row.resource_type == "client"
    assert row.resource_id == "jiya-makeover"
    assert row.request_id == "rid-1"
    assert row.user_agent == "Mozilla/5"
    assert row.ip_address == "203.0.113.9"
    assert row.severity == "info"
    assert actor_id == "u-123" and actor_role == "super_admin"
    # extra governance fields live in new_value payload
    import json

    payload = json.loads(row.new_value)
    assert payload["actor_role"] == "super_admin"
    assert payload["result"] == "success"
    assert payload["idempotency_key"] == "idem-9"
    assert payload["tenant"] == "jiya-makeover"


def test_build_audit_row_rejected_is_warning_and_records_error():
    row, _ = admin_audit.build_audit_row(
        request=_FakeRequest(),
        actor=_FakeUser(role="admin"),
        action="ops.celery_trim",
        target_type="queue",
        target_id="celery",
        result="rejected",
        error="confirm:true required",
    )
    assert row.severity == "warning"
    import json

    payload = json.loads(row.new_value)
    assert payload["result"] == "rejected"
    assert "confirm" in payload["error"]


def test_build_audit_row_redacts_secret_in_before_state():
    row, _ = admin_audit.build_audit_row(
        request=_FakeRequest(),
        actor=_FakeUser(),
        action="trust.configure",
        before={
            "secret_key": "PLACEHOLDER_SECRET",  # pragma: allowlist secret
            "site_key": "public",
        },
        result="success",
    )
    assert "PLACEHOLDER_SECRET" not in (row.old_value or "")
    assert "REDACTED" in (row.old_value or "")


# ---- persistence policy (fail-open-but-loud vs fail-closed) --------------------


class _FakeSession:
    def __init__(self, fail=False):
        self.fail = fail
        self.added = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def add(self, row):
        self.added.append(row)

    async def commit(self):
        if self.fail:
            raise RuntimeError("db down")


def _patch_session(monkeypatch, session):
    import app.models.base as base

    def _factory():
        return session

    monkeypatch.setattr(base, "get_async_session", _factory, raising=False)


def test_record_admin_action_persists_success(monkeypatch):
    sess = _FakeSession(fail=False)
    _patch_session(monkeypatch, sess)
    ok = asyncio.run(
        admin_audit.record_admin_action(
            request=_FakeRequest({"x-request-id": "r"}),
            actor=_FakeUser(),
            action="client.dedupe",
            target_type="client",
            target_id="*",
            result="success",
        )
    )
    assert ok is True
    assert len(sess.added) == 1
    assert sess.added[0].action == "client.dedupe"


def test_record_admin_action_fail_open_returns_false(monkeypatch):
    # audit DB down → default policy must NOT raise (post-action fail-open) and returns False
    sess = _FakeSession(fail=True)
    _patch_session(monkeypatch, sess)
    ok = asyncio.run(
        admin_audit.record_admin_action(
            request=_FakeRequest(),
            actor=_FakeUser(),
            action="client.delete",
            target_type="client",
            target_id="x",
            result="success",
        )
    )
    assert ok is False


def test_record_admin_action_fail_closed_raises(monkeypatch):
    sess = _FakeSession(fail=True)
    _patch_session(monkeypatch, sess)
    raised = False
    try:
        asyncio.run(
            admin_audit.record_admin_action(
                request=_FakeRequest(),
                actor=_FakeUser(),
                action="client.delete",
                target_type="client",
                target_id="x",
                result="success",
                fail_closed=True,
            )
        )
    except Exception:
        raised = True
    assert raised is True
