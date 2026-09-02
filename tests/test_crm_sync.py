"""Native CRM sync (Zoho/HubSpot) — gated/inert/never-raise contract tests."""

import asyncio

import pytest


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for k in (
        "CRM_SYNC",
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "ZOHO_REFRESH_TOKEN",
        "HUBSPOT_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    # settings cached ho sakta hai — direct blank override
    try:
        from app.config import settings

        monkeypatch.setattr(settings, "zoho_client_id", "", raising=False)
        monkeypatch.setattr(settings, "zoho_client_secret", "", raising=False)
        monkeypatch.setattr(settings, "zoho_refresh_token", "", raising=False)
        monkeypatch.setattr(settings, "hubspot_api_key", "", raising=False)
    except Exception:
        pass
    yield


def test_zoho_inert_without_creds():
    from app.integrations.zoho_crm import ZohoCRM

    z = ZohoCRM()
    assert z.enabled is False
    assert asyncio.run(z.upsert_lead({"business_name": "X", "phone": "9999999999"})) is None
    assert asyncio.run(z.add_note("123", "t", "c")) is False
    res = asyncio.run(z.test_connection())
    assert res["ok"] is False


def test_zoho_india_dc_default():
    from app.integrations.zoho_crm import ZohoCRM

    z = ZohoCRM(client_id="a", client_secret="b", refresh_token="c")
    assert z.enabled is True
    assert "zoho.in" in z.accounts_base
    assert "zohoapis.in" in z.api_base
    # Unreachable/invalid creds -> token '' -> upsert None, no raise
    assert asyncio.run(z.upsert_lead({"business_name": "X"})) is None


def test_hubspot_per_client_token():
    from app.integrations.hubspot import HubSpotIntegration

    hs = HubSpotIntegration(api_key="test-token-123")  # nosecret
    assert hs.headers is not None
    assert "test-token-123" in hs.headers["Authorization"]
    hs2 = HubSpotIntegration()
    assert hs2.headers is None  # global key blank in tests


def test_crm_sync_no_config_skips():
    from app.platform import crm_sync

    assert crm_sync.auto_enabled() is False
    out = asyncio.run(crm_sync.push_lead({"business_name": "Test", "phone": "9876543210"}))
    assert out["ok"] is False
    assert "skipped" in out
    st = crm_sync.status()
    assert st["provider"] == "none"
    assert st["auto_sync"] is False


def test_crm_sync_auto_flag(monkeypatch):
    from app.platform import crm_sync

    monkeypatch.setenv("CRM_SYNC", "1")
    assert crm_sync.auto_enabled() is True


def test_save_client_config_validates_provider():
    from app.platform import crm_sync

    out = crm_sync.save_client_config("whatever", {"provider": "salesforce"})
    assert out["ok"] is False


def test_lead_delivery_zoho_channel_skips():
    from app.integrations.lead_delivery import LeadDelivery

    d = LeadDelivery()
    res = asyncio.run(
        d.deliver_lead({"business": "T", "phone": "9876543210"}, {"channels": ["zoho"]})
    )
    assert "zoho" in res.skipped
    assert res.failed == {}


def test_flag_in_registry():
    from app.api.growth import AUTOMATION_FLAGS

    assert "CRM_SYNC" in AUTOMATION_FLAGS
