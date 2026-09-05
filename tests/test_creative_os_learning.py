"""Unit tests for Creative OS self-improvement learning engine and KB integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.marketing.creative_os import brief as B
from app.marketing.creative_os import flags
from app.marketing.creative_os import hyperframes_provider as HP
from app.marketing.creative_os import learning as L
from app.marketing.creative_os.learning import (
    CreativeLearningLink,
    get_learning_history,
    get_tenant_recipe_stats,
    recommend,
    record_learning,
    suggest_next_creative_strategy,
    sync_creative_learning_to_kb,
)
from app.marketing.creative_os.recipes import build_scene_plan
from app.marketing.creative_os.spec import CreativeSpec


@pytest.fixture(autouse=True)
def _isolate_learning(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_LEARNING_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_LEARNING_ROOT", str(tmp_path / "learning"))
    monkeypatch.setenv("CREATIVE_LEDGER_ROOT", str(tmp_path / "ledger"))


def test_learning_link_serialization():
    link = CreativeLearningLink(
        creative_id="c_123",
        revision=1,
        tenant_id="tenant_a",
        recipe="service_showcase",
        metrics={"avg_watch_s": 4.5, "ctr": 0.035},
        lead_event_ids=["lead_1", "lead_2"],
        verified=True,
    )
    data = link.to_dict()
    assert data["creative_id"] == "c_123"
    assert data["metrics"]["avg_watch_s"] == 4.5

    rebuilt = CreativeLearningLink.from_dict(data)
    assert rebuilt.creative_id == link.creative_id
    assert rebuilt.verified is True
    assert rebuilt.recipe == "service_showcase"


def test_record_learning_and_get_history():
    link1 = CreativeLearningLink(
        creative_id="c_01",
        revision=1,
        tenant_id="tenant_test",
        recipe="offer_announcement",
        metrics={"avg_watch_s": 2.1, "ctr": 0.008},
        verified=True,
    )
    link2 = CreativeLearningLink(
        creative_id="c_02",
        revision=1,
        tenant_id="tenant_test",
        recipe="service_showcase",
        metrics={"avg_watch_s": 5.2, "ctr": 0.042},
        lead_event_ids=["lead_101"],
        verified=True,
    )

    res1 = record_learning(link1)
    res2 = record_learning(link2)
    assert res1["ok"] is True
    assert res2["ok"] is True

    hist = get_learning_history("tenant_test")
    assert len(hist) == 2
    assert hist[0].creative_id == "c_01"
    assert hist[1].creative_id == "c_02"


def test_recipe_stats_aggregates_and_prefers_winning_recipe():
    # Recipe A: low watch time & low CTR
    for i in range(2):
        record_learning(
            CreativeLearningLink(
                creative_id=f"c_a{i}",
                revision=1,
                tenant_id="tenant_perf",
                recipe="offer_announcement",
                metrics={"avg_watch_s": 1.8, "ctr": 0.005},
                verified=True,
            )
        )

    # Recipe B: high watch time, high CTR, leads
    for i in range(2):
        record_learning(
            CreativeLearningLink(
                creative_id=f"c_b{i}",
                revision=1,
                tenant_id="tenant_perf",
                recipe="service_showcase",
                metrics={"avg_watch_s": 6.0, "ctr": 0.05},
                lead_event_ids=[f"lead_{i}"],
                verified=True,
            )
        )

    stats = get_tenant_recipe_stats("tenant_perf")
    assert stats["ok"] is True
    assert stats["sample_count"] == 4
    # service_showcase should easily win due to higher watch time & CTR
    assert stats["prefer_recipe"] == "service_showcase"
    assert "service_showcase" in stats["recipes"]
    assert "offer_announcement" in stats["recipes"]

    # Overall avg watch time = (1.8 + 1.8 + 6.0 + 6.0) / 4 = 3.9s -> hook improvement not needed
    assert stats["hook_improvement_needed"] is False


def test_suggest_next_creative_strategy():
    record_learning(
        CreativeLearningLink(
            creative_id="c_h1",
            revision=1,
            tenant_id="tenant_strat",
            recipe="problem_solution",
            metrics={"avg_watch_s": 1.2, "ctr": 0.01},
            verified=True,
        )
    )

    strategy = suggest_next_creative_strategy("tenant_strat")
    assert strategy["ok"] is True
    assert strategy["prefer_recipe"] == "problem_solution"
    assert strategy["hook_improvement_needed"] is True
    assert any("Strengthen first 2s" in r for r in strategy["recommendations"])


def test_sync_creative_learning_to_kb(monkeypatch):
    added_docs = []

    class MockKB:
        def add_documents(self, docs, source="", namespace=""):
            added_docs.append((docs, source, namespace))

    monkeypatch.setattr("app.voice_agent.knowledge_base.get_knowledge_base", lambda: MockKB())

    ok = sync_creative_learning_to_kb("tenant_kb", "Recipe service_showcase performed 2.5x better")
    assert ok is True
    assert len(added_docs) == 1
    docs, src, ns = added_docs[0]
    assert "Recipe service_showcase" in docs[0]
    assert ns == "client:tenant_kb"


def test_recommend_contract_unverified_vs_verified():
    unverified = CreativeLearningLink(
        creative_id="c_u", revision=1, tenant_id="t1", metrics={"avg_watch_s": 1.0}, verified=False
    )
    rec_unverified = recommend(unverified)
    assert rec_unverified["ok"] is True
    assert rec_unverified["recommendations"] == []
    assert rec_unverified["note"] == "no_verified_metrics"

    verified = CreativeLearningLink(
        creative_id="c_v",
        revision=1,
        tenant_id="t1",
        metrics={"avg_watch_s": 1.4, "ctr": 0.005},
        verified=True,
    )
    rec_verified = recommend(verified, recipe_stats={"prefer_recipe": "beauty_luxury_offer_v1"})
    assert rec_verified["ok"] is True
    assert any("Increase hook length" in r for r in rec_verified["recommendations"])
    assert any("Change CTA" in r for r in rec_verified["recommendations"])
    assert any("Prefer recipe: beauty_luxury_offer_v1" in r for r in rec_verified["recommendations"])


def test_brief_resolves_brand_with_kb_grounding(monkeypatch):
    client_rec = {
        "id": "tenant_grounded",
        "business_name": "Grounded Salon",
        "niche": "salon",
        "city": "Pune",
        "plan": "starter",
        "status": "active",
        "phone": "+919876543210",
        "brand": {"primary": "#112233", "accent": "#445566", "tagline": "Grounded Hair & Beauty"},
        "services": [{"name": "Hair Spa", "price_inr": 800}],
    }
    monkeypatch.setattr(B, "_client_record", lambda tid: client_rec)
    monkeypatch.setattr(
        "app.marketing.kb_personalize.client_context",
        lambda tid, query="", k=4: [
            "5+ Years Experience in Bridal Hair",
            "100% Organic Products certified",
            "Over 500 Happy Brides served",
        ],
    )

    prof = B.resolve_brand_profile("tenant_grounded")
    assert prof.business_name == "Grounded Salon"
    assert prof.phone == "+919876543210"
    assert prof.contact_display == "+919876543210"
    assert len(prof.kb_facts) == 3
    assert prof.sources["kb_facts"] == "knowledge_base"
    assert len(prof.verified_trust) >= 2
    assert "5+ Years Experience" in prof.verified_trust[0]


def test_hyperframes_manifest_incorporates_kb_trust_and_services(monkeypatch):
    brand_facts = {
        "business_name": "Studio Elegance",
        "city": "Delhi",
        "primary_color": "#223344",
        "accent_color": "#ffaa00",
        "tagline": "Delhi Premier Luxury Salon",
        "contact_display": "+919800000000",
        "verified_trust": ["Certified Stylists", "Premium German Products"],
        "verified_metrics": [{"value": "1000+", "label": "Clients"}],
        "services": [{"name": "Bridal Glow", "price_inr": 5000}],
    }

    # CreativeSpec without explicit service scenes -> tests fallback to verified services
    spec = CreativeSpec(
        creative_id="c_manifest_test",
        tenant_id="tenant_elegance",
        goal="salon",
        audience="Studio Elegance",
        offer="20% off",
        language="hinglish",
        platform="instagram",
        aspect_ratio="9:16",
        recipe="local_service_promo_v1",
        scenes=[
            {"role": "hook", "text": "Are you ready for festive glow?", "duration_s": 4.0},
            {"role": "cta", "text": "Call now to book", "duration_s": 4.0},
        ],
        captions={},
        cta="Call now",
        provider="hyperframes",
    )

    manifest = HP.build_manifest(
        spec, brand=brand_facts, template_id="local_service_promo_v1"
    )
    vars_ = manifest["variables"]

    assert vars_["business_name"] == "Studio Elegance"
    assert vars_["contact_display"] == "+919800000000"
    # trust_json should contain the verified trust items
    trust = json.loads(vars_["trust_json"])
    assert "Certified Stylists" in trust
    # steps_json should have fallen back to the service item
    steps = json.loads(vars_["steps_json"])
    assert any("Bridal Glow" in s.get("title", "") for s in steps)
