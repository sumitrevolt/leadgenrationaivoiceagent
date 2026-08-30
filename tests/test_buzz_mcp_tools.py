"""Buzz MCP tools (/api/buzz/*) — safety-rail contract tests.

t_574a3fbe (CTRL-P0-D2 rework): file MODULE-LEVEL import hoti hai (function-
level import trap se bachne ke liye — CLAUDE.md landmine §7), taaki import
khud hi proof ban jaaye ki deliverable repo me EXIST karti hai.

Auth: conftest.py globally require_admin override karta hai (mock-admin) —
yahan business-logic gates test hote hain.
"""

import pytest
from fastapi.testclient import TestClient

# Module-level import = existence proof (D2 regression guard).
from app.api import buzz_mcp_tools as buzz_mod
from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_redis(monkeypatch):
    """Redis-dependent gates ko in-memory fake se chalao (deterministic tests)."""
    store: dict[str, Any] = {}

    class FakeRedis:
        async def set(self, key, value, nx=False, ex=None):
            if nx and key in store:
                return None
            store[key] = value
            return True

        async def incr(self, key):
            store[key] = int(store.get(key, 0)) + 1
            return store[key]

        async def expire(self, key, ttl):
            return True

        async def delete(self, key):
            store.pop(key, None)
            return 1

    async def fake_client():
        return FakeRedis()

    monkeypatch.setattr("app.cache.get_redis_client", fake_client)
    yield
    store.clear()


from typing import Any  # noqa: E402  (fixture annotation ke liye)


def _patch_suppression(monkeypatch, state="none"):
    from app.platform import email_unsub

    monkeypatch.setattr(email_unsub, "suppression_state", lambda **kw: state)


# ---------------------------------------------------------------- existence
def test_module_and_class_exist():
    assert hasattr(buzz_mod, "AgentRuntimeIdempotency")
    assert hasattr(buzz_mod, "RATE_LIMITS")
    assert set(buzz_mod.RATE_LIMITS) == {"voice", "whatsapp", "email"}


@pytest.mark.parametrize(
    ("path", "op"),
    [
        ("/api/buzz/voice-call", "buzz_voice_call"),
        ("/api/buzz/whatsapp-message", "buzz_whatsapp_message"),
        ("/api/buzz/email-send", "buzz_email_send"),
    ],
)
def test_tools_registered_with_operation_ids(path, op):
    # NOTE: app.routes me wrapped routers '_IncludedRouter' hote hain (.path
    # nahi) — isliye source-router se inspect karte hain. Router-level paths
    # prefix-less hain (/buzz/...); main.py /api prefix add karta hai.
    routes = {r.path: getattr(r, "operation_id", "") for r in buzz_mod.router.routes}
    assert routes.get(path.replace("/api", "", 1)) == op


