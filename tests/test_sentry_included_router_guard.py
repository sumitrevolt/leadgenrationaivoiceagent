"""Regression tests for the sentry-sdk <2.x `_IncludedRouter` transaction-name crash.

Prod evidence 2026-08-15: `GET /api/growth/social/token-health` 500'd with
`AttributeError: '_IncludedRouter' object has no attribute 'path'` — the REAL
error (QueuePool timeout under load) was masked because sentry-sdk 1.x's
`_transaction_name_from_router` iterates `router.routes` and returns
`route.path` on the FIRST FULL match, but FastAPI >= 0.115 stores lazy
`_IncludedRouter` wrappers in `router.routes` that have `.matches` and NO
`.path`. `app/main.py:_safe_transaction_name_from_router` is the guarded drop-in.
"""

from __future__ import annotations

import pytest
from fastapi import APIRouter, FastAPI

from app.main import _safe_transaction_name_from_router


def _naive_sentry_namer(scope):
    """Byte-for-byte mirror of sentry-sdk 1.x `_transaction_name_from_router`."""
    router = scope.get("router")
    if not router:
        return None
    for route in router.routes:
        match = route.matches(scope)
        if match[0].name == "FULL":
            return route.path
    return None


def _build_scope(app: FastAPI, path: str) -> dict:
    return {"router": app.router, "path": path, "method": "GET", "type": "http"}


def _build_app() -> FastAPI:
    sub = APIRouter()

    @sub.get("/ping")
    def _ping():
        return {"ok": True}

    top = APIRouter()
    top.include_router(sub)
    app = FastAPI()
    app.include_router(top)
    return app


def test_included_router_entries_exist_in_routes() -> None:
    app = _build_app()
    lazy = [r for r in app.router.routes if not hasattr(r, "path")]
    assert lazy, "FastAPI should expose lazy _IncludedRouter entries in routes"
    assert all(hasattr(r, "matches") for r in lazy)


def test_naive_sentry_namer_crashes_guard_returns_path() -> None:
    """Reproduce the prod crash: naive loop raises; guarded drop-in works."""
    app = _build_app()
    scope = _build_scope(app, "/ping")
    with pytest.raises(AttributeError, match="path"):
        _naive_sentry_namer(scope)
    assert _safe_transaction_name_from_router(scope) == "/ping"


def test_guard_returns_none_for_unmatched_path() -> None:
    app = _build_app()
    scope = _build_scope(app, "/nope")
    assert _safe_transaction_name_from_router(scope) is None


def test_guard_skips_routes_without_matches_or_path() -> None:
    app = _build_app()

    class _Broken:
        pass

    app.router.routes.append(_Broken())  # type: ignore[attr-defined]
    scope = _build_scope(app, "/ping")
    assert _safe_transaction_name_from_router(scope) == "/ping"


def test_guard_handles_missing_router_in_scope() -> None:
    assert _safe_transaction_name_from_router({}) is None


def test_main_patch_mechanism_applies_guard() -> None:
    """Same mechanism as app/main.py init: module-level monkeypatch sticks."""
    import sentry_sdk.integrations.starlette as sentry_starlette

    if not hasattr(sentry_starlette, "_transaction_name_from_router"):
        pytest.skip("sentry-sdk 2.x: fixed upstream, nothing to patch")

    app = _build_app()
    scope = _build_scope(app, "/ping")

    original = sentry_starlette._transaction_name_from_router
    try:
        sentry_starlette._transaction_name_from_router = _safe_transaction_name_from_router
        assert sentry_starlette._transaction_name_from_router(scope) == "/ping"
    finally:
        sentry_starlette._transaction_name_from_router = original
