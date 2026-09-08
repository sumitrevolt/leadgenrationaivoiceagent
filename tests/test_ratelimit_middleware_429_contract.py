"""Flat per-IP `RateLimitMiddleware` 429 contract (+ P1 safety harden).

Original UX defect body:
``{"detail": "Rate limit exceeded. Please slow down.", "retry_after": 60}``.

Root causes locked here:
1. Fixed-window ``Retry-After`` (not hardcoded 60).
2. Structured dict ``detail`` for FE countdown parsers.
3. Static assets use a separate higher bucket (not an exemption).
4. Limiter failure must never double-invoke ``call_next`` (no write replay).

P1 safety (cloud review @ 662c2b3):
5. No broad auth/telephony prefix bypass — logout/reset/test-call stay limited.
6. Canonical trusted IP = rightmost XFF (middleware + ``app.api.ratelimit``).
7. Admin raised ceiling only for explicit safe GET/HEAD dashboard reads;
   admin POST stays on the default API budget.
"""

from __future__ import annotations

import json

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.middleware import (
    RateLimitMiddleware,
    _fixed_window_retry_after,
    _is_asset_path,
    _is_html_navigation,
    _is_safe_idempotent_admin_read,
    _real_client_ip,
)


def _request(
    path: str = "/api/growth/summary",
    ip: str = "203.0.113.1",
    *,
    method: str = "GET",
    authorization: str | None = None,
    xff: str | None = None,
    extra_headers: list[tuple[bytes, bytes]] | None = None,
) -> Request:
    forwarded = xff if xff is not None else ip
    headers: list[tuple[bytes, bytes]] = [(b"x-forwarded-for", forwarded.encode())]
    if authorization:
        headers.append((b"authorization", authorization.encode()))
    if extra_headers:
        headers.extend(extra_headers)
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
            "headers": headers,
            "client": (ip.split(",")[-1].strip(), 12345),
        }
    )


async def _ok(_request: Request):
    return PlainTextResponse("ok")


def _body(response) -> dict:
    return json.loads(bytes(response.body).decode())


def _force_memory(mw: RateLimitMiddleware) -> RateLimitMiddleware:
    """Drive the in-memory fallback so counting is deterministic."""

    async def _none(_bucket: str = "api"):
        return None

    mw._get_limiter = _none
    return mw


# --------------------------------------------------------------------------- #
# 1. Retry-After must describe the real fixed-window reset, not a constant 60.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        (1_800_000_000.0, 60),
        (1_800_000_058.0, 2),
        (1_800_000_059.5, 1),
        (1_800_000_030.0, 30),
    ],
)
def test_retry_after_tracks_the_fixed_window(now: float, expected: int):
    assert _fixed_window_retry_after(60, now=now) == expected


def test_retry_after_is_never_zero_or_over_the_window():
    for offset in range(60):
        value = _fixed_window_retry_after(60, now=1_800_000_000.0 + offset + 0.25)
        assert 1 <= value <= 60


# --------------------------------------------------------------------------- #
# 2. Uniform 429 body — identical contract to app/api/ratelimit.py.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_middleware_429_detail_is_a_dict_with_the_uniform_fields():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    ip = "203.0.113.11"

    await mw.dispatch(_request(ip=ip), _ok)
    blocked = await mw.dispatch(_request(ip=ip), _ok)

    assert blocked.status_code == 429
    body = _body(blocked)
    detail = body["detail"]
    assert isinstance(detail, dict)
    assert detail["error"] == "rate_limited"
    assert detail["scope"] == "global_ip_api"
    assert detail["message"] == "Rate limit exceeded. Please slow down."
    assert isinstance(detail["retry_after"], int)
    assert body["retry_after"] == detail["retry_after"]


@pytest.mark.asyncio
async def test_middleware_429_header_matches_body_and_is_not_hardcoded_60():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    ip = "203.0.113.12"

    await mw.dispatch(_request(ip=ip), _ok)
    blocked = await mw.dispatch(_request(ip=ip), _ok)

    retry_after = _body(blocked)["detail"]["retry_after"]
    assert blocked.headers["Retry-After"] == str(retry_after)
    assert 1 <= retry_after <= 60
    assert blocked.headers["X-RateLimit-Limit"] == "1"
    assert blocked.headers["X-RateLimit-Remaining"] == "0"


