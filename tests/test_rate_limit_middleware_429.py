"""Contract: flat RateLimitMiddleware 429 shape + asset/admin policy.

User-visible defect body was historically:
  {detail: "Rate limit exceeded. Please slow down.", retry_after: 60}

Root cause: ``RateLimitMiddleware`` (production-only, ~100 rpm/IP) counted
StaticFiles CSS/JS/font hits on the SAME bucket as API calls. One admin
dashboard load burned the minute budget → every subsequent /api/* got 429
with a bare-string ``detail`` that FE handlers (login.html / pricing.html /
customer_dashboard.html) coerce to ``{}``, dropping the countdown.

Guarantees locked here:
1. 429 ``detail`` is a structured dict (FE-parseable) with the same message.
2. ``Retry-After`` header is present and equals detail.retry_after (window-aware).
3. Asset burst does NOT exhaust the API bucket.
4. Anon API still 429s after the API ceiling (abuse control intact).
5. Authenticated admin/super_admin bearer gets a higher API ceiling (not a bypass).
6. Limiter failure must NOT double-invoke call_next (write-safety).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.middleware import (
    RateLimitMiddleware,
    _fixed_window_retry_after,
    _is_asset_path,
    _rate_limit_429,
)


def _request(path: str, *, ip: str = "203.0.113.50", authorization: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", ip.encode("ascii"))]
    if authorization:
        headers.append((b"authorization", authorization.encode("ascii")))
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": b"",
            "headers": headers,
            "client": (ip, 54321),
            "server": ("testserver", 80),
        }
    )


async def _ok(_request: Request) -> PlainTextResponse:
    return PlainTextResponse("ok")


async def _no_redis(_bucket: str = "api"):
    """Force in-memory fallback — Redis path not under test."""
    return None


def test_is_asset_path_never_treats_api_as_asset():
    assert _is_asset_path("/api/admin/clients") is False
    assert _is_asset_path("/api/growth/infra/flags") is False
    assert _is_asset_path("/design-system/tokens.css") is True
    assert _is_asset_path("/site/logo.png") is True
    assert _is_asset_path("/app/admin") is False  # HTML page = not an asset
    assert _is_asset_path("/favicon.ico") is True


def test_fixed_window_retry_after_is_bounded_and_window_aware():
    # Window boundary at t=120; at t=118.1 remaining ≈ 1.9 → ceil to 2.
    assert _fixed_window_retry_after(60, now=118.1) == 2
    assert _fixed_window_retry_after(60, now=120.0) == 60
    assert 1 <= _fixed_window_retry_after(60) <= 60


def test_rate_limit_429_detail_is_structured_for_fe():
    """Bare-string detail was the UX break — FE does typeof detail === 'object'."""
    resp = _rate_limit_429(retry_after=17, scope="global_ip_api", limit=100)
    assert resp.status_code == 429
    assert resp.headers.get("Retry-After") == "17"
    assert resp.headers.get("X-RateLimit-Limit") == "100"
    payload = json.loads(resp.body)
    detail = payload["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "rate_limited"
    assert detail["message"] == "Rate limit exceeded. Please slow down."
    assert detail["retry_after"] == 17
    assert detail["scope"] == "global_ip_api"
    assert payload["retry_after"] == 17  # legacy top-level for older callers


@pytest.mark.asyncio
async def test_asset_burst_does_not_exhaust_api_bucket(monkeypatch):
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=5)
    monkeypatch.setattr(mw, "_get_limiter", _no_redis)

    # 20 asset hits — well over the API ceiling of 5 — must all pass.
    for i in range(20):
        resp = await mw.dispatch(_request(f"/design-system/chunk{i}.css"), _ok)
        assert resp.status_code == 200, f"asset {i} should not 429, got {resp.status_code}"

    # API still has its own budget of 5.
    for i in range(5):
        resp = await mw.dispatch(_request(f"/api/probe/{i}"), _ok)
        assert resp.status_code == 200
    blocked = await mw.dispatch(_request("/api/probe/over"), _ok)
    assert blocked.status_code == 429
    detail = json.loads(blocked.body)["detail"]
    assert detail["scope"] == "global_ip_api"
    assert detail["message"] == "Rate limit exceeded. Please slow down."
    assert blocked.headers.get("Retry-After") == str(detail["retry_after"])


@pytest.mark.asyncio
async def test_anon_api_still_rate_limited(monkeypatch):
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=3)
    monkeypatch.setattr(mw, "_get_limiter", _no_redis)

    codes = []
    for i in range(5):
        resp = await mw.dispatch(_request(f"/api/x/{i}", ip="198.51.100.9"), _ok)
        codes.append(resp.status_code)
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes


@pytest.mark.asyncio
async def test_admin_bearer_gets_higher_api_ceiling_not_bypass(monkeypatch):
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=3)
    monkeypatch.setattr(mw, "_get_limiter", _no_redis)

    def _admin_rpm(request: Request) -> int | None:
        auth = (request.headers.get("authorization") or "").lower()
        return 10 if auth.startswith("bearer ") else None

    monkeypatch.setattr(mw, "_admin_rpm_from_bearer", _admin_rpm)

    # Anon IP burns out at 3.
    anon_codes = [
        (await mw.dispatch(_request(f"/api/a/{i}", ip="198.51.100.20"), _ok)).status_code
        for i in range(5)
    ]
    assert 429 in anon_codes

    # Admin on a different IP with bearer gets the raised ceiling (10).
    admin_codes = []
    for i in range(12):
        resp = await mw.dispatch(
            _request(f"/api/b/{i}", ip="198.51.100.21", authorization="Bearer fake"),
            _ok,
        )
        admin_codes.append(resp.status_code)
    assert admin_codes[:10].count(200) == 10
    assert 429 in admin_codes  # still capped — not a bypass


@pytest.mark.asyncio
async def test_limiter_exception_does_not_double_call_next(monkeypatch):
    """Regression: Redis error used to catch call_next failures and re-run POST."""
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=100)

    class _Boom:
        async def is_allowed(self, _ident):
            raise RuntimeError("redis down")

    async def _limiter(_bucket: str = "api"):
        return _Boom()

    monkeypatch.setattr(mw, "_get_limiter", _limiter)

    calls = {"n": 0}

    async def _counting(_request: Request) -> PlainTextResponse:
        calls["n"] += 1
        return PlainTextResponse("once")

    resp = await mw.dispatch(_request("/api/write"), _counting)
    assert resp.status_code == 200
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_websocket_upgrade_is_not_flat_limited(monkeypatch):
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=1)
    monkeypatch.setattr(mw, "_get_limiter", _no_redis)

    # Burn the API budget.
    await mw.dispatch(_request("/api/burn"), _ok)
    blocked = await mw.dispatch(_request("/api/burn2"), _ok)
    assert blocked.status_code == 429

    # WS upgrade must still pass (voice/web-call streams).
    req = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/api/web-call/ws/token",
            "raw_path": b"/api/web-call/ws/token",
            "query_string": b"",
            "headers": [
                (b"x-forwarded-for", b"203.0.113.50"),
                (b"upgrade", b"websocket"),
            ],
            "client": ("203.0.113.50", 54321),
            "server": ("testserver", 80),
        }
    )
    resp = await mw.dispatch(req, _ok)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_auth_login_path_skips_flat_limiter_after_api_burn(monkeypatch):
    """Dashboard burn must not lock out credential POST (route deps still apply)."""
    mw = RateLimitMiddleware(app=SimpleNamespace(), requests_per_minute=1)
    monkeypatch.setattr(mw, "_get_limiter", _no_redis)

    await mw.dispatch(_request("/api/burn"), _ok)
    assert (await mw.dispatch(_request("/api/burn2"), _ok)).status_code == 429

    login = await mw.dispatch(_request("/api/customer/auth/login"), _ok)
    assert login.status_code == 200
