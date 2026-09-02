"""Unit tests for app/api/impersonation.py — super-admin "login as customer".

Critical invariants: flag-gating (404 when off), token is customer-role + imp-marked,
audit is called on start. No full app / DB — coroutines direct, deps faked.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.api import impersonation as imp


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("IMPERSONATION", raising=False)
    monkeypatch.delenv("IMPERSONATION_TTL_MIN", raising=False)
    yield


class _FakeAdmin:
    id = "admin-1"
    email = "boss@leadsgenai.in"


class _FakeReq:
    def __init__(self, ip="1.2.3.4"):
        self.headers = {"x-forwarded-for": ip}
        self.client = type("C", (), {"host": "9.9.9.9"})()


def test_token_is_customer_role_with_imp_markers(monkeypatch):
    monkeypatch.setenv("IMPERSONATION", "1")
    tok = imp._mint_impersonation_token("cli9", "c@x.com", "admin-1", "boss@x.com")
    from app.api.admin import decode_token

    p = decode_token(tok)
    assert p["role"] == "customer"  # works in customer portal
    assert p["sub"] == "cli9"
    assert p["imp"] is True
    assert p["imp_by"] == "admin-1"

    # and require_customer (the portal gate) accepts it
    from fastapi.security import HTTPAuthorizationCredentials

    from app.api.customer_auth import require_customer

    cid = asyncio.run(
        require_customer(HTTPAuthorizationCredentials(scheme="Bearer", credentials=tok))
    )
    assert cid == "cli9"


def test_guard_blocks_when_disabled(monkeypatch):
    monkeypatch.delenv("IMPERSONATION", raising=False)
    with pytest.raises(HTTPException) as e:
        imp._guard()
    assert e.value.status_code == 404
    monkeypatch.setenv("IMPERSONATION", "1")
    imp._guard()  # no raise


@pytest.mark.asyncio
async def test_targets_404_when_disabled(monkeypatch):
    monkeypatch.delenv("IMPERSONATION", raising=False)
    with pytest.raises(HTTPException) as e:
        await imp.impersonation_targets(admin=_FakeAdmin())
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_targets_lists_logins(monkeypatch):
    monkeypatch.setenv("IMPERSONATION", "1")
    monkeypatch.setattr(
        "app.api.customer_auth._read",
        lambda: [
            {"client_id": "c1", "email": "a@x.com"},
            {"client_id": "c1", "email": "a@x.com"},  # dupe -> collapsed
            {"client_id": "c2", "email": "b@x.com"},
        ],
    )
    monkeypatch.setattr(imp, "_biz_name", lambda cid: {"c1": "Alpha", "c2": "Beta"}.get(cid, ""))
    res = await imp.impersonation_targets(admin=_FakeAdmin())
    assert res["count"] == 2
    cids = {t["client_id"] for t in res["targets"]}
    assert cids == {"c1", "c2"}


@pytest.mark.asyncio
async def test_start_mints_token_and_audits(monkeypatch):
    monkeypatch.setenv("IMPERSONATION", "1")
    monkeypatch.setattr(imp, "_client_email", lambda cid: "client@x.com")
    monkeypatch.setattr(imp, "_biz_name", lambda cid: "Acme Co")

    audited = {}

    async def _fake_audit(db, **kw):
        audited.update(kw)

    monkeypatch.setattr(imp, "log_audit", _fake_audit)

    body = imp.ImpersonateIn(client_id="c42", reason="debug dashboard")
    out = await imp.impersonation_start(body, _FakeReq(), admin=_FakeAdmin(), db=object())

    assert out["impersonation"] is True
    assert out["client_id"] == "c42"
    assert out["business_name"] == "Acme Co"
    # audit captured the action with warning severity + admin + target
    assert audited["action"] == "impersonate.start"
    assert audited["resource_id"] == "c42"
    assert audited["severity"] == "warning"

    # token is a usable customer-role impersonation token
    from app.api.admin import decode_token

    p = decode_token(out["access_token"])
    assert p["role"] == "customer" and p["imp"] is True


@pytest.mark.asyncio
async def test_start_404_for_unknown_client(monkeypatch):
    monkeypatch.setenv("IMPERSONATION", "1")
    monkeypatch.setattr(imp, "_client_email", lambda cid: "")
    monkeypatch.setattr(imp, "_biz_name", lambda cid: "")
    with pytest.raises(HTTPException) as e:
        await imp.impersonation_start(
            imp.ImpersonateIn(client_id="ghost"), _FakeReq(), admin=_FakeAdmin(), db=object()
        )
    assert e.value.status_code == 404