@pytest.mark.asyncio
async def test_redis_branch_emits_the_same_uniform_429():
    mw = RateLimitMiddleware(app=None, requests_per_minute=7)

    class _DenyAll:
        async def is_allowed(self, _ident):
            return False, 0

    mw._limiters["api"] = _DenyAll()
    blocked = await mw.dispatch(_request(ip="203.0.113.16"), _ok)

    assert blocked.status_code == 429
    detail = _body(blocked)["detail"]
    assert detail["error"] == "rate_limited"
    assert detail["scope"] == "global_ip_api"
    assert blocked.headers["Retry-After"] == str(detail["retry_after"])
    assert blocked.headers["X-RateLimit-Limit"] == "7"


# --------------------------------------------------------------------------- #
# 3. Static assets get their own budget instead of eating the API budget.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "/design-system/tokens.css",
        "/static/app.js",
        "/logo.svg",
        "/fonts/inter.woff2",
        "/unity/build.wasm",
    ],
)
def test_asset_paths_are_classified_as_assets(path: str):
    assert _is_asset_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "/api/growth/summary",
        "/api/marketing/leads.js",
        "/app/inbox",
        "/pricing",
        "/",
    ],
)
def test_api_and_page_paths_are_never_assets(path: str):
    assert _is_asset_path(path) is False


@pytest.mark.asyncio
async def test_page_assets_do_not_exhaust_the_api_budget(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ASSET_MULT", "5")
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=2))
    ip = "203.0.113.13"
    asset = "/design-system/tokens.css"

    for _ in range(mw._ceiling_for("asset")):
        allowed = await mw.dispatch(_request(asset, ip=ip), _ok)
        assert allowed.status_code == 200
    blocked = await mw.dispatch(_request(asset, ip=ip), _ok)
    assert blocked.status_code == 429
    assert _body(blocked)["detail"]["scope"] == "global_ip_asset"

    api = await mw.dispatch(_request("/api/growth/summary", ip=ip), _ok)
    assert api.status_code == 200


@pytest.mark.asyncio
async def test_asset_mult_of_one_collapses_the_asset_ceiling(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ASSET_MULT", "1")
    mw = RateLimitMiddleware(app=None, requests_per_minute=3)
    assert mw._ceiling_for("asset") == mw._ceiling_for("api") == 3


# --------------------------------------------------------------------------- #
# 3a. Human HTML page navigation = own higher bucket (2026-08-02 429 burst).
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "/app/admin",
        "/app/admin/",
        "/app/customer",
        "/app/automation",
        "/app/whatsapp",
        "/app/admin-login",
        "/app/test-call",
        "/pricing",
        "/start",
        "/voice-agent",
    ],
)
def test_html_page_navigation_is_classified_as_html(path: str):
    assert _is_html_navigation(_request(path, method="GET")) is True
    assert _is_html_navigation(_request(path, method="HEAD")) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/app/admin"),
        ("POST", "/pricing"),
        ("GET", "/api/growth/summary"),
        ("GET", "/api/marketing/leads"),
        ("GET", "/"),
        ("GET", "/blog"),
        ("GET", "/design-system/tokens.css"),
    ],
)
def test_html_navigation_helper_never_catches_writes_api_or_other_paths(method: str, path: str):
    assert _is_html_navigation(_request(path, method=method)) is False


@pytest.mark.asyncio
async def test_page_load_burst_does_not_exhaust_the_api_budget(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_HTML_MULT", "10")
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=5))
    ip = "203.0.113.17"
    page = "/app/admin"

    for _ in range(mw._ceiling_for("html")):
        allowed = await mw.dispatch(_request(page, ip=ip), _ok)
        assert allowed.status_code == 200
    blocked = await mw.dispatch(_request(page, ip=ip), _ok)
    assert blocked.status_code == 429
    assert _body(blocked)["detail"]["scope"] == "global_ip_html"

    api = await mw.dispatch(_request("/api/growth/summary", ip=ip), _ok)
    assert api.status_code == 200


@pytest.mark.asyncio
async def test_page_loads_do_not_trip_a_low_shared_api_ceiling(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_HTML_MULT", "10")
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=2))
    ip = "203.0.113.18"

    for i in range(3):
        code = (await mw.dispatch(_request(f"/pricing?tab={i}", ip=ip), _ok)).status_code
        assert code == 200


@pytest.mark.asyncio
async def test_html_post_stays_on_default_api_budget(monkeypatch):
    """Page-navigation relief must NEVER apply to writes."""
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=2))
    ip = "203.0.113.19"

    for _ in range(mw._ceiling_for("api")):
        assert (
            await mw.dispatch(_request("/app/admin", ip=ip, method="POST"), _ok)
        ).status_code == 200
    blocked = await mw.dispatch(_request("/app/admin", ip=ip, method="POST"), _ok)
    assert blocked.status_code == 429
    assert _body(blocked)["detail"]["scope"] == "global_ip_api"


