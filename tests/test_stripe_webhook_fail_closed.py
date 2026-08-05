"""The retired Stripe webhook must never accept an unverified payment event.

Owner decision 2026-08-05: **manual UPI is the canonical payment method** and a
provider-backed rail is out of scope (issue #243, closed `not_planned`). Stripe
was removed 2026-07-10 and Razorpay 2026-06-18, so `PROVIDER_VERIFIED` is
unreachable BY DESIGN, not by accident.

`POST /api/billing/webhooks/stripe` still exists as a compatibility stub. The
danger is not that it is dead — it is that it *looks* alive: the handler carries
a "signature-verified" docstring and is followed by a full subscription-
activation body (`_activate_subscription_row`, minute-ledger provisioning) that
is currently unreachable only because an unconditional `raise` sits above it.

If that raise were ever removed while restoring the endpoint, the code below it
would run against a completely unverified payload — anyone who can POST to the
URL could activate a paid subscription. This suite is the lock on that: the
endpoint must refuse, and it must refuse BEFORE parsing or acting on any event.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app, raise_server_exceptions=False)


FORGED_PAID_EVENT = {
    "id": "evt_forged_001",
    "type": "checkout.session.completed",
    "data": {
        "object": {
            "id": "cs_forged",
            "mode": "subscription",
            "subscription": "sub_forged",
            "customer": "cus_forged",
            "metadata": {"client_id": "victim-tenant", "plan_id": "advanced"},
        }
    },
}


def test_forged_paid_event_is_refused(client):
    """A completely unsigned 'payment succeeded' must never be accepted."""
    r = client.post("/api/billing/webhooks/stripe", json=FORGED_PAID_EVENT)

    assert r.status_code in (400, 401, 403, 404, 503), r.status_code
    body = r.text.lower()
    assert "received" not in body
    assert "true" not in body or r.status_code != 200


def test_forged_event_with_a_fake_signature_header_is_still_refused(client):
    """Supplying a Stripe-Signature header must not buy any trust."""
    r = client.post(
        "/api/billing/webhooks/stripe",
        json=FORGED_PAID_EVENT,
        headers={"Stripe-Signature": "t=1,v1=" + "0" * 64},
    )

    assert r.status_code in (400, 401, 403, 404, 503), r.status_code


def test_refusal_happens_before_any_subscription_side_effect(client, monkeypatch):
    """The refusal must precede activation, not merely fail afterwards.

    Guards the real hazard: the unreachable activation body below the raise.
    If a future edit restores the endpoint without restoring verification, this
    fails because activation would have been reached.
    """
    called: list[str] = []

    try:
        from app.api import billing as billing_mod
    except Exception:  # pragma: no cover
        pytest.skip("billing module unavailable")

    if hasattr(billing_mod, "_activate_subscription_row"):

        async def spy(*a, **k):
            called.append("activated")
            return None

        monkeypatch.setattr(billing_mod, "_activate_subscription_row", spy)

    client.post(
        "/api/billing/webhooks/stripe",
        json=FORGED_PAID_EVENT,
        headers={"Stripe-Signature": "t=1,v1=" + "0" * 64},
    )

    assert called == [], "unverified event reached subscription activation"


def test_no_provider_verified_claim_anywhere_in_the_response(client):
    """Truthful vocabulary: manual UPI is owner_confirmed, never provider-verified."""
    r = client.post("/api/billing/webhooks/stripe", json=FORGED_PAID_EVENT)

    assert "provider_verified" not in r.text.lower()


def test_handler_source_contains_no_activation_capability():
    """Structural guard: the capability is GONE, not merely guarded.

    The behavioural tests above prove the endpoint refuses today. This proves it
    *cannot* be made to activate by deleting one line, which is what the previous
    shape allowed — 200 lines of activation sat below an unconditional `raise`.

    AST-based, so it inspects the real function body rather than grepping a file
    (docstring prose describing the removed hazard must not trip it).
    """
    import ast
    import inspect

    from app.api import billing as billing_mod

    src = inspect.getsource(billing_mod)
    tree = ast.parse(src)

    handler = None
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and "stripe_webhook" in node.name:
            handler = node
            break
    assert handler is not None, "retired stripe webhook handler not found"

    called = {
        n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
        for n in ast.walk(handler)
        if isinstance(n, ast.Call)
    }

    forbidden = {
        "_activate_subscription_row",
        "_provision_usage",
        "_find_subscription_by_gateway_id",
        "_emit_billing_customer_webhook",
        "commit",
    }
    leaked = called & forbidden
    assert not leaked, f"retired handler regained activation capability: {sorted(leaked)}"

    # And it must still refuse unconditionally.
    raises = [n for n in ast.walk(handler) if isinstance(n, ast.Raise)]
    assert raises, "retired handler no longer refuses"


def test_manual_upi_routes_are_unaffected():
    """Removing the Stripe body must not disturb the canonical payment rail.

    Asserts against the UPI router itself rather than `app.routes` — the router
    is mounted under `/api` by main, so its paths are not flattened into the
    top-level route list.
    """
    from app.api.upi_payments import router as upi_router

    paths = {getattr(r, "path", "") for r in upi_router.routes}

    assert "/upi/submit" in paths
    assert "/upi/pending" in paths
