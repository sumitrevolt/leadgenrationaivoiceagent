"""Owner-inbox email canary — red-first refusal + idempotency tests."""

from __future__ import annotations

import asyncio

import pytest

from app.platform import owner_email_canary as canary


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(canary, "_store_dir", lambda: tmp_path)
    monkeypatch.setattr(canary, "_TIMEOUT_S", 2.0)
    yield


def test_preflight_never_requires_bulk_flag(monkeypatch):
    monkeypatch.delenv("AUTO_EMAIL_OUTREACH", raising=False)
    pf = canary.preflight()
    assert pf["ok"] is True
    assert pf["bulk_outreach_required"] is False
    assert pf["auto_email_outreach_enabled"] is False


def test_one_to_one_helper():
    assert canary.is_one_to_one("owner@example.com") is True
    assert canary.is_one_to_one("a@x.com,b@y.com") is False
    assert canary.is_one_to_one("") is False


def test_confirm_required_zero_provider():
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True, "mode": "email_sender", "provider_called": True}

    # bypass by calling send with confirm False at API layer — module requires confirm
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com", idempotency_key="idem-key-01", confirm=False
        )
    )
    assert res["outcome"] == canary.BLOCKED
    assert res["provider_called"] is False
    assert called["n"] == 0


def test_bulk_refused_zero_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    res = asyncio.run(
        canary.send_canary(
            to_email="a@x.com,b@y.com",
            idempotency_key="idem-bulk-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "bulk_or_invalid_email_refused"
    assert called["n"] == 0


def test_suppressed_zero_provider(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return {"sent": True}

    monkeypatch.setattr(canary, "_provider_send", _boom)
    monkeypatch.setattr(canary, "_suppressed", lambda e: True)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-sup-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.SKIPPED
    assert res["reason"] == "suppressed"
    assert called["n"] == 0


def test_missing_smtp_fails_closed(monkeypatch):
    async def _no(*a, **k):
        return {"sent": False, "mode": "smtp_not_configured", "provider_called": False}

    monkeypatch.setattr(canary, "_provider_send", _no)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-smtp-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.FAILED
    assert res["reason"] == "smtp_not_configured"
    assert res["provider_called"] is False


def test_timeout_unknown_no_retry(monkeypatch):
    async def _to(*a, **k):
        raise asyncio.TimeoutError()

    monkeypatch.setattr(canary, "_provider_send", _to)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    res = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-to-01",
            confirm=True,
        )
    )
    assert res["outcome"] == canary.UNKNOWN_REQUIRES_REVIEW
    assert res["reason"] == "provider_timeout_no_retry"


def test_duplicate_idempotency_sends_once(monkeypatch):
    sent = {"n": 0}

    async def _ok(*a, **k):
        sent["n"] += 1
        return {
            "sent": True,
            "mode": "email_sender",
            "provider_called": True,
            "list_unsubscribe_attached": True,
        }

    monkeypatch.setattr(canary, "_provider_send", _ok)
    monkeypatch.setattr(canary, "_suppressed", lambda e: False)
    r1 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-once-01",
            confirm=True,
        )
    )
    r2 = asyncio.run(
        canary.send_canary(
            to_email="owner@example.com",
            idempotency_key="idem-once-01",
            confirm=True,
        )
    )
    assert r1["outcome"] == canary.SENT
    assert r2["outcome"] == canary.DUPLICATE
    assert sent["n"] == 1
    assert "owner@example.com" not in str(r1)  # never echo cleartext recipient