# --------------------------------------------------------------------------- #
# 3b. Admin raised ceiling = GET/HEAD dashboard relief only (not writes).
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_admin_get_dashboard_read_gets_higher_ceiling_not_bypass(monkeypatch):
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=3))

    def _admin_rpm(request: Request) -> int | None:
        auth = (request.headers.get("authorization") or "").lower()
        return 10 if auth.startswith("bearer ") else None

    monkeypatch.setattr(mw, "_admin_rpm_from_bearer", _admin_rpm)

    anon_ip = "198.51.100.20"
    anon_codes = [
        (await mw.dispatch(_request(f"/api/a/{i}", ip=anon_ip), _ok)).status_code for i in range(5)
    ]
    assert 429 in anon_codes

    admin_ip = "198.51.100.21"
    admin_codes = []
    for i in range(12):
        resp = await mw.dispatch(
            _request(
                f"/api/growth/probe/{i}",
                ip=admin_ip,
                method="GET",
                authorization="Bearer fake",
            ),
            _ok,
        )
        admin_codes.append(resp.status_code)
    assert admin_codes[:10].count(200) == 10
    assert 429 in admin_codes


@pytest.mark.asyncio
async def test_admin_post_stays_on_default_api_budget(monkeypatch):
    """P1: admin bearer must NOT raise the ceiling for writes/external actions."""
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=3))

    def _admin_rpm(request: Request) -> int | None:
        return 600

    monkeypatch.setattr(mw, "_admin_rpm_from_bearer", _admin_rpm)
    ip = "198.51.100.30"

    codes = []
    for i in range(5):
        resp = await mw.dispatch(
            _request(
                f"/api/admin/clients/{i}",
                ip=ip,
                method="POST",
                authorization="Bearer fake",
            ),
            _ok,
        )
        codes.append(resp.status_code)
    assert codes[:3] == [200, 200, 200]
    assert 429 in codes
    blocked = await mw.dispatch(
        _request("/api/admin/clients/x", ip=ip, method="POST", authorization="Bearer fake"),
        _ok,
    )
    assert blocked.status_code == 429
    assert _body(blocked)["detail"]["scope"] == "global_ip_api"


def test_safe_admin_read_helper_is_method_and_prefix_gated():
    assert _is_safe_idempotent_admin_read(_request("/api/growth/summary", method="GET")) is True
    assert _is_safe_idempotent_admin_read(_request("/api/admin/clients", method="HEAD")) is True
    assert _is_safe_idempotent_admin_read(_request("/api/admin/clients", method="POST")) is False
    assert _is_safe_idempotent_admin_read(_request("/api/billing/charge", method="GET")) is False


@pytest.mark.asyncio
async def test_websocket_upgrade_is_not_flat_limited():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    ip = "203.0.113.50"

    await mw.dispatch(_request("/api/burn", ip=ip), _ok)
    blocked = await mw.dispatch(_request("/api/burn2", ip=ip), _ok)
    assert blocked.status_code == 429

    ws_req = _request(
        "/api/web-call/ws/token",
        ip=ip,
        extra_headers=[(b"upgrade", b"websocket")],
    )
    resp = await mw.dispatch(ws_req, _ok)
    assert resp.status_code == 200


# --------------------------------------------------------------------------- #
# 4. Skip list must stay narrow — auth writes + telephony actions stay limited.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    ["/health", "/metrics", "/api/web-call/ws/token", "/robots.txt"],
)
def test_narrow_safe_paths_may_skip(path: str):
    mw = RateLimitMiddleware(app=None, requests_per_minute=1)
    assert mw._should_skip(_request(path)) is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/admin/auth/logout"),
        ("POST", "/api/customer/auth/login"),
        ("POST", "/api/customer/auth/change-password"),
        ("POST", "/api/team-access/auth/change-password"),
        ("POST", "/api/admin/auth/reset-password"),
        ("POST", "/api/telephony/vobiz/test-call"),
        ("POST", "/api/telephony/vobiz/stream-call"),
        ("GET", "/api/telephony/vobiz/stream/tok"),
        ("GET", "/api/growth/summary"),
        ("GET", "/app/inbox"),
        ("POST", "/api/public/signup"),
    ],
)
def test_auth_writes_and_telephony_actions_are_not_skipped(method: str, path: str):
    mw = RateLimitMiddleware(app=None, requests_per_minute=1)
    assert mw._should_skip(_request(path, method=method)) is False


