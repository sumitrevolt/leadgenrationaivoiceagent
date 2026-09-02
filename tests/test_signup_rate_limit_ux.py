"""Signup 429 response contract.

The rate-bucket algorithm and middleware have separate coverage.  These tests
exercise ``public_signup`` directly so the structured detail, Retry-After header
and admin audit event stay deterministic without creating accounts.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request


def _trigger_signup_limit(monkeypatch) -> HTTPException:
    from app.api import public_site as ps

    async def _limited(_ip: str, _bucket: str = "signup") -> None:
        raise HTTPException(status_code=429, detail="limited")

    monkeypatch.setattr(ps, "_rate_check", _limited)
    body = ps.SignupIn(
        business_name="Rate Test Business",
        email="rate@example.com",
        password="secret123",
        plan="starter",
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/public/signup",
            "headers": [],
            "client": ("testclient", 12345),
        }
    )
    with pytest.raises(HTTPException) as caught:
        asyncio.run(ps.public_signup(body, request))
    return caught.value


def test_signup_429_carries_retry_after_header(monkeypatch):
    exc = _trigger_signup_limit(monkeypatch)

    assert exc.status_code == 429
    assert exc.headers and exc.headers.get("Retry-After")
    retry_after = int(exc.headers["Retry-After"])
    assert 1 <= retry_after <= 600


def test_signup_429_detail_is_structured_with_reason(monkeypatch):
    exc = _trigger_signup_limit(monkeypatch)

    detail = exc.detail
    assert isinstance(detail, dict)
    assert detail.get("error") == "rate_limited"
    assert detail.get("scope") == "signup_ip"
    assert isinstance(detail.get("retry_after"), int)
    assert detail.get("message")


def test_signup_429_emits_admin_automation_log(monkeypatch):
    import app.platform.automation_log_service as als

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    _trigger_signup_limit(monkeypatch)

    rows = [row for row in captured if row.get("job_type") == "signup_rate_limited"]
    assert len(rows) == 1
    row = rows[0]
    assert row.get("status") == "failed"
    assert row.get("triggered_by") == "signup"
    meta = row.get("meta_json") or {}
    assert meta.get("ip") == "testclient"
    assert meta.get("scope") == "signup_ip"