# ---------------------------------------------------------------- dry-run happy path
def test_voice_dry_run_ok(client, monkeypatch):
    _patch_suppression(monkeypatch)
    r = client.post("/api/buzz/voice-call", json={"phone": "919876543210"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True and body["dry_run"] is True
    assert body["idempotency_key"].startswith("buzz:mcp:idem:voice:")


def test_email_dry_run_ok(client, monkeypatch):
    _patch_suppression(monkeypatch)
    r = client.post("/api/buzz/email-send", json={"email": "a@b.com", "subject": "s", "body": "b"})
    assert r.status_code == 200
    assert r.json()["detail"] == "dry_run_ok"


def test_whatsapp_dry_run_ok(client, monkeypatch):
    _patch_suppression(monkeypatch)
    r = client.post(
        "/api/buzz/whatsapp-message", json={"phone": "919876543210", "message": "hi"}
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


# ---------------------------------------------------------------- suppression (fail-closed)
def test_suppressed_email_rejected_structured(client, monkeypatch):
    from app.platform.email_unsub import STATE_PERMANENT

    _patch_suppression(monkeypatch, STATE_PERMANENT)
    r = client.post("/api/buzz/email-send", json={"email": "x@y.com", "subject": "s", "body": "b"})
    body = r.json()
    assert body["ok"] is False
    assert body["detail"] == f"suppressed:{STATE_PERMANENT}"


def test_suppressed_phone_rejected_whatsapp(client, monkeypatch):
    from app.platform.email_unsub import STATE_QUARANTINE

    _patch_suppression(monkeypatch, STATE_QUARANTINE)
    r = client.post(
        "/api/buzz/whatsapp-message", json={"phone": "919876543210", "message": "hi"}
    )
    body = r.json()
    assert body["ok"] is False
    assert "suppressed:" in body["detail"]


# ---------------------------------------------------------------- idempotency
@pytest.mark.anyio
async def test_idempotency_duplicate_blocked():
    idem = buzz_mod.AgentRuntimeIdempotency("email")
    ok1, reason1 = await idem.check_and_claim("fp-test-1")
    ok2, reason2 = await idem.check_and_claim("fp-test-1")
    assert ok1 is True and reason1 == ""
    assert ok2 is False and reason2 == "duplicate_send_blocked"


@pytest.mark.anyio
async def test_real_send_retry_is_single_send(client, monkeypatch):
    """Retried real-send call → duplicate refusal, provider exactly once."""
    _patch_suppression(monkeypatch)
    monkeypatch.setenv("BUZZ_MCP_REAL_SEND", "1")

    calls: list[str] = []

    from app.integrations.whatsapp_selfhost import SelfHostWhatsApp

    async def fake_send(self, to_number, message):
        calls.append(to_number)
        return {"error": None}

    monkeypatch.setattr(SelfHostWhatsApp, "send_text_message", fake_send)

    payload = {"phone": "919876543210", "message": "hello", "dry_run": False}
    r1 = client.post("/api/buzz/whatsapp-message", json=payload)
    assert r1.json()["ok"] is True

    # Same payload retry → deterministic key match → duplicate blocked.
    r2 = client.post("/api/buzz/whatsapp-message", json=payload)
    body2 = r2.json()
    assert body2["ok"] is False
    assert body2["detail"] == "duplicate_send_blocked"
    assert len(calls) == 1  # exactly one real send


# ---------------------------------------------------------------- rate limits
def test_rate_limit_blocks_after_cap(client, monkeypatch):
    _patch_suppression(monkeypatch)
    last = None
    for _ in range(buzz_mod.RATE_LIMITS["whatsapp"][0] + 1):
        last = client.post(
            "/api/buzz/whatsapp-message",
            json={"phone": f"919876543{len(str(_))}", "message": f"m{_}"},
        ).json()
    assert last["ok"] is False
    assert last["detail"].startswith("rate_limited:whatsapp")


# ---------------------------------------------------------------- inert real-send
def test_real_send_refused_when_not_armed(client, monkeypatch):
    _patch_suppression(monkeypatch)
    monkeypatch.delenv("BUZZ_MCP_REAL_SEND", raising=False)
    r = client.post(
        "/api/buzz/whatsapp-message",
        json={"phone": "919876543210", "message": "hi", "dry_run": False},
    )
    body = r.json()
    assert body["ok"] is False and body["detail"] == "real_send_not_armed"


# ---------------------------------------------------------------- validation
def test_invalid_phone_422(client):
    r = client.post("/api/buzz/voice-call", json={"phone": "123"})
    assert r.status_code == 422


def test_missing_dry_run_defaults_true(client, monkeypatch):
    _patch_suppression(monkeypatch)
    monkeypatch.delenv("BUZZ_MCP_REAL_SEND", raising=False)
    # dry_run omitted -> default True -> dry_run_ok even without arming.
    r = client.post(
        "/api/buzz/email-send", json={"email": "ok@fine.in", "subject": "s", "body": "b"}
    )
    assert r.json()["dry_run"] is True
