"""N.1 C1 cross-tenant IDOR regression guard.

The audit's #1 launch-blocker: every billing mutation used to trust ?client_id=
from the query string with zero auth. Unauthenticated callers could cancel /
upgrade / credit / read any tenant's account.

These tests pin the FIXED behaviour so a future refactor that drops the auth
dep cannot silently regress. They cover the contract — not the underlying
plan logic — so they pass on a fresh checkout with no live DB.

Matrix asserted:
  no token             -> 401 (unauthenticated)
  customer token       -> uses token.sub, ignores ?client_id= (no IDOR)
  admin/super_admin    -> requires explicit ?client_id= (acting on behalf)
  wrong token role     -> 403 / 401
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.api.billing import _authed_admin_client_id, _authed_client_id


class _Creds:
    """Mimic HTTPAuthorizationCredentials (avoid importing the FastAPI class
    just to construct it in pure-Python tests)."""

    def __init__(self, token: str) -> None:
        self.credentials = token


# --------------------------------------------------------------------------- #
# _authed_client_id — customer + admin paths
# --------------------------------------------------------------------------- #
async def test_no_token_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _authed_client_id(client_id=None, creds=None)
    assert exc.value.status_code == 401


async def test_customer_token_resolves_to_token_sub(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Even when the caller passes ?client_id=victim, the dep MUST return the
    customer's own sub — this is the IDOR fix."""
    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "customer", "sub": "actual_owner"},
    )
    cid = await _authed_client_id(client_id="victim", creds=_Creds("x"))
    assert cid == "actual_owner"


async def test_customer_token_missing_sub_is_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "customer", "sub": ""},
    )
    with pytest.raises(HTTPException) as exc:
        await _authed_client_id(client_id="any", creds=_Creds("x"))
    assert exc.value.status_code == 401


async def test_admin_token_requires_explicit_client_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "admin", "sub": "admin1"},
    )
    # No ?client_id= -> 400 (admin must say who they're acting on behalf of)
    with pytest.raises(HTTPException) as exc:
        await _authed_client_id(client_id=None, creds=_Creds("x"))
    assert exc.value.status_code == 400


async def test_admin_token_with_client_id_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "super_admin", "sub": "boss"},
    )
    cid = await _authed_client_id(client_id="target_client", creds=_Creds("x"))
    assert cid == "target_client"


async def test_unknown_role_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    """A valid JWT but a role we don't authorize for billing (e.g. an agent
    role) must NOT silently pass."""
    from fastapi import HTTPException

    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "agent", "sub": "x"},
    )
    with pytest.raises(HTTPException) as exc:
        await _authed_client_id(client_id="x", creds=_Creds("x"))
    assert exc.value.status_code == 403


# --------------------------------------------------------------------------- #
# _authed_admin_client_id — admin-only mutations (e.g. free plan swap)
# --------------------------------------------------------------------------- #
async def test_admin_dep_rejects_customer_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A customer must NOT self-upgrade for free via the admin direct-plan-swap
    endpoint — they go through /checkout which actually charges."""
    from fastapi import HTTPException

    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "customer", "sub": "victim_or_owner"},
    )
    with pytest.raises(HTTPException) as exc:
        await _authed_admin_client_id(client_id="any", creds=_Creds("x"))
    assert exc.value.status_code == 403


async def test_admin_dep_accepts_admin_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.api import billing

    monkeypatch.setattr(
        billing,
        "_decode_or_401",
        lambda _creds: {"role": "admin", "sub": "boss"},
    )
    cid = await _authed_admin_client_id(client_id="target", creds=_Creds("x"))
    assert cid == "target"


# --------------------------------------------------------------------------- #
# HTTP-level regression: routes must be auth-gated
# --------------------------------------------------------------------------- #
def test_billing_subscription_route_is_auth_gated() -> None:
    """Live route-level proof — GET /api/billing/subscription without a token
    MUST NOT be 200. This is the audit's exact attack: anyone with a guessed
    client_id used to read anyone's subscription."""
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/billing/subscription?client_id=somebodys_id")
    assert r.status_code != 200
    assert r.status_code in {401, 403}, (
        f"REGRESSION: billing/subscription returned {r.status_code} without "
        f"auth — C1 IDOR is back. Inspect _authed_client_id wiring."
    )


def test_billing_balance_route_is_auth_gated() -> None:
    """Same property on a different mutation — proves the auth dep is wired
    consistently across the router, not just on one endpoint."""
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/billing/balance?client_id=somebodys_id")
    assert r.status_code != 200
    assert r.status_code in {
        401,
        403,
    }, f"REGRESSION: billing/balance returned {r.status_code} without auth"
