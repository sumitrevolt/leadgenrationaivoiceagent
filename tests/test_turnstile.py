"""Cloudflare Turnstile bot-protection — full behaviour matrix.

Behaviour matrix this guards:
    SECRET unset                  -> dep is a no-op (INERT, today's behaviour)
    SECRET set + token missing    -> 403
    SECRET set + token invalid    -> 403 (Cloudflare says success=false)
    SECRET set + Cloudflare 5xx   -> pass (fail-OPEN on infra error)
    SECRET set + Cloudflare error -> pass (fail-OPEN on exception)
    SECRET set + token valid      -> pass

No real Cloudflare call: httpx is monkey-patched. Free-stack, deterministic.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.security import turnstile as ts


def _build_app() -> FastAPI:
    app = FastAPI()

    @app.post("/probe")
    async def probe(_=Depends(ts.verify_turnstile)) -> dict[str, Any]:
        return {"ok": True}

    return app


def _patch_siteverify(
    monkeypatch: pytest.MonkeyPatch,
    *,
    success: bool = True,
    status: int = 200,
    raise_exc: bool = False,
) -> dict[str, Any]:
    """Replace httpx.AsyncClient.post on the Turnstile module with a stub."""
    captured: dict[str, Any] = {}

    class _Resp:
        def __init__(self, status_code: int, payload: dict[str, Any]):
            self.status_code = status_code
            self._payload = payload

        def json(self) -> dict[str, Any]:
            return self._payload

    class _Client:
        def __init__(self, *a: Any, **kw: Any) -> None:  # noqa: ANN401
            pass

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *a: Any) -> None:  # noqa: ANN401
            return None

        async def post(self, url: str, data: dict[str, Any] | None = None, **kw: Any) -> _Resp:  # noqa: ANN401
            if raise_exc:
                raise httpx.ConnectError("simulated")
            captured["url"] = url
            captured["data"] = data
            payload = {"success": success}
            if not success:
                payload["error-codes"] = ["invalid-input-response"]
            return _Resp(status, payload)

    monkeypatch.setattr(ts.httpx, "AsyncClient", _Client)
    return captured


# --------------------------------------------------------------------------- #
# INERT mode — secret unset
# --------------------------------------------------------------------------- #
def test_inert_when_secret_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """Today's behaviour preserved: no secret -> no check, no Cloudflare call."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    captured = _patch_siteverify(monkeypatch)  # would record a call if made
    client = TestClient(_build_app())

    r = client.post("/probe", json={})
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    # Critical: did NOT call Cloudflare at all
    assert captured == {}


def test_site_key_helper_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURNSTILE_SITE_KEY", "  pk_test_abc  ")
    assert ts.site_key() == "pk_test_abc"
    monkeypatch.delenv("TURNSTILE_SITE_KEY", raising=False)
    assert ts.site_key() == ""


# --------------------------------------------------------------------------- #
# ARMED mode — secret set
# --------------------------------------------------------------------------- #
def test_armed_missing_token_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """MISSING token = widget didn't render for this client (broken site-key/
    domain, blocked CDN, mobile browser). Client-side loader already fails-OPEN,
    so the server must too — hard-403 blocked 100% of real customers whenever
    the widget was down (2026-07-04 launch incident). Fail-OPEN on missing;
    fail-CLOSED stays for PRESENT-but-INVALID tokens (real caught bots)."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    monkeypatch.delenv("TURNSTILE_STRICT_MISSING", raising=False)
    captured = _patch_siteverify(monkeypatch)
    client = TestClient(_build_app())

    r = client.post("/probe", json={})
    assert r.status_code == 200
    # Did NOT call Cloudflare — no token to verify
    assert captured == {}


def test_armed_missing_token_strict_mode_returns_403(monkeypatch: pytest.MonkeyPatch) -> None:
    """TURNSTILE_STRICT_MISSING=1 restores the old hard-403 for operators who
    have verified the widget renders and want zero-token-tolerance."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setenv("TURNSTILE_STRICT_MISSING", "1")
    captured = _patch_siteverify(monkeypatch)
    client = TestClient(_build_app())

    r = client.post("/probe", json={})
    assert r.status_code == 403
    assert "Bot-check" in r.json()["detail"]
    assert captured == {}


def test_armed_valid_token_passes_via_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    captured = _patch_siteverify(monkeypatch, success=True)
    client = TestClient(_build_app())

    r = client.post("/probe", json={}, headers={"X-Turnstile-Token": "real-token"})
    assert r.status_code == 200
    assert captured["data"]["secret"] == "sk_test_secret"
    assert captured["data"]["response"] == "real-token"


def test_armed_valid_token_passes_via_json_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """Header-less clients can send token in body (e.g. form-builders)."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    captured = _patch_siteverify(monkeypatch, success=True)
    client = TestClient(_build_app())

    r = client.post("/probe", json={"_turnstile_token": "body-token"})
    assert r.status_code == 200
    assert captured["data"]["response"] == "body-token"


def test_armed_invalid_token_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare says success=false -> 403. No silent bypass."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    _patch_siteverify(monkeypatch, success=False)
    client = TestClient(_build_app())

    r = client.post("/probe", json={}, headers={"X-Turnstile-Token": "tampered"})
    assert r.status_code == 403


def test_armed_cloudflare_5xx_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cloudflare 5xx should NOT take the funnel down (transient infra)."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    _patch_siteverify(monkeypatch, success=False, status=503)
    client = TestClient(_build_app())

    r = client.post("/probe", json={}, headers={"X-Turnstile-Token": "anything"})
    assert r.status_code == 200  # fail-OPEN: keep the funnel alive


def test_armed_cloudflare_exception_fails_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """Network exception -> pass (don't block legit users for transient errors)."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    _patch_siteverify(monkeypatch, raise_exc=True)
    client = TestClient(_build_app())

    r = client.post("/probe", json={}, headers={"X-Turnstile-Token": "anything"})
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
# Real-app wiring — /api/localseo/geo-check (2026-07-01 hardening: this fans out
# multiple free-LLM calls per public request, same abuse class as /api/public/
# ai-demo, but was previously rate-limit-only).
# --------------------------------------------------------------------------- #
def test_geo_check_inert_when_secret_unset(client, monkeypatch: pytest.MonkeyPatch) -> None:
    """Today's default (no Turnstile creds) — geo-check works with no token."""
    monkeypatch.delenv("TURNSTILE_SECRET_KEY", raising=False)
    from app.marketing import geo_visibility

    async def _fake_check(*a, **k):
        return {"ok": True, "score": 50, "verdict": "ok", "probes": [], "tips": []}

    monkeypatch.setattr(geo_visibility, "check", _fake_check)
    r = client.post(
        "/api/localseo/geo-check",
        json={"business_name": "Test Biz", "niche": "salon", "city": "Pune"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_geo_check_armed_missing_token_strict_returns_403(
    client, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Strict mode (operator verified widget) still fail-CLOSED on missing."""
    monkeypatch.setenv("TURNSTILE_SECRET_KEY", "sk_test_secret")
    monkeypatch.setenv("TURNSTILE_STRICT_MISSING", "1")
    _patch_siteverify(monkeypatch)
    r = client.post(
        "/api/localseo/geo-check",
        json={"business_name": "Test Biz", "niche": "salon", "city": "Pune"},
    )
    assert r.status_code == 403
