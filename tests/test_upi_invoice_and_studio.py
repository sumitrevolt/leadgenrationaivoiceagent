"""UPI-invoice hook + customer-studio wrappers — audit-2026-07-05 delivery fixes.

Covers three gaps that stopped the platform delivering promised features to
per-client paying customers (jiya makeover / trending tattoos):

  1. UPI approve/auto-activate now fires the GST invoice hook (parity with the
     Stripe path in billing._provision_usage). Mocked on_payment_success — no DB.
  2. New customer studio wrappers:
       - POST /studio/upi-qr   → persists client's own VPA + returns QR pack
       - POST /studio/ai-image, /studio/complete-post (customer-scoped, IDOR-safe)
     and the quote-draft tool now drafts the CLIENT's OWN price-quote (no LeadGen
     self-pitch / hidden Growth ₹2,999 leak).

free_ai.chat is stubbed by conftest; the quote test additionally forces the
never-empty TEMPLATE path so the assertion is deterministic (business_name
present, "LeadGen"/"2,999" absent) regardless of the stub's canned reply.
"""

import os

from fastapi.testclient import TestClient

from app.api.admin import create_access_token
from app.main import app
from tests._api_helpers import iter_mounted_routes


# --------------------------------------------------------------------------- #
# Gap 1 — UPI activation fires the GST invoice hook (best-effort, never-raise)  #
# --------------------------------------------------------------------------- #
def test_upi_decide_fires_gst_invoice(tmp_path, monkeypatch):
    """Admin approve of a pending UPI payment → on_payment_success called once
    with the client_id + plan. _try_activate is forced True (no real billing DB);
    on_payment_success is an ASYNC mock so the sync asyncio.run() path awaits it."""
    from app.platform import upi_payments

    # Isolate the payment store (never touch real data/upi_payments.json).
    store = tmp_path / "upi_payments.json"
    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(store))

    # Force activation success (real usage.activate_plan needs a DB row).
    monkeypatch.setattr(upi_payments, "_try_activate", lambda *a, **k: True)
    # Silence the onboarding enqueue + deal-won side effects.
    monkeypatch.setattr(upi_payments, "_trigger_onboarding", lambda *a, **k: None)
    monkeypatch.setattr(upi_payments, "_mark_deal_won", lambda *a, **k: None)

    calls = []

    async def _fake_on_payment_success(
        client_id, plan, payment_ref="", gateway="", amount_inr=None
    ):
        calls.append({"client_id": client_id, "plan": plan, "gateway": gateway, "ref": payment_ref})
        return {"ok": True}

    from app.billing import gst_invoice

    monkeypatch.setattr(gst_invoice, "on_payment_success", _fake_on_payment_success)

    # Seed a pending record (UPI_AUTO_ACTIVATE unset → stays pending on submit).
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)
    sub = upi_payments.submit_payment(
        client_id="cust-abc", plan="starter", upi_ref="TXN123", amount=1999
    )
    assert sub["ok"] is True and sub["status"] == "pending"

    # Admin approves → invoice hook must fire (sync caller → asyncio.run path).
    rec = upi_payments.decide(sub["id"], approve=True, decided_by="tester")
    assert rec.get("status") == "approved" and rec.get("activated") is True

    assert len(calls) == 1, f"invoice hook fired {len(calls)}x (expected 1)"
    assert calls[0]["client_id"] == "cust-abc"
    assert calls[0]["plan"] == "starter"
    assert calls[0]["gateway"] == "upi"


def test_upi_invoice_hook_never_raises(tmp_path, monkeypatch):
    """A blowing-up on_payment_success must NOT break the activation/onboarding
    that already succeeded (best-effort contract)."""
    from app.billing import gst_invoice
    from app.platform import upi_payments

    monkeypatch.setattr(upi_payments, "_STORE", lambda: str(tmp_path / "upi.json"))
    monkeypatch.setattr(upi_payments, "_try_activate", lambda *a, **k: True)
    monkeypatch.setattr(upi_payments, "_trigger_onboarding", lambda *a, **k: None)
    monkeypatch.setattr(upi_payments, "_mark_deal_won", lambda *a, **k: None)

    async def _boom(*a, **k):
        raise RuntimeError("invoice store down")

    monkeypatch.setattr(gst_invoice, "on_payment_success", _boom)
    monkeypatch.delenv("UPI_AUTO_ACTIVATE", raising=False)

    sub = upi_payments.submit_payment(client_id="c2", plan="starter", upi_ref="T2", amount=1999)
    rec = upi_payments.decide(sub["id"], approve=True)
    # Activation still marked done — invoice failure swallowed.
    assert rec.get("activated") is True and rec.get("status") == "approved"


