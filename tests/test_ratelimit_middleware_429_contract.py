"""Flat per-IP `RateLimitMiddleware` 429 contract.

The user-visible defect was the body
``{"detail": "Rate limit exceeded. Please slow down.", "retry_after": 60}``.
Three things were wrong with the path that produces it:

1. ``retry_after`` was the literal 60 even though ``app.cache.RateLimiter`` is a
   FIXED window keyed on ``int(time.time() // 60)`` — the counter resets at the
   next minute boundary, so the real wait is 1..60s.
2. ``detail`` was a bare string, so every FE 429 handler
   (``typeof j.detail === "object" ? j.detail : {}``) dropped the countdown and
   had no ``error``/``scope`` to branch on. ``app/api/ratelimit.py`` and
   ``tests/test_ratelimit_uniform_429.py`` already require a dict.
3. Static assets shared the API budget, so a single page load (StaticFiles is
   mounted on ``/``) spent it on CSS/JS/fonts.

Plus a latent write-safety bug: a failure inside ``call_next`` was caught by the
limiter's ``except`` and the request was re-run through the in-memory fallback.

Every test uses its own client IP — the limiter's backing store is process-wide
and outlives a single test.
"""

from __future__ import annotations

import json

import pytest
from starlette.requests import Request
from starlette.responses import PlainTextResponse

from app.middleware import RateLimitMiddleware, _fixed_window_retry_after, _is_asset_path


def _request(path: str = "/api/growth/summary", ip: str = "203.0.113.1") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "root_path": "",
            "headers": [(b"x-forwarded-for", ip.encode())],
            "client": (ip, 12345),
        }
    )


async def _ok(_request: Request):
    return PlainTextResponse("ok")


def _body(response) -> dict:
    return json.loads(bytes(response.body).decode())


def _force_memory(mw: RateLimitMiddleware) -> RateLimitMiddleware:
    """Drive the in-memory fallback so counting is deterministic.

    The Redis-backed limiter fail-opens on any error, which would turn a real
    regression into a silent pass. The Redis branch is covered separately by the
    stub-limiter tests below; both branches build the 429 the same way.
    """

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
        (1_800_000_000.0, 60),  # exactly on a boundary -> a full window ahead
        (1_800_000_058.0, 2),  # 58s in -> 2s left, NOT 60
        (1_800_000_059.5, 1),  # sub-second remainder still rounds up to >= 1
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
    # FEs branch on `typeof j.detail === "object"`; a string loses the countdown.
    assert isinstance(detail, dict)
    assert detail["error"] == "rate_limited"
    assert detail["scope"] == "global_ip_api"
    assert detail["message"]
    assert isinstance(detail["retry_after"], int)
    # Top-level retry_after retained for callers that already read it there.
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
    """The distributed limiter and the in-memory fallback must not diverge."""
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
    """Spending the whole asset allowance must leave API calls untouched."""
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
    """`RATE_LIMIT_ASSET_MULT=1` is the kill switch back to a single budget."""
    monkeypatch.setenv("RATE_LIMIT_ASSET_MULT", "1")
    mw = RateLimitMiddleware(app=None, requests_per_minute=3)
    assert mw._ceiling_for("asset") == mw._ceiling_for("api") == 3


# --------------------------------------------------------------------------- #
# 4. The skip list must not become an abuse hole.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "path",
    [
        "/health",
        "/metrics",
        "/api/admin/auth/login",
        "/api/customer/auth/login",
        "/api/team-access/auth/change-password",
        "/api/telephony/vobiz/stream/tok",
    ],
)
def test_skipped_paths(path: str):
    mw = RateLimitMiddleware(app=None, requests_per_minute=1)
    assert mw._should_skip(_request(path)) is True


@pytest.mark.parametrize(
    "path",
    ["/api/growth/summary", "/app/inbox", "/api/public/signup", "/pricing"],
)
def test_ordinary_paths_are_still_counted(path: str):
    mw = RateLimitMiddleware(app=None, requests_per_minute=1)
    assert mw._should_skip(_request(path)) is False


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
    """The flat limiter skips `/api/*/auth/*`, so the route dep is the only cover.

    Every path here verifies a password. If one loses its `rate_limit` dep it
    becomes unthrottled, which is exactly what the skip list assumes cannot
    happen.
    """
    import importlib

    module = importlib.import_module(module_path)
    matches = [r for r in module.router.routes if getattr(r, "path", None) == route_path]
    assert matches, f"{route_path} not found in {module_path}.router"
    for route in matches:
        names = _dependency_names(route)
        assert any(
            "rate_limit" in name for name in names
        ), f"{route_path} has no rate_limit dependency: {names}"


# --------------------------------------------------------------------------- #
# 5. A downstream failure must never silently replay the request.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_downstream_failure_is_not_retried_through_the_fallback():
    """`call_next` raising is the application's error, not a limiter error.

    Catching it alongside the limiter call meant the in-memory fallback ran the
    same request again — a duplicate write for any POST.
    """
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
