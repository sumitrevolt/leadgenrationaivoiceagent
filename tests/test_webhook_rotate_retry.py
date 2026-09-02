"""K.2 + K.3 — webhook rotate_secret + retry_delivery.

Operationally critical: rotation must NOT lose subscriptions; retry must NOT
succeed if the underlying delivery already succeeded (idempotency).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.platform import customer_webhooks as cw


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cw, "_DATA_DIR", tmp_path)
    monkeypatch.setattr(cw, "_REG_PATH", tmp_path / "registrations.jsonl")
    monkeypatch.setattr(cw, "_DEL_PATH", tmp_path / "deliveries.jsonl")
    monkeypatch.setenv("CUSTOMER_WEBHOOKS", "1")
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "0")


# --------------------------------------------------------------------------- #
# K.3 rotate_secret
# --------------------------------------------------------------------------- #
def test_rotate_secret_returns_new_value() -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    old = reg["secret"]
    out = cw.rotate_secret(reg["id"], "client_a")
    assert out["ok"] is True
    assert out["secret"] != old
    assert out["secret"].startswith("whsec_")


def test_rotate_secret_preserves_subscription_id_and_events() -> None:
    """Rotation MUST keep the webhook id + events list intact (the only
    thing changing is the secret + the rotated_at timestamp)."""
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified", "payment.received"])
    cw.rotate_secret(reg["id"], "client_a")
    after = cw.list_for("client_a")[0]
    assert after["id"] == reg["id"]
    assert sorted(after["events"]) == sorted(["lead.qualified", "payment.received"])


def test_rotate_secret_refuses_other_client() -> None:
    """Cross-tenant IDOR check — rotating another customer's secret MUST fail."""
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    out = cw.rotate_secret(reg["id"], "client_b")
    assert out["ok"] is False
    assert out["error"] == "not_found"


def test_rotate_persists_rotated_at() -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    cw.rotate_secret(reg["id"], "client_a")
    rows = cw._read_registrations()
    assert "secret_rotated_at" in rows[0]


# --------------------------------------------------------------------------- #
# K.2 retry_delivery
# --------------------------------------------------------------------------- #
async def test_retry_failed_delivery(monkeypatch: pytest.MonkeyPatch) -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    # Seed a failed delivery row by hand
    cw._append_delivery(
        {
            "id": "del_failed1",
            "webhook_id": reg["id"],
            "client_id": "client_a",
            "event_type": "lead.qualified",
            "url": reg["url"],
            "attempts": 3,
            "last_status": 500,
            "delivered": False,
            "at": 1700000000,
        }
    )

    class _Resp:
        status_code = 200

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content, headers):  # noqa: ANN001
            assert headers["X-LeadGen-Event"] == "lead.qualified"
            return _Resp()

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())
    out = await cw.retry_delivery(reg["id"], "client_a", "del_failed1")
    assert out["delivered"] is True


async def test_retry_unknown_delivery_returns_error() -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    out = await cw.retry_delivery(reg["id"], "client_a", "del_nope")
    assert out.get("error") == "delivery_not_found"


async def test_retry_succeeded_delivery_refuses() -> None:
    """Already-succeeded deliveries must NOT be re-fired (idempotency)."""
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    cw._append_delivery(
        {
            "id": "del_ok",
            "webhook_id": reg["id"],
            "client_id": "client_a",
            "event_type": "lead.qualified",
            "url": reg["url"],
            "attempts": 1,
            "last_status": 200,
            "delivered": True,
            "at": 1700000000,
        }
    )
    out = await cw.retry_delivery(reg["id"], "client_a", "del_ok")
    assert out.get("error") == "delivery_already_succeeded"


async def test_retry_cross_tenant_rejected() -> None:
    reg = cw.register("client_a", "https://example.com/h", ["lead.qualified"])
    cw._append_delivery(
        {
            "id": "del_xfail",
            "webhook_id": reg["id"],
            "client_id": "client_a",
            "event_type": "lead.qualified",
            "url": reg["url"],
            "attempts": 3,
            "last_status": 500,
            "delivered": False,
            "at": 1700000000,
        }
    )
    out = await cw.retry_delivery(reg["id"], "client_b", "del_xfail")
    # client_b doesn't own the webhook -> get_one returns None -> webhook_not_found
    assert out.get("error") == "webhook_not_found"


# --------------------------------------------------------------------------- #
# SSRF TOCTOU regression (production audit 2026-07-01, security batch 2):
# _is_url_safe() only ran at register() time. A customer could register a
# webhook against a hostname resolving to a public IP, then repoint DNS to an
# internal address (127.0.0.1 / 169.254.169.254 / docker service name) before
# delivery or a later retry fires. Fixed by re-checking immediately before
# each connect attempt inside _deliver_one().
# --------------------------------------------------------------------------- #
async def test_delivery_blocked_when_url_becomes_unsafe(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even with a delivery row already queued, a URL that now resolves to a
    private/internal address must be refused — httpx must never be called."""
    monkeypatch.setenv("CUSTOMER_WEBHOOK_DENY_PRIVATE", "1")  # override the fixture's "0"

    called = {"post": False}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        async def post(self, url, content, headers):  # noqa: ANN001
            called["post"] = True
            raise AssertionError("httpx.post must not be called for an unsafe URL")

    import httpx as _httpx

    monkeypatch.setattr(_httpx, "AsyncClient", lambda *a, **kw: _Client())

    row = {
        "id": "wh_rebind_test",
        "client_id": "client_a",
        "url": "http://127.0.0.1:9999/internal",  # simulates a rebound hostname
        "secret": "whsec_test",
    }
    out = await cw._deliver_one(row, "lead.qualified", {"x": 1}, schedule=(0.0,))

    assert out["delivered"] is False
    assert called["post"] is False, "SSRF: request was sent to a private-IP URL"
    assert "url_unsafe" in out["error"]
