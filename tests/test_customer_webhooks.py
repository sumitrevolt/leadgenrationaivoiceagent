"""customer_webhooks — CRUD, SSRF defense, HMAC sign, retries, ownership.

A paid feature gets a paid level of test discipline. The bars:
- A customer MUST NOT be able to register a URL pointing at our infra.
- A customer MUST NOT be able to read / delete another customer's webhook.
- HMAC signature MUST verify with the registered secret.
- Delivery retries MUST follow the schedule; failures MUST be logged.
- emit() MUST short-circuit when CUSTOMER_WEBHOOKS unset.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from pathlib import Path
from typing import Any

import pytest

from app.platform import customer_webhooks as cw


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cw, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(cw, "_REG_PATH", tmp_path / "registrations.jsonl")
    monkeypatch.setattr(cw, "_DEL_PATH", tmp_path / "deliveries.jsonl")
    monkeypatch.setenv("CUSTOMER_WEBHOOKS", "1")
    # Tests use http://example.com (a globally-routable host). Resolution
    # might still fall on a non-private IP — we keep DENY_PRIVATE on so
    # the SSRF path is actually exercised.
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "1")


# --------------------------------------------------------------------------- #
# Register validation
# --------------------------------------------------------------------------- #
def test_register_rejects_internal_hostnames() -> None:
    """SSRF defense: docker-network names MUST be refused (C4 lesson)."""
    out = cw.register("client_a", "http://leadgen_db:5432/hook", ["lead.qualified"])
    assert out["ok"] is False
    assert "internal" in out["error"].lower()


def test_register_rejects_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    out = cw.register("client_a", "http://127.0.0.1/hook", ["lead.qualified"])
    assert out["ok"] is False
    # Either internal hostname OR private-ip path triggers reject
    assert "private" in out["error"].lower() or "internal" in out["error"].lower()


def test_register_rejects_non_http_scheme() -> None:
    out = cw.register("client_a", "ftp://example.com/hook", ["lead.qualified"])
    assert out["ok"] is False
    assert "scheme" in out["error"].lower()


def test_register_rejects_unknown_event() -> None:
    monkeypatch_off_ssrf(["lead.notathing"])
    out = cw.register("client_a", "https://example.com/hook", ["lead.notathing"])
    assert out["ok"] is False
    assert "unknown event" in out["error"].lower()


def test_register_requires_at_least_one_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", [])
    assert out["ok"] is False


def monkeypatch_off_ssrf(_dummy: Any = None) -> None:
    """Stub used by tests that need register() to succeed without DNS."""
    import os

    os.environ["CUSTOMER_WEBHOOK_DENY_PRIVATE"] = "0"


def test_register_returns_secret_only_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])
    assert out["ok"] is True
    assert out["secret"].startswith("whsec_")
    # Subsequent list redacts
    items = cw.list_for("client_a")
    assert len(items) == 1
    assert "secret" not in items[0]
    assert "secret_preview" in items[0]
    assert "..." in items[0]["secret_preview"]


# --------------------------------------------------------------------------- #
# Ownership / IDOR
# --------------------------------------------------------------------------- #
def test_list_for_filters_by_client(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    cw.register("client_b", "https://example.com/b", ["lead.qualified"])
    assert len(cw.list_for("client_a")) == 1
    assert len(cw.list_for("client_b")) == 1


def test_remove_requires_ownership(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    wh_id = out["id"]
    # Wrong owner -> False
    assert cw.remove(wh_id, "client_b") is False
    # Right owner -> True
    assert cw.remove(wh_id, "client_a") is True


def test_get_one_refuses_cross_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    assert cw.get_one(out["id"], "client_a") is not None
    assert cw.get_one(out["id"], "client_b") is None


# --------------------------------------------------------------------------- #
# HMAC signature
# --------------------------------------------------------------------------- #
def test_signature_matches_known_pattern() -> None:
    body = b'{"a":1}'
    sig = cw._sign(body, "topsecret")
    expected = hmac.new(b"topsecret", body, hashlib.sha256).hexdigest()
    assert sig == f"sha256={expected}"


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def _async_test(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


async def test_delivery_records_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    # Fake httpx client
    class _Resp:
        status_code = 200

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, content, headers):  # noqa: ANN001
            # Verify the request shape the customer will receive
            assert headers["X-LeadGen-Event"] == "lead.qualified"
            assert headers["X-LeadGen-Signature"].startswith("sha256=")
            assert "X-LeadGen-Delivery" in headers
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    result = await cw._deliver_one(out, "lead.qualified", {"lead_id": "L1"})
    assert result["delivered"] is True
    assert result["attempts"] == 1
    rows = cw._read_deliveries()
    assert rows[-1]["delivered"] is True
    assert rows[-1]["webhook_id"] == out["id"]


async def test_delivery_retries_on_5xx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    state = {"calls": 0}

    class _Resp:
        def __init__(self, code): self.status_code = code

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, content, headers):  # noqa: ANN001
            state["calls"] += 1
            if state["calls"] < 3:
                return _Resp(503)
            return _Resp(200)

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    # Use 0-second backoff so the test runs fast
    result = await cw._deliver_one(out, "lead.qualified", {}, schedule=(0.0, 0.0, 0.0))
    assert result["delivered"] is True
    assert result["attempts"] == 3
    assert state["calls"] == 3


async def test_delivery_exhausts_retries_then_logs_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/hook", ["lead.qualified"])

    class _Resp:
        status_code = 500

    class _Client:
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, content, headers):  # noqa: ANN001
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    result = await cw._deliver_one(out, "lead.qualified", {}, schedule=(0.0, 0.0, 0.0))
    assert result["delivered"] is False
    assert result["attempts"] == 3
    rows = cw._read_deliveries()
    assert rows[-1]["delivered"] is False
    assert rows[-1]["last_status"] == 500


# --------------------------------------------------------------------------- #
# emit()
# --------------------------------------------------------------------------- #
async def test_emit_inert_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_WEBHOOKS", raising=False)
    out = await cw.emit("client_a", "lead.qualified", {})
    assert out["disabled"] is True


async def test_emit_fires_only_for_subscribed_event(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    cw.register("client_a", "https://example.com/b", ["payment.received"])

    # Stub deliver_one so emit() returns synchronously-trackable
    fired: list[tuple[str, str]] = []

    async def _stub(row, event_type, payload, delivery_id=None, schedule=None):
        fired.append((row["url"], event_type))
        return {"delivered": True}

    monkeypatch.setattr(cw, "_deliver_one", _stub)
    out = await cw.emit("client_a", "lead.qualified", {"id": "L1"})
    assert out["emitted"] == 1
    # Let the scheduled task run
    await asyncio.sleep(0)
    assert ("https://example.com/a", "lead.qualified") in fired
    assert all(u != "https://example.com/b" for u, _ in fired)


async def test_emit_skips_disabled_webhook(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")
    out = cw.register("client_a", "https://example.com/a", ["lead.qualified"])
    # Toggle off by hand-editing the row + rewriting
    rows = cw._read_registrations()
    for r in rows:
        if r["id"] == out["id"]:
            r["enabled"] = False
    cw._atomic_rewrite(rows)

    async def _stub(row, event_type, payload, delivery_id=None, schedule=None):
        return {"delivered": True}

    monkeypatch.setattr(cw, "_deliver_one", _stub)
    result = await cw.emit("client_a", "lead.qualified", {})
    assert result["emitted"] == 0