@pytest.mark.asyncio
async def test_auth_logout_still_globally_limited_after_api_burn():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    ip = "203.0.113.51"

    await mw.dispatch(_request("/api/burn", ip=ip), _ok)
    assert (await mw.dispatch(_request("/api/burn2", ip=ip), _ok)).status_code == 429

    logout = await mw.dispatch(
        _request("/api/admin/auth/logout", ip=ip, method="POST"),
        _ok,
    )
    assert logout.status_code == 429


@pytest.mark.asyncio
async def test_telephony_test_call_still_globally_limited_after_api_burn():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    ip = "203.0.113.52"

    await mw.dispatch(_request("/api/burn", ip=ip), _ok)
    assert (await mw.dispatch(_request("/api/burn2", ip=ip), _ok)).status_code == 429

    call = await mw.dispatch(
        _request("/api/telephony/vobiz/test-call", ip=ip, method="POST"),
        _ok,
    )
    assert call.status_code == 429


def _dependency_names(route) -> list[str]:
    return [
        getattr(getattr(dep, "dependency", None), "__qualname__", "")
        for dep in (getattr(route, "dependencies", None) or [])
    ]


@pytest.mark.parametrize(
    ("module_path", "route_path"),
    [
        ("app.api.admin", "/admin/auth/login"),
        ("app.api.customer_auth", "/customer/auth/login"),
        ("app.api.customer_auth", "/customer/auth/change-password"),
        ("app.api.team_access", "/team-access/auth/change-password"),
    ],
)
def test_credential_routes_keep_their_own_rate_limit(module_path: str, route_path: str):
    """Defense-in-depth: route deps still present even though global limiter covers auth."""
    import importlib

    module = importlib.import_module(module_path)
    matches = [r for r in module.router.routes if getattr(r, "path", None) == route_path]
    assert matches, f"{route_path} not found in {module_path}.router"
    for route in matches:
        names = _dependency_names(route)
        assert any("rate_limit" in name for name in names), (
            f"{route_path} has no rate_limit dependency: {names}"
        )


# --------------------------------------------------------------------------- #
# 4b. Multi-value XFF cannot evade — rightmost is canonical for both layers.
# --------------------------------------------------------------------------- #


def test_real_client_ip_uses_rightmost_xff():
    req = _request("/api/growth/summary", xff="198.51.100.99, 203.0.113.77")
    assert _real_client_ip(req) == "203.0.113.77"


def test_ratelimit_dep_ip_matches_middleware_canonical():
    from app.api import ratelimit as rl

    req = _request("/api/x", xff="8.8.8.8, 203.0.113.88")
    assert rl._client_ip(req) == _real_client_ip(req) == "203.0.113.88"


@pytest.mark.asyncio
async def test_spoofed_leftmost_xff_cannot_evade_flat_limiter():
    mw = _force_memory(RateLimitMiddleware(app=None, requests_per_minute=1))
    real_ip = "203.0.113.60"

    await mw.dispatch(_request("/api/burn", ip=real_ip, xff=real_ip), _ok)
    blocked = await mw.dispatch(_request("/api/burn2", ip=real_ip, xff=real_ip), _ok)
    assert blocked.status_code == 429

    # Attacker prepends a fresh leftmost IP — rightmost (trusted) still burned.
    evade = await mw.dispatch(
        _request("/api/burn3", ip=real_ip, xff=f"198.51.100.1, {real_ip}"),
        _ok,
    )
    assert evade.status_code == 429


# --------------------------------------------------------------------------- #
# 5. A downstream failure must never silently replay the request.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_downstream_failure_is_not_retried_through_the_fallback():
    mw = RateLimitMiddleware(app=None, requests_per_minute=100)

    class _AllowAll:
        async def is_allowed(self, _ident):
            return True, 99

    mw._limiters["api"] = _AllowAll()
    calls: list[str] = []

    async def _explodes(_request: Request):
        calls.append("x")
        raise RuntimeError("downstream boom")

    with pytest.raises(RuntimeError):
        await mw.dispatch(_request("/api/billing/charge", ip="203.0.113.14"), _explodes)

    assert len(calls) == 1, "request must not be replayed after a downstream failure"


@pytest.mark.asyncio
async def test_limiter_failure_still_falls_back_without_double_execution():
    mw = RateLimitMiddleware(app=None, requests_per_minute=100)

    class _Broken:
        async def is_allowed(self, _ident):
            raise ConnectionError("redis down")

    mw._limiters["api"] = _Broken()
    calls: list[str] = []

    async def _counting(_request: Request):
        calls.append("x")
        return PlainTextResponse("ok")

    response = await mw.dispatch(_request(ip="203.0.113.15"), _counting)

    assert response.status_code == 200
    assert len(calls) == 1
