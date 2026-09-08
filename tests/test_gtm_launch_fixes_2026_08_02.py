"""GTM launch fixes (2026-08-02 Cursor session) — proposal truth, login alias,
inquiry→autopilot feed, admin prospect add, guest UPI route contract.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient


def test_proposal_public_pricing_no_growth_leak():
    from app.marketing import proposal

    starter = asyncio.run(proposal.generate_proposal("X", "salon", "Pune", "starter"))
    assert starter["price_inr"] == 1999
    assert starter["plan_key"] == "starter"
    growth = asyncio.run(proposal.generate_proposal("X", "salon", "Pune", "growth"))
    assert growth["price_inr"] == 1999
    assert "2999" not in growth["proposal"]
    advanced = asyncio.run(proposal.generate_proposal("X", "salon", "Pune", "advanced"))
    assert advanced["price_inr"] == 5999


def test_login_alias_redirects_to_app_login():
    from app.main import app

    c = TestClient(app)
    r = c.get("/login", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers.get("location") == "/app/login"


def test_inquiry_ingests_platform_lead_to_autopilot(tmp_path, monkeypatch):
    from app.platform import inquiry_hooks
    from app.platform.sales_autopilot import store as ap_store

    monkeypatch.setattr(ap_store, "_DIR", str(tmp_path))
    monkeypatch.setattr(ap_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(ap_store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))

    out = inquiry_hooks.maybe_ingest_sales_autopilot(
        {
            "id": "inq-test-1",
            "business_name": "Glow Salon",
            "name": "Riya",
            "phone": "9876543210",
            "email": "info@glowsalon.test",
            "city": "Pune",
            "niche": "beauty_makeover",
            "client_id": None,
        }
    )
    assert out and out.get("id") == "inq-test-1"
    assert out.get("consent_basis") == "website_inquiry_form"
    assert out.get("status") == ap_store.STATUS_NEW
    assert out.get("email") == "info@glowsalon.test"


def test_inquiry_skips_client_owned_leads(tmp_path, monkeypatch):
    from app.platform import inquiry_hooks
    from app.platform.sales_autopilot import store as ap_store

    monkeypatch.setattr(ap_store, "_DIR", str(tmp_path))
    monkeypatch.setattr(ap_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    assert (
        inquiry_hooks.maybe_ingest_sales_autopilot(
            {
                "id": "inq-client",
                "phone": "9876543210",
                "email": "a@b.com",
                "client_id": "jiya-makeover",
            }
        )
        is None
    )


@pytest.mark.asyncio
async def test_admin_add_prospect_requires_consent(tmp_path, monkeypatch):
    from app.api import sales_autopilot_admin as admin
    from app.platform.sales_autopilot import store as ap_store

    monkeypatch.setattr(ap_store, "_DIR", str(tmp_path))
    monkeypatch.setattr(ap_store, "_PROSPECTS_FILE", str(tmp_path / "prospects.json"))
    monkeypatch.setattr(ap_store, "_ATTEMPTS_FILE", str(tmp_path / "attempts.jsonl"))

    missing = await admin.add_prospect({"name": "X", "email": "x@y.com"}, _user={"role": "admin"})
    assert missing["ok"] is False and missing["error"] == "consent_basis_required"

    ok = await admin.add_prospect(
        {
            "name": "New Spa",
            "email": "hello@newspa.test",
            "phone": "9123456789",
            "city": "Thane",
            "niche": "beauty_makeover",
            "consent_basis": "owner_manual_confirmed",
        },
        _user={"role": "admin"},
    )
    assert ok["ok"] is True
    assert ok["prospect"]["consent_basis"] == "owner_manual_confirmed"
    assert ok["prospect"]["manual_owner_confirmed"] is False


def test_upi_submit_guest_optional_auth(monkeypatch):
    """Route must accept guests (optional_customer → '') — regression for homepage pay."""
    from app.api import upi_payments as route
    from app.platform import upi_payments as store_mod

    seen: dict = {}

    def _fake_submit(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "status": "pending", "id": "upi_guest_1"}

    monkeypatch.setattr(store_mod, "submit_payment", _fake_submit)
    body = route.UpiSubmitIn(
        plan="starter",
        upi_ref="GUESTREF1",
        amount=0,
        payer_name="A",
        payer_contact="9999999999",
    )
    out = asyncio.run(route.upi_submit(body, client_id=""))
    assert out["ok"] is True
    assert out["status"] == "pending"
    assert seen.get("client_id") == ""
