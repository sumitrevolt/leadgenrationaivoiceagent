"""Guest /pay submit adopts the offer's admin-bound client (conversion fast-path).

Hosted ``/pay/{order_ref}`` buyers carry no JWT, so ``submit_payment`` used to
record every such payment as an unbound guest (``needs_client_bind=True``) and
a single owner approve could never activate it — bind + re-approve were
mandatory. When the JWT client is absent, the record now adopts the
``client_id`` the ADMIN bound to the issued offer (server-resolved via
``resolve_payable``, never ``body.client_id``), so one approve activates.

Security invariants (all asserted below):
- a logged-in client_id is never overridden by the offer's;
- payer input (``payer_contact`` etc.) can never choose the account — only the
  admin-issued offer binds it;
- an offer without a client keeps the exact guest path (fail-closed);
- money semantics unchanged: record stays ``pending``, activation only via the
  owner approve / allowlisted auto path, never at submit.
"""

from __future__ import annotations

import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import offers
    from app.platform import upi_payments

    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "upi.json"))
    monkeypatch.setattr(offers, "_store", lambda: str(tmp_path / "offers.jsonl"))
    monkeypatch.setattr(upi_payments, "_notify_admin", lambda *a, **k: None)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE_CLIENTS", raising=False)
    return upi_payments, offers


def _issue(offers, deal="deal1", plan="starter", client_id="cli1", **kw):
    o = offers.issue_offer(deal, plan, client_id=client_id, **kw)
    assert o is not None
    return o


def test_guest_submit_adopts_offer_client(env):
    """Core fast-path: no JWT + offer has admin-bound client → bound record."""
    upi, offers = env
    o = _issue(offers)

    out = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert out["ok"] is True
    assert out["status"] == "pending"  # money still NOT collected
    assert out["client_id"] == "cli1"
    assert out["needs_client_bind"] is False
    assert out["client_adopted_from_order"] is True


def test_offer_without_client_keeps_guest_path(env):
    """Fail-closed: offer carries no client → exact old guest behaviour."""
    upi, offers = env
    o = _issue(offers, client_id="")

    out = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert out["ok"] is True
    assert out["client_id"] == ""
    assert out["needs_client_bind"] is True
    assert "client_adopted_from_order" not in out


def test_logged_in_client_is_never_overridden(env):
    """JWT identity wins — the offer must not re-point a logged-in payer."""
    upi, offers = env
    o = _issue(offers)

    out = upi.submit_payment("cli9", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert out["ok"] is True
    assert out["client_id"] == "cli9"
    assert "client_adopted_from_order" not in out


def test_payer_input_cannot_choose_the_account(env):
    """Spoof check: attacker's own contact/name never becomes the binding."""
    upi, offers = env
    o = _issue(offers)

    out = upi.submit_payment(
        "",
        "starter",
        "TXN1",
        amount=1999,
        payer_name="Mallory",
        payer_contact="attacker-client-id",
        order_ref=o["order_ref"],
    )

    assert out["ok"] is True
    assert out["client_id"] == "cli1"  # offer's, not the payer's
    assert out["payer_contact"] == "attacker-client-id"  # contact still recorded


def test_adopted_record_replays_as_duplicate_not_a_second_row(env):
    """Double-click with the same ref under an adopted client dedupes."""
    upi, offers = env
    o = _issue(offers)

    first = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    second = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])

    assert first["ok"] is True and second["ok"] is True
    assert second.get("duplicate") is True
    assert second["id"] == first["id"]
    assert len(upi.list_payments("pending")) == 1


def test_no_order_ref_behaves_exactly_as_before(env):
    """Omitting order_ref preserves the pre-existing guest path byte-for-byte."""
    upi, _ = env

    out = upi.submit_payment("", "starter", "TXN1", amount=1999)

    assert out["ok"] is True
    assert out["client_id"] == ""
    assert out["needs_client_bind"] is True
    assert "client_adopted_from_order" not in out
    assert "order_ref" not in out


def test_single_approve_activates_adopted_record_without_bind(env, monkeypatch):
    """Money assertion: adopted guest → ONE owner approve activates, no bind step."""
    from app.billing import usage
    from app.platform import upi_payments as upi_mod

    upi, offers = env
    o = _issue(offers)

    calls: list[tuple] = []

    def fake_activate(cid, plan, **kw):
        calls.append((cid, plan))
        return True

    monkeypatch.setattr(usage, "activate_plan", fake_activate)
    monkeypatch.setattr(usage, "reset_usage_period", lambda cid, **kw: True)
    monkeypatch.setattr(upi_mod, "_trigger_onboarding", lambda cid="": None)
    monkeypatch.setattr(upi_mod, "_mark_deal_won", lambda phone: None)
    monkeypatch.setattr(upi_mod, "_fire_gst_invoice", lambda *a, **k: None)

    sub = upi.submit_payment("", "starter", "TXN1", amount=1999, order_ref=o["order_ref"])
    assert sub["ok"] is True

    decided = upi.decide(sub["id"], True, decided_by="admin")

    assert decided.get("status") == "approved"
    assert decided.get("activated") is True
    assert "activation_blocked" not in decided
    assert "approved_but_unbound" not in (decided.get("warning") or "")
    assert calls == [("cli1", "starter")]  # exactly once, no double activation
    assert upi.list_actionable() == []
