"""Unit tests for magic-link login (app/api/customer_auth.py).

No SMTP / no full app — endpoint coroutines direct call, deps monkeypatched.
Critical invariants: flag-gating, NO email-enumeration leak, single-use, expiry.
"""

import asyncio

import pytest
from fastapi import HTTPException

from app.api import customer_auth as ca


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    monkeypatch.delenv("MAGIC_LINK", raising=False)
    yield


def test_mint_decode_roundtrip(monkeypatch):
    monkeypatch.setenv("MAGIC_LINK", "1")
    tok = ca._mint_magic("c123", "User@Biz.com")
    payload = ca._decode_magic(tok)
    assert payload["sub"] == "c123"
    assert payload["type"] == "magic"
    assert payload["email"] == "user@biz.com"
    assert payload.get("jti")


def test_decode_rejects_non_magic(monkeypatch):
    monkeypatch.setenv("MAGIC_LINK", "1")
    # a normal customer access token is NOT a magic token
    from app.api.admin import create_access_token

    tok = create_access_token("c1", "a@b.com", "customer")
    with pytest.raises(HTTPException) as e:
        ca._decode_magic(tok)
    assert e.value.status_code == 401


@pytest.mark.asyncio
async def test_config_reflects_flag(monkeypatch):
    monkeypatch.delenv("MAGIC_LINK", raising=False)
    assert (await ca.magic_link_config())["enabled"] is False
    monkeypatch.setenv("MAGIC_LINK", "1")
    assert (await ca.magic_link_config())["enabled"] is True


@pytest.mark.asyncio
async def test_request_404_when_disabled(monkeypatch):
    monkeypatch.delenv("MAGIC_LINK", raising=False)
    with pytest.raises(HTTPException) as e:
        await ca.magic_link_request(ca.MagicRequestIn(email="x@y.com"))
    assert e.value.status_code == 404


@pytest.mark.asyncio
async def test_request_no_enumeration(monkeypatch):
    """Known vs unknown email => IDENTICAL response. Email sent only for known."""
    monkeypatch.setenv("MAGIC_LINK", "1")
    sent = []

    async def _send(email, link, biz):
        sent.append(email)
        return True

    async def _cd_ok(email):
        return True

    monkeypatch.setattr(ca, "_send_magic_email", _send)
    monkeypatch.setattr(ca, "_email_cooldown_ok", _cd_ok)
    monkeypatch.setattr(ca, "_biz_name", lambda cid: "Biz")

    # unknown email
    monkeypatch.setattr(ca, "_find", lambda e: None)
    r_unknown = await ca.magic_link_request(ca.MagicRequestIn(email="ghost@x.com"))

    # known email
    monkeypatch.setattr(ca, "_find", lambda e: {"client_id": "c9", "email": e})
    r_known = await ca.magic_link_request(ca.MagicRequestIn(email="real@x.com"))
    # send is now fire-and-forget (anti-timing-oracle) — let the detached task run.
    for _ in range(5):
        await asyncio.sleep(0)

    assert r_unknown == r_known  # zero signal leak
    assert r_unknown["ok"] is True
    assert sent == ["real@x.com"]  # email only to the real account


@pytest.mark.asyncio
async def test_verify_single_use(monkeypatch):
    monkeypatch.setenv("MAGIC_LINK", "1")
    monkeypatch.setattr(ca, "_biz_name", lambda cid: "Biz")
    tok = ca._mint_magic("c5", "z@x.com")

    # first use: jti consumable -> returns a customer access token
    async def _consume_true(jti):
        return True

    monkeypatch.setattr(ca, "_consume_jti", _consume_true)
    out = await ca.magic_link_verify(ca.MagicVerifyIn(token=tok))
    assert out["access_token"]
    assert out["client_id"] == "c5"

    # the minted token must be a real customer token
    from app.api.admin import decode_token

    p = decode_token(out["access_token"])
    assert p["role"] == "customer"
    assert p["sub"] == "c5"

    # second use: jti already consumed -> 401
    async def _consume_false(jti):
        return False

    monkeypatch.setattr(ca, "_consume_jti", _consume_false)
    with pytest.raises(HTTPException) as e:
        await ca.magic_link_verify(ca.MagicVerifyIn(token=tok))
    assert e.value.status_code == 401
