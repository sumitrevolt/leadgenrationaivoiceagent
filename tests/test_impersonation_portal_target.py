"""Tests for the impersonation landing-target (`to` / `portal_url`) feature.

Why this exists: `portal_url` is echoed to the browser and then followed by the
frontend (`frontend/impersonate.html` -> `window.open(j.portal_url)`). A free-form
value would be an open redirect, which is why it is validated against
`PORTAL_ALLOWLIST`. These tests lock that invariant down.

Also covers `/api/impersonate/targets` exposing each client's `product`, which is
what lets an operator pick the right console per client instead of guessing.
No full app / DB — pure-function tests plus coroutines with faked deps.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.api import impersonation as imp


# --------------------------------------------------------------------------
# _safe_portal_url — the open-redirect gate
# --------------------------------------------------------------------------

@pytest.mark.parametrize("target", list(imp.PORTAL_ALLOWLIST))
def test_allowlisted_targets_are_honoured(target):
    assert imp._safe_portal_url(target) == target


@pytest.mark.parametrize(
    "hostile",
    [
        "https://evil.example.com/app/customer",   # absolute URL
        "http://evil.example.com",                 # absolute, no path
        "//evil.example.com/app/customer",         # protocol-relative
        "javascript:alert(1)",                     # scheme handler
        "/app/customer?next=//evil.example.com",   # query smuggling
        "/app/customer/../../admin",               # traversal
        "/app/voice-console/",                     # trailing slash - not a member
        "/app/voice-console?x=1",                  # query - not a member
        "/app/not-a-page",                         # unknown path
        "/",                                       # root
        "",                                        # empty -> default
        None,                                      # missing -> default
        "APP/VOICE-CONSOLE",                       # case must not be coerced
    ],
)
def test_hostile_targets_fall_back_to_customer_dashboard(hostile):
    """Nothing outside the allowlist may ever reach the browser."""
    assert imp._safe_portal_url(hostile) == "/app/customer"


def test_default_is_stable_when_feature_is_not_used():
    """Callers that predate `to` must keep landing on /app/customer."""
    assert imp._safe_portal_url("") == "/app/customer"


def test_allowlist_contains_no_external_or_relative_entries():
    """Guard against someone later adding an unsafe entry to the allowlist."""
    for t in imp.PORTAL_ALLOWLIST:
        assert t.startswith("/app/"), f"allowlist entry must be an /app path: {t}"
        assert "://" not in t and not t.startswith("//")
        assert "?" not in t and "#" not in t


# --------------------------------------------------------------------------
# _client_product — entitlement normalisation
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("voice", "voice"),
        ("marketing", "marketing"),
        ("combo", "combo"),
        ("  VOICE  ", "voice"),       # trimmed + lowercased
        ("", "marketing"),            # missing -> safe default
        (None, "marketing"),          # missing -> safe default
        ("bogus", "marketing"),       # unknown -> safe default
    ],
)
def test_client_product_normalisation(monkeypatch, raw, expected):
    class _FakeStore:
        @staticmethod
        def get_client(_cid):
            return {"product": raw}

    import sys
    import types

    fake = types.ModuleType("app.marketing.clients_store")
    fake.get_client = _FakeStore.get_client
    monkeypatch.setitem(sys.modules, "app.marketing.clients_store", fake)

    assert imp._client_product("cli1") == expected


def test_client_product_defaults_when_store_raises(monkeypatch):
    """A broken client store must not break impersonation — fail safe."""
    import sys
    import types

    fake = types.ModuleType("app.marketing.clients_store")

    def _boom(_cid):
        raise RuntimeError("store unavailable")

    fake.get_client = _boom
    monkeypatch.setitem(sys.modules, "app.marketing.clients_store", fake)

    assert imp._client_product("cli1") == "marketing"


# --------------------------------------------------------------------------
# /api/impersonate/targets exposes product
# --------------------------------------------------------------------------

def test_targets_include_product(monkeypatch):
    import sys
    import types

    monkeypatch.setenv("IMPERSONATION", "1")

    rows = [
        {"client_id": "cli_v", "email": "v@x.com"},
        {"client_id": "cli_m", "email": "m@x.com"},
        {"client_id": "cli_c", "email": "c@x.com"},
    ]
    products = {"cli_v": "voice", "cli_m": "marketing", "cli_c": "combo"}

    # customer_auth._read supplies the login rows
    fake_auth = types.ModuleType("app.api.customer_auth")
    fake_auth._read = lambda: rows
    monkeypatch.setitem(sys.modules, "app.api.customer_auth", fake_auth)

    # clients_store supplies business_name + product
    fake_store = types.ModuleType("app.marketing.clients_store")
    fake_store.get_client = lambda cid: {
        "business_name": cid.upper(),
        "product": products.get(cid, "marketing"),
    }
    monkeypatch.setitem(sys.modules, "app.marketing.clients_store", fake_store)

    out = asyncio.run(imp.impersonation_targets(admin=type("A", (), {"id": "a1"})()))

    by_id = {t["client_id"]: t for t in out["targets"]}
    assert set(by_id) == {"cli_v", "cli_m", "cli_c"}
    assert by_id["cli_v"]["product"] == "voice"
    assert by_id["cli_m"]["product"] == "marketing"
    assert by_id["cli_c"]["product"] == "combo"
    assert by_id["cli_v"]["business_name"] == "CLI_V"


# --------------------------------------------------------------------------
# /api/impersonate/start echoes a validated portal_url
# --------------------------------------------------------------------------

class _FakeAdmin:
    id = "admin-1"
    email = "boss@leadsgenai.in"


class _FakeReq:
    headers = {"x-forwarded-for": "1.2.3.4"}
    client = type("C", (), {"host": "9.9.9.9"})()


class _FakeDB:
    async def commit(self):
        return None


@pytest.mark.parametrize(
    "to,expected",
    [
        ("/app/voice-console", "/app/voice-console"),
        ("/app/marketing-console", "/app/marketing-console"),
        ("/app/customer", "/app/customer"),
        ("https://evil.example.com/x", "/app/customer"),  # open redirect blocked
        ("", "/app/customer"),                            # absent -> default
    ],
)
def test_start_echoes_validated_portal_url(monkeypatch, to, expected):
    monkeypatch.setenv("IMPERSONATION", "1")

    import sys
    import types

    fake_store = types.ModuleType("app.marketing.clients_store")
    fake_store.get_client = lambda cid: {"business_name": "Test Co", "product": "combo"}
    monkeypatch.setitem(sys.modules, "app.marketing.clients_store", fake_store)

    fake_auth = types.ModuleType("app.api.customer_auth")
    fake_auth._read = lambda: [{"client_id": "cli1", "email": "c@x.com"}]
    monkeypatch.setitem(sys.modules, "app.api.customer_auth", fake_auth)

    async def _noop_audit(*_a, **_k):
        return None

    monkeypatch.setattr(imp, "log_audit", _noop_audit)

    body = imp.ImpersonateIn(client_id="cli1", reason="support", to=to)
    res = asyncio.run(
        imp.impersonation_start(
            body=body,
            request=_FakeReq(),
            admin=_FakeAdmin(),
            db=_FakeDB(),
        )
    )

    assert res["portal_url"] == expected
    assert res["client_id"] == "cli1"
    assert res["impersonation"] is True


def test_start_rejects_unknown_client(monkeypatch):
    monkeypatch.setenv("IMPERSONATION", "1")

    import sys
    import types

    fake_store = types.ModuleType("app.marketing.clients_store")
    fake_store.get_client = lambda cid: {}
    monkeypatch.setitem(sys.modules, "app.marketing.clients_store", fake_store)

    fake_auth = types.ModuleType("app.api.customer_auth")
    fake_auth._read = lambda: []
    monkeypatch.setitem(sys.modules, "app.api.customer_auth", fake_auth)

    body = imp.ImpersonateIn(client_id="nope", reason="", to="/app/voice-console")
    with pytest.raises(HTTPException) as ei:
        asyncio.run(
            imp.impersonation_start(
                body=body, request=_FakeReq(), admin=_FakeAdmin(), db=_FakeDB()
            )
        )
    assert ei.value.status_code == 404
