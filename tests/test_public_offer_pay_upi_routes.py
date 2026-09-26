"""Route-level tests — public offer → pay page → UPI submission (isolated stores).

Slice 2026-09-24 (OpenCode): HTTP-level proof for the three customer-facing money
routes that previously had only string-presence assertions:

  * ``GET  /api/public/offers/{order_ref}`` — valid / unknown / expired, fail-closed
  * ``GET  /pay/{order_ref}``               — hosted pay page + order-ref handoff JS
  * ``POST /api/upi/submit``                — valid pending, duplicate idempotent,
                                              unknown/expired/plan-mismatch refused

Money-truth invariants this suite locks (AGENTS §3 billing truth):

  * A customer submission NEVER marks money collected and NEVER activates a plan
    by itself: the offer stays ``issued``, the record stays ``pending``, and the
    activation helper is never invoked — even with ``UPI_AUTO_ACTIVATE=1`` for a
    guest submission (guests carry no ``client_id``, which the allowlist requires).
  * The owner's bank-credit confirmation stays the single activation gate:
    ``/api/upi/pending/{id}/approve`` refuses without admin auth.

Isolation: both money stores are monkeypatched to ``tmp_path`` — the real
``data/offers.jsonl`` / ``data/upi_payments.json`` are never read or written.
No payment flag, admin auth, price floor or default-off auto-activation setting
is changed by any test here; they are exercised exactly as shipped.

Rate-limit budget note: ``/api/upi/submit`` allows 10 req/min per client IP and
all TestClient requests share one IP, so this file keeps total submits <= 8.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _issue(deal_id: str, package_code: str = "starter") -> dict:
    """Issue a real (but store-isolated) catalogue offer for the test deal."""
    from app.marketing import offers

    off = offers.issue_offer(deal_id, package_code)
    assert off, f"test offer must issue for {deal_id!r}"
    return off


def _write_expired_offer(store_path) -> str:
    """Craft an already-expired issued offer directly in the isolated store.

    ``issue_offer`` clamps TTL to >= 1 day, so expiry is written here instead of
    waiting on wall-clock time.
    """
    ref = "LG-" + "e" * 32
    now = datetime.now(timezone.utc)
    row = {
        "order_ref": ref,
        "deal_id": "deal-expired-1",
        "package_code": "starter",
        "quoted_amount": 1999,
        "currency": "INR",
        "offer_version": 1,
        "status": "issued",
        "created_at": (now - timedelta(days=40)).isoformat(),
        "expires_at": (now - timedelta(days=10)).isoformat(),
    }
    store_path.write_text(json.dumps(row) + "\n", encoding="utf-8")
    return ref


def _submit(
    client,
    *,
    upi_ref: str,
    order_ref: str,
    plan: str = "starter",
    amount: float = 1999,
):
    """Guest self-serve submit (no auth header) — the public pay-page path."""
    return client.post(
        "/api/upi/submit",
        json={
            "plan": plan,
            "upi_ref": upi_ref,
            "amount": amount,
            "payer_name": "Route Test",
            "payer_contact": "9876543210",
            "order_ref": order_ref,
        },
    )


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def stores(monkeypatch, tmp_path):
    """Point BOTH money stores at tmp_path and silence admin ntfy pushes."""
    from app.marketing import offers
    from app.platform import ops_alerts, upi_payments

    offers_file = tmp_path / "offers.jsonl"
    upi_file = tmp_path / "upi_payments.json"
    monkeypatch.setattr(offers, "_OFFERS", str(offers_file))
    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(upi_file))
    monkeypatch.setattr(ops_alerts, "_ntfy", lambda *args, **kwargs: None)
    return offers_file


@pytest.fixture
def activation_canary(monkeypatch):
    """Record any plan-activation attempt; money-truth tests assert it stays empty."""
    calls: list[tuple] = []
    from app.billing import usage

    def _record(*args, **kwargs):
        calls.append((args, kwargs))
        return True

    monkeypatch.setattr(usage, "activate_plan", _record)
    return calls


# --------------------------------------------------------------------------- #
# GET /api/public/offers/{order_ref}
# --------------------------------------------------------------------------- #
class TestPublicOffer:
    def test_valid_offer_resolves_pay_kit(self, client, stores):
        """A live issued offer hands the page its ref, issued price and pay-kit."""
        off = _issue("deal-offer-ok")
        res = client.get(f"/api/public/offers/{off['order_ref']}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["order_ref"] == off["order_ref"]
        # Amount handed to the page is the ISSUED (frozen) quote, not a live lookup.
        assert data["amount_inr"] == off["quoted_amount"]
        assert data["status"] == "issued"
        # UPI pay-kit payload is always present (armed depends on VPA config).
        assert "armed" in data

    def test_unknown_ref_fails_closed_without_leaking(self, client, stores):
        """Guessable/unknown refs resolve fail-closed — no amount, no pay-kit."""
        res = client.get("/api/public/offers/LG-" + "0" * 32)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert data["reason"] == "unknown"
        assert "amount_inr" not in data
        assert "upi_link" not in data

    def test_expired_ref_reports_expired(self, client, stores):
        """An issued-but-expired order stops being payable with an explicit reason."""
        ref = _write_expired_offer(stores)
        res = client.get(f"/api/public/offers/{ref}")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert data["reason"] == "expired"
        assert "amount_inr" not in data


# --------------------------------------------------------------------------- #
# GET /pay/{order_ref}
# --------------------------------------------------------------------------- #
class TestPayPage:
    @pytest.mark.parametrize(
        "order_ref",
        ["LG-" + "a" * 32, "totally-bogus-ref"],
        ids=["lg-shaped-ref", "bogus-ref"],
    )
    def test_pay_page_serves_order_ref_handoff(self, client, order_ref):
        """Hosted pay page always serves 200 + the full order-ref handoff.

        Unknown refs are handled client-side: the page resolves the ref against
        ``/api/public/offers/`` and fail-closes in the UI — the route itself is a
        static FileResponse and reads no store (hence no ``stores`` fixture).
        """
        res = client.get(f"/pay/{order_ref}")
        assert res.status_code == 200
        assert "text/html" in res.headers["content-type"]
        html = res.text
        # ref extracted from the URL path …
        assert "location.pathname.split('/').pop()" in html
        # … resolved against the public offer API …
        assert "/api/public/offers/" in html
        # … and submitted back bound to that ref, with the canonical ref synced
        # into the address bar.
        assert "history.replaceState" in html
        assert "/api/upi/submit" in html
        assert "order_ref:ref" in html


# --------------------------------------------------------------------------- #
# POST /api/upi/submit
# --------------------------------------------------------------------------- #
class TestUpiSubmit:
    def test_valid_submit_is_pending_not_collected_not_activated(
        self, client, stores, activation_canary
    ):
        """A fresh submission is ONLY a pending claim — no money, no activation."""
        off = _issue("deal-submit-ok")
        res = _submit(
            client,
            upi_ref="TXNAUTO0001",
            order_ref=off["order_ref"],
            amount=float(off["quoted_amount"]),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["status"] == "pending"
        assert "duplicate" not in data

        from app.marketing import offers
        from app.platform import upi_payments

        rows = upi_payments.list_payments()
        assert len(rows) == 1
        row = rows[0]
        assert row["status"] == "pending"
        assert row["auto_activated"] is False
        assert row["decided_at"] is None
        # Server-resolved reconciliation anchors come from the ISSUED offer.
        assert row["order_ref"] == off["order_ref"]
        assert row["expected_amount"] == off["quoted_amount"]

        # Money NOT collected: the offer is still payable (not flipped to paid).
        assert offers.get_offer(off["order_ref"])["status"] == "issued"
        # No plan activation happened without the owner's bank-credit approval.
        assert activation_canary == []

    def test_duplicate_submission_is_idempotent(self, client, stores, activation_canary):
        """Same txn ref + plan again → same record replayed, never a second row."""
        off = _issue("deal-submit-dup")
        first = _submit(client, upi_ref="TXNDUP0001", order_ref=off["order_ref"]).json()
        second = _submit(client, upi_ref="TXNDUP0001", order_ref=off["order_ref"]).json()

        assert first["ok"] is True
        assert second["ok"] is True
        assert second.get("duplicate") is True
        assert second["id"] == first["id"]

        from app.platform import upi_payments

        assert len(upi_payments.list_payments()) == 1
        assert activation_canary == []

    def test_unknown_order_ref_refused_and_nothing_recorded(
        self, client, stores, activation_canary
    ):
        """Unverifiable order_ref on a NEW submission → refused, zero rows written."""
        res = _submit(client, upi_ref="TXNUNK0001", order_ref="LG-" + "f" * 32)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert "Order reference not payable (unknown)" in data["error"]

        from app.platform import upi_payments

        assert upi_payments.list_payments() == []
        assert activation_canary == []

    def test_expired_order_ref_refused_on_submit(self, client, stores, activation_canary):
        """An expired offer cannot be paid against — fail-closed with the reason."""
        ref = _write_expired_offer(stores)
        res = _submit(client, upi_ref="TXNEXP0001", order_ref=ref)
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert "Order reference not payable (expired)" in data["error"]

        from app.platform import upi_payments

        assert upi_payments.list_payments() == []
        assert activation_canary == []

    def test_plan_mismatch_refused(self, client, stores, activation_canary):
        """The issued order owns the commercial truth — a disagreeing plan cannot
        ride along on its reference."""
        off = _issue("deal-submit-mismatch")
        res = _submit(
            client,
            upi_ref="TXNMIS0001",
            order_ref=off["order_ref"],
            plan="advanced",
            amount=5999,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is False
        assert "does not match the submitted plan" in data["error"]

        from app.platform import upi_payments

        assert upi_payments.list_payments() == []
        assert activation_canary == []

    def test_guest_submit_stays_pending_even_with_auto_flag_on(
        self, client, stores, activation_canary, monkeypatch
    ):
        """Even UPI_AUTO_ACTIVATE=1 + allowlist '*' cannot activate a GUEST
        submission (no client_id) — owner bank-credit Approve remains the gate."""
        monkeypatch.setenv("UPI_AUTO_ACTIVATE", "1")
        monkeypatch.setenv("UPI_AUTO_ACTIVATE_CLIENTS", "*")

        off = _issue("deal-submit-flagon")
        res = _submit(
            client,
            upi_ref="TXNGST0001",
            order_ref=off["order_ref"],
            amount=float(off["quoted_amount"]),
        )
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert data["status"] == "pending"
        assert activation_canary == []

        from app.marketing import offers

        # Money still not marked collected — offer remains payable.
        assert offers.get_offer(off["order_ref"])["status"] == "issued"

    def test_owner_approve_endpoint_requires_admin(self, client, stores, activation_canary):
        """Manual UPI approval stays admin-gated — the bank-credit confirm door
        cannot be walked through without admin auth.

        The suite-wide conftest mocks ``require_admin``/``get_current_user``
        (tests/conftest.py, session baseline) so most admin tests never exercise
        auth. This test temporarily REMOVES those two overrides to run the REAL
        production gate, then restores them (conftest's autouse
        ``restore_dependency_overrides`` is the backstop)."""
        from app.api.auth_deps import get_current_user, require_admin
        from app.main import app

        off = _issue("deal-submit-approve")
        _submit(client, upi_ref="TXNAPR0001", order_ref=off["order_ref"])

        saved = {
            dep: app.dependency_overrides.pop(dep, None)
            for dep in (require_admin, get_current_user)
        }
        try:
            res = client.post("/api/upi/pending/upi_does_not_matter/approve")
            assert res.status_code in (401, 403), res.status_code
        finally:
            app.dependency_overrides.update({k: v for k, v in saved.items() if v is not None})

        from app.marketing import offers
        from app.platform import upi_payments

        # Unauthenticated attempt changed nothing: still pending, offer still issued.
        rows = upi_payments.list_payments()
        assert len(rows) == 1 and rows[0]["status"] == "pending"
        assert offers.get_offer(off["order_ref"])["status"] == "issued"
        assert activation_canary == []
