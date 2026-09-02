"""Admin dashboard + clients_store product lane (marketing / voice / combo)."""

from __future__ import annotations

from app.api.admin_dashboard import (
    Client,
    _client_mrr,
    _client_product,
    _collect_live_stats,
    _real_clients,
)
from app.marketing.clients_store import resolve_product


def test_resolve_product_from_field():
    assert resolve_product({"product": "voice", "plan": "starter"}) == "voice"
    assert resolve_product({"product": "combo"}) == "combo"
    assert resolve_product({"product": "both"}) == "combo"


def test_resolve_product_infers_voice_plan():
    assert resolve_product({"plan": "voice_b_monthly"}) == "voice"
    assert resolve_product({"plan": "combo_growth_monthly"}) == "combo"
    assert resolve_product({"plan": "growth"}) == "marketing"


def test_client_mrr_voice_band():
    c = {"status": "active", "product": "voice", "plan": "voice_a_monthly"}
    assert _client_mrr(c) == 4999


def test_client_mrr_combo():
    c = {"status": "active", "product": "combo", "plan": "combo_starter_monthly"}
    assert _client_mrr(c) == 4999


def test_client_model_has_product():
    row = Client(
        company="Test Co",
        niche="solar",
        product="voice",
        plan="Voice A Monthly",
        leads_delivered=0,
        status="active",
        mrr=4999,
    )
    assert row.product == "voice"


def test_collect_live_stats_product_breakdown_keys():
    stats = _collect_live_stats()
    assert "clients_by_product" in stats
    assert set(stats["clients_by_product"].keys()) >= {"marketing", "voice", "combo"}
    assert "mrr_by_product" in stats


def test_real_clients_rows_include_product(monkeypatch):
    monkeypatch.setattr(
        "app.marketing.clients_store.list_clients",
        lambda status=None, product=None: [
            {
                "id": "abc",
                "business_name": "Acme",
                "niche": "solar",
                "plan": "voice_a_monthly",
                "product": "voice",
                "status": "active",
            }
        ],
    )
    monkeypatch.setattr("app.api.admin_dashboard._inquiry_count_for_client", lambda _c: 0)
    rows = _real_clients()
    assert len(rows) == 1
    assert rows[0].product == "voice"
    assert _client_product(rows[0].model_dump()) == "voice"
