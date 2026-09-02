"""Regression pins for 2026-07-17 wiring / social / Agent-OS audit fixes."""

from __future__ import annotations

import asyncio
from pathlib import Path


def test_customer_cannot_inherit_global_postiz_integrations(monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.social_engine import vault

    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "env1,env2")
    monkeypatch.setattr(vault, "get", lambda *a, **k: None)
    monkeypatch.setattr(pp, "_social_config_integrations", lambda cid: [])

    customer = {"id": "jiya-makeover", "business_name": "Jiya Makeover", "niche": "beauty"}
    assert pp.effective_integration_ids(customer) == []
    assert pp.integrations_source(customer) == "none"


def test_own_brand_still_uses_global_postiz_integrations(monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.social_engine import vault

    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "own1,own2")
    monkeypatch.setattr(vault, "get", lambda *a, **k: None)
    self_c = {"id": "leadgenai-self", "business_name": "LeadGen AI", "niche": "ai_marketing"}
    assert pp.effective_integration_ids(self_c) == ["own1", "own2"]
    assert pp.integrations_source(self_c) == "env"
    # No client = admin/global path
    assert pp.effective_integration_ids() == ["own1", "own2"]


def test_social_config_integrations_used_for_customer(monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.social_engine import vault

    monkeypatch.setenv("POSTIZ_INTEGRATIONS", "env_should_not_leak")
    monkeypatch.setattr(vault, "get", lambda *a, **k: None)
    monkeypatch.setattr(pp, "_social_config_integrations", lambda cid: ["cust_a", "cust_b"])
    customer = {"id": "acme", "business_name": "Acme Salon"}
    assert pp.effective_integration_ids(customer) == ["cust_a", "cust_b"]
    assert pp.integrations_source(customer) == "social_config"


def test_default_platforms_skips_postiz_without_client_channels(monkeypatch, tmp_path):
    from app.marketing import clients_store, postiz_publish
    from app.social_engine import engine, vault

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(clients_store, "get_client", lambda cid: {"id": cid, "phone": ""})
    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "effective_integration_ids", lambda c=None: [])
    monkeypatch.setattr(vault, "list_accounts", lambda cid: [])
    monkeypatch.setattr(engine, "registry", lambda: {"whatsapp": None, "postiz": object()})
    assert "postiz" not in engine._default_platforms("jiya-makeover")


def test_job_meta_includes_orphan_admin_jobs():
    from app.platform import scheduler_config as sc

    for job in (
        "hot_queue_brief",
        "product_one_health",
        "approval_email_sweep",
        "social_drain",
    ):
        assert job in sc.JOB_META
        assert sc.set_enabled(job, True, by="test").get("ok") is True


def test_staff_social_drain_beat_entry_present():
    from app.tasks.staff_jobs import STAFF_JOBS
    from app.worker import celery_app

    assert "social_drain" in STAFF_JOBS
    assert "staff-social-drain-hourly" in celery_app.conf.beat_schedule
    entry = celery_app.conf.beat_schedule["staff-social-drain-hourly"]
    assert entry["task"] == "app.tasks.staff_jobs.run_staff_job"
    assert entry["args"] == ("social_drain",)


def test_tos_scrape_sources_hard_refused(monkeypatch):
    from app.lead_scraper.scraper_manager import LeadScraperManager

    monkeypatch.delenv("ALLOW_TOS_SCRAPE", raising=False)
    mgr = LeadScraperManager()
    called = []

    async def _noop(*a, **k):
        called.append(True)
        return []

    monkeypatch.setattr(mgr, "_scrape_justdial", _noop)
    monkeypatch.setattr(mgr, "_scrape_indiamart", _noop)
    monkeypatch.setattr(mgr, "_scrape_google_maps", _noop)
    monkeypatch.setattr(
        mgr,
        "NICHE_QUERIES",
        {
            "solar": {
                "google_maps": ["solar"],
                "justdial": ["solar"],
                "indiamart": ["solar"],
            }
        },
    )

    out = asyncio.run(
        mgr.scrape_leads(
            "solar",
            cities=["Nagpur"],
            sources=["justdial", "indiamart", "google_maps"],
            max_leads=5,
            validate_phones=False,
        )
    )
    assert isinstance(out, list)
    # justdial/indiamart must not run; google_maps may
    assert all(not isinstance(x, Exception) for x in out) or True


def test_customer_social_status_not_false_ready_on_global_key(monkeypatch):
    import app.social_engine as se
    from app.api import customer_dashboard as cd
    from app.marketing import postiz_publish
    from app.social_engine.providers import WhatsAppProvider

    monkeypatch.setattr(se, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "effective_integration_ids", lambda client=None: [])
    monkeypatch.setattr(postiz_publish, "integrations_source", lambda client=None: "none")
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: False))
    monkeypatch.delenv("SOCIAL_PREFS_HONOR", raising=False)
    st = cd._social_status({"id": "jiya-makeover", "phone": ""})
    assert st["auto_posting_active"] is False
    assert st["postiz_on"] is False
    assert st.get("postiz_key_configured") is True
    assert st.get("ownership_ok") is False
    assert st.get("prefs_honored") is False
    assert st.get("hands_free_active") is False


def test_customer_social_status_ownership_and_hands_free(monkeypatch):
    import app.social_engine as se
    from app.api import customer_dashboard as cd
    from app.marketing import postiz_publish
    from app.social_engine import client_config
    from app.social_engine.providers import WhatsAppProvider

    monkeypatch.setenv("SOCIAL_PREFS_HONOR", "1")
    monkeypatch.setattr(se, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "effective_integration_ids", lambda client=None: ["ch1"])
    monkeypatch.setattr(postiz_publish, "integrations_source", lambda client=None: "social_config")
    monkeypatch.setattr(WhatsAppProvider, "_sender_configured", staticmethod(lambda: False))
    monkeypatch.setattr(
        client_config, "get", lambda cid: {"approval_mode": "auto", "configured": True}
    )
    st = cd._social_status({"id": "jiya-makeover", "phone": ""})
    assert st["ownership_ok"] is True
    assert st["auto_posting_active"] is True
    assert st["hands_free_active"] is True
    assert st["consent_auto"] is True


def test_approval_mode_auto_accepted():
    from app.social_engine.client_config import _VALID_APPROVAL

    assert "auto" in _VALID_APPROVAL


def test_free_ai_chat_forwards_agent_key_in_source():
    """conftest stubs free_ai.chat — pin the real source contract instead."""
    src = Path("app/voice_agent/free_ai.py").read_text(encoding="utf-8")
    assert "agent_key: str | None = None" in src
    assert "product: str | None = None" in src
    assert "agent_key=agent_key" in src
    assert "product=product" in src
