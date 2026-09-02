"""Tests: booking API mount + WhatsApp campaign (official-API, ban-safe default) + call_type."""

import asyncio

from tests._api_helpers import iter_mounted_routes


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def test_wa_link():
    from app.marketing import whatsapp_campaign as WC

    link = WC.wa_link("+91 98765 43210", "hi there")
    assert link.startswith("https://wa.me/919876543210?text=")


def test_send_one_defaults_to_link(monkeypatch):
    from app.marketing import whatsapp_campaign as WC

    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    r = _run(WC.send_one("9876543210", "hello"))
    assert r["sent"] is False and r["mode"] == "link" and r["link"]


def test_send_campaign_links_when_off(monkeypatch):
    from app.marketing import whatsapp_campaign as WC

    monkeypatch.delenv("WHATSAPP_AUTO_SEND", raising=False)
    res = _run(
        WC.send_campaign(
            [{"phone": "9000000001", "message": "a"}, {"phone": "9000000002", "message": "b"}]
        )
    )
    assert res["total"] == 2 and res["links"] == 2 and res["sent"] == 0 and res["auto"] is False


def test_call_request_call_type():
    from app.telephony.call_manager import CallRequest

    base = {
        "lead_id": "l",
        "phone_number": "p",
        "campaign_id": "c",
        "niche": "n",
        "client_name": "cn",
        "client_service": "cs",
        "script_name": "s",
        "lead_data": {},
    }
    assert CallRequest(**base).call_type == "promotional"
    assert CallRequest(**base, call_type="transactional").call_type == "transactional"


def test_booking_router_mounted():
    from app.main import app

    paths = {r.path for r in iter_mounted_routes(app)}
    assert "/api/booking/slots" in paths
    assert "/api/booking/book" in paths


def test_imports_clean():
    from app.api import booking  # noqa: F401
    from app.marketing import whatsapp_campaign  # noqa: F401

    assert True
