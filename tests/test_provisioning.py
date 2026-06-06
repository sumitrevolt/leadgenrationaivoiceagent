"""
Tests: client onboarding auto-provisions 2 agents (data + leads),
and the 25-niche registry powers flows + API correctly.
"""
import pytest
from fastapi.testclient import TestClient

from app.niches import NICHES, niches_by_tier, niches_by_target


class TestNicheRegistry:
    def test_exactly_25_niches(self):
        assert len(NICHES) == 25

    def test_every_niche_has_required_fields(self):
        required = [
            "name", "tier", "target_type", "b2b_client", "end_customer",
            "keywords", "avg_deal_value", "avg_ticket_inr", "pitch_hook",
            "pricing_inr", "qualification_questions",
        ]
        for key, cfg in NICHES.items():
            for field in required:
                assert field in cfg, f"{key} missing {field}"
            p = cfg["pricing_inr"]
            assert p["qualified_lead"][0] < p["qualified_lead"][1], key
            assert p["appointment"][0] < p["appointment"][1], key
            assert p["monthly_starter"] > 0, key
            assert cfg["tier"] in ("S", "A", "B"), key
            assert cfg["target_type"] in ("b2c", "b2b", "both"), key

    def test_tier_and_target_views(self):
        assert len(niches_by_tier("S")) == 8
        total = sum(len(niches_by_tier(t)) for t in ("S", "A", "B"))
        assert total == 25
        # b2c view includes 'both'
        b2c = niches_by_target("b2c")
        assert "real_estate" in b2c and "wedding_venues" in b2c

    def test_flow_builds_for_every_niche(self):
        from app.voice_agent.flow_builder import build_flow_for_niche
        for key in NICHES:
            flow = build_flow_for_niche(key)
            assert flow is not None, f"flow failed for {key}"


class TestNichesAPI:
    def test_niches_endpoint_returns_25(self, client: TestClient):
        r = client.get("/api/data/niches")
        assert r.status_code == 200
        assert r.json()["count"] == 25

    def test_tier_filter(self, client: TestClient):
        r = client.get("/api/data/niches?tier=S")
        assert r.status_code == 200
        assert r.json()["count"] == 8

    def test_target_type_filter(self, client: TestClient):
        r = client.get("/api/data/niches?target_type=b2c")
        assert r.status_code == 200
        data = r.json()
        assert 0 < data["count"] <= 25
        for n in data["niches"]:
            assert n["target_type"] in ("b2c", "both")


class TestClientAgentProvisioning:
    payload = {
        "business_name": "SunGrow Solar Pvt Ltd",
        "contact_name": "Asha Mehta",
        "contact_email": "asha@sungrow.example",
        "contact_phone": "+919810000001",
        "industry": "solar",
    }

    def test_create_client_provisions_two_agents(self, client: TestClient, db):
        r = client.post("/api/platform/clients", json=self.payload)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["client"]["business_name"] == self.payload["business_name"]
        roles = sorted(a["role"] for a in data["agents"])
        assert roles == ["data", "leads"]
        # niche resolved from loose "solar" string
        assert "solar" in data["client"]["niche"]

    def test_provisioning_is_idempotent(self, client: TestClient, db):
        payload = dict(self.payload, contact_email="asha2@sungrow.example")
        r1 = client.post("/api/platform/clients", json=payload)
        cid = r1.json()["client"]["id"]
        r2 = client.post(f"/api/platform/clients/{cid}/provision-agents")
        assert r2.status_code == 200
        assert r2.json()["created"] == []          # dobara naye agents nahi
        assert len(r2.json()["existing"]) == 2

    def test_list_client_agents(self, client: TestClient, db):
        payload = dict(self.payload, contact_email="asha3@sungrow.example")
        r1 = client.post("/api/platform/clients", json=payload)
        cid = r1.json()["client"]["id"]
        r = client.get(f"/api/platform/clients/{cid}/agents")
        assert r.status_code == 200
        assert r.json()["count"] == 2

    def test_duplicate_email_rejected(self, client: TestClient, db):
        payload = dict(self.payload, contact_email="dup@sungrow.example")
        assert client.post("/api/platform/clients", json=payload).status_code == 200
        assert client.post("/api/platform/clients", json=payload).status_code == 409


class TestNicheResolution:
    def test_resolve_exact_key(self):
        from app.platform.agent_provisioner import resolve_niche_key
        assert resolve_niche_key("real_estate") == "real_estate"

    def test_resolve_display_name(self):
        from app.platform.agent_provisioner import resolve_niche_key
        assert resolve_niche_key("Health & Term Insurance") == "insurance"

    def test_resolve_loose_word(self):
        from app.platform.agent_provisioner import resolve_niche_key
        assert resolve_niche_key("solar").startswith("solar")

    def test_resolve_unknown_falls_back(self):
        from app.platform.agent_provisioner import resolve_niche_key
        assert resolve_niche_key("xyz-unknown-industry") == "general"
        assert resolve_niche_key(None) == "general"