# --------------------------------------------------------------------------- #
# Shared client fixture for the studio wrapper tests                           #
# --------------------------------------------------------------------------- #
def _seed_client(
    monkeypatch, tmp_path, business_name="Glow Studio Nagpur", niche="beauty_makeover"
):
    """Create an isolated marketing client and return (client_id, auth_headers)."""
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    rec = clients_store.add_client(
        business_name=business_name,
        niche=niche,
        city="Nagpur",
        phone="8712928847",
        brand={"tagline": "Aapki khoobsurti, humari zimmedari"},
    )
    cid = rec["id"]
    tok = create_access_token(cid, "cust@test.com", "customer")
    return cid, {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


# --------------------------------------------------------------------------- #
# Gap 2a — quote-draft = customer's OWN quote, NOT LeadGen's self-pitch         #
# --------------------------------------------------------------------------- #
def test_studio_quote_is_client_scoped_not_leadgen(tmp_path, monkeypatch):
    cid, H = _seed_client(monkeypatch, tmp_path, business_name="Glow Studio Nagpur")

    # Force the never-empty template path (deterministic assertion).
    from app.voice_agent import free_ai

    async def _empty(*a, **k):
        return ("", "stub")

    monkeypatch.setattr(free_ai, "chat", _empty)

    c = TestClient(app)
    r = c.post(
        "/api/customer/studio/quote-draft",
        headers=H,
        json={
            "inquiry": "Bridal makeup ka rate kya hai?",
            "service": "Bridal makeup",
            "customer_name": "Riya",
        },
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    quote = (d.get("result") or {}).get("quote") or ""
    assert quote, "quote empty"
    # The CLIENT's business name must appear...
    assert "Glow Studio Nagpur" in quote
    # ...and NONE of LeadGen's own product/pricing leaks.
    low = quote.lower()
    assert "leadgen" not in low, f"LeadGen leaked into customer quote: {quote}"
    assert "2,999" not in quote and "2999" not in quote, f"hidden Growth price leaked: {quote}"


def test_studio_quote_fields_updated_in_tools_card(tmp_path, monkeypatch):
    """The _TOOLS card for quote-draft advertises the new customer-scoped fields."""
    from app.api.customer_marketing_studio import _TOOLS

    q = next(t for t in _TOOLS if t["key"] == "quote-draft")
    assert "inquiry" in q["fields"]
    assert "avg_deal_value" not in q["fields"]  # old LeadGen-ROI field gone


# --------------------------------------------------------------------------- #
# Gap 2b — /studio/upi-qr persists VPA + returns pack; ai-image/complete-post   #
# --------------------------------------------------------------------------- #
def test_studio_upi_qr_persists_vpa_and_returns_pack(tmp_path, monkeypatch):
    from app.marketing import clients_store

    cid, H = _seed_client(monkeypatch, tmp_path)

    c = TestClient(app)
    r = c.post("/api/customer/studio/upi-qr", headers=H, json={"vpa": "glowstudio@okhdfcbank"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True
    res = d.get("result") or {}
    assert res.get("vpa") == "glowstudio@okhdfcbank"
    assert res.get("upi_uri", "").startswith("upi://pay")
    assert res.get("qr_url")  # QR image URL present

    # VPA persisted to the client record (whitelisted field).
    rec = clients_store.get_client(cid) or {}
    assert rec.get("upi_vpa") == "glowstudio@okhdfcbank"

    # Second call WITHOUT vpa still works (reads persisted value).
    r2 = c.post("/api/customer/studio/upi-qr", headers=H, json={})
    assert r2.status_code == 200
    assert (r2.json().get("result") or {}).get("vpa") == "glowstudio@okhdfcbank"


def test_studio_upi_qr_no_vpa_graceful(tmp_path, monkeypatch):
    """No VPA set + none in record → actionable message, not a 5xx."""
    _cid, H = _seed_client(monkeypatch, tmp_path)
    c = TestClient(app)
    r = c.post("/api/customer/studio/upi-qr", headers=H, json={})
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is False and d.get("error")


def test_studio_new_routes_mounted_and_authed():
    paths = {r.path for r in iter_mounted_routes(app)}
    for p in [
        "/api/customer/studio/upi-qr",
        "/api/customer/studio/ai-image",
        "/api/customer/studio/complete-post",
    ]:
        assert p in paths, f"missing route {p}"
    c = TestClient(app)
    for p in [
        "/api/customer/studio/upi-qr",
        "/api/customer/studio/ai-image",
        "/api/customer/studio/complete-post",
    ]:
        assert c.post(p, json={}).status_code in (401, 403), f"{p} not auth-gated"


def test_studio_new_tools_in_card_list():
    from app.api.customer_marketing_studio import _TOOLS

    keys = {t["key"] for t in _TOOLS}
    assert {"upi-qr", "ai-image", "complete-post"} <= keys


def test_studio_ai_image_customer_scoped(tmp_path, monkeypatch):
    """AI image wrapper resolves business/niche from the client record (IDOR-safe)
    and returns a marketing_image payload. marketing_image is stubbed (no network)."""
    from app.marketing import ai_image

    cid, H = _seed_client(
        monkeypatch, tmp_path, business_name="Trend Tattoos", niche="tattoo_studio"
    )

    seen = {}

    async def _fake_marketing_image(
        business_name,
        niche="general",
        occasion="",
        offer="",
        style="vibrant professional",
        width=1024,
        height=1024,
    ):
        seen["business_name"] = business_name
        seen["niche"] = niche
        return {"url": "/api/marketing/ai-image-proxy?prompt=x", "prompt": "test prompt"}

    monkeypatch.setattr(ai_image, "marketing_image", _fake_marketing_image)

    c = TestClient(app)
    r = c.post("/api/customer/studio/ai-image", headers=H, json={"occasion": "Diwali"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d.get("ok") is True and (d.get("result") or {}).get("url")
    # business/niche came from the CLIENT record, not the request body.
    assert seen["business_name"] == "Trend Tattoos"
    assert seen["niche"] == "tattoo_studio"
