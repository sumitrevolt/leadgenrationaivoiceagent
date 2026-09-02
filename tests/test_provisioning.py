"""
Tests: client onboarding auto-provisions 2 agents (data + leads),
and the 26-niche registry (25 research + ai_marketing) powers flows + API correctly.
"""

from fastapi.testclient import TestClient

from app.niches import NICHES, niches_by_target, niches_by_tier


class TestNicheRegistry:
    def test_exactly_51_builtin_niches(self):
        # ADR-009 + niche rebuild (commits 46f3b4d/50ea9a8): curated 39 builtin
        # niches (S=8, A=14, B=17) + wizard catalog extension 2026-08 (12 naye
        # SMB niches; real_estate folded into real_estate_luxury as a builtin) = 51.
        from app.niches import _BUILTIN_KEYS

        assert len(_BUILTIN_KEYS) == 51

    def test_every_niche_has_required_fields(self):
        required = [
            "name",
            "tier",
            "target_type",
            "b2b_client",
            "end_customer",
            "keywords",
            "avg_deal_value",
            "avg_ticket_inr",
            "pitch_hook",
            "lead_band",  # ADR-009: per-lead pricing_inr REMOVED
            "qualification_questions",
        ]
        for key, cfg in NICHES.items():
            for field in required:
                assert field in cfg, f"{key} missing {field}"
            assert cfg["lead_band"] in ("A", "B", "C"), key  # voice-product band (ADR-009)
            assert cfg["tier"] in ("S", "A", "B", "C"), key
            assert cfg["target_type"] in ("b2c", "b2b", "both"), key

    def test_tier_and_target_views(self):
        assert len(niches_by_tier("S")) == 8  # S-tier (post niche rebuild)
        total = sum(len(niches_by_tier(t)) for t in ("S", "A", "B"))
        assert total == 51  # builtin tiers; custom niches tier "C" me hote hain
        # b2c view includes 'both'
        b2c = niches_by_target("b2c")
        assert "cloud_kitchen" in b2c and "skin_dermatology" in b2c

    def test_flow_builds_for_every_niche(self):
        from app.voice_agent.flow_builder import build_flow_for_niche

        for key in NICHES:
            flow = build_flow_for_niche(key)
            assert flow is not None, f"flow failed for {key}"


class TestNicheKnowledge:
    """Har builtin niche ka grounded knowledge + objection playbook complete ho."""

    def test_every_builtin_niche_has_a_knowledge_pack(self):
        from app.niche_knowledge import NICHE_KNOWLEDGE
        from app.niches import _BUILTIN_KEYS

        missing = [k for k in _BUILTIN_KEYS if k not in NICHE_KNOWLEDGE]
        assert not missing, f"builtin niches missing knowledge pack: {missing}"

    def test_packs_are_substantive(self):
        from app.niche_knowledge import NICHE_KNOWLEDGE

        for key, pack in NICHE_KNOWLEDGE.items():
            assert len(pack.get("facts", [])) >= 3, f"{key}: <3 facts"
            assert len(pack.get("benefits", [])) >= 2, f"{key}: <2 benefits"
            assert len(pack.get("objections", {})) >= 2, f"{key}: <2 objections"
            for f in pack["facts"] + pack["benefits"]:
                assert isinstance(f, str) and f.strip(), f"{key}: empty fact/benefit"

    def test_helpers_and_generic_fallback(self):
        from app.niche_knowledge import (
            knowledge_facts,
            match_objection,
            niche_benefits,
            objection_response,
        )

        assert knowledge_facts("solar_residential")
        assert niche_benefits("solar_residential")
        # unknown niche -> generic, never crashes
        assert knowledge_facts("xyz-unknown-niche")
        assert objection_response("xyz-unknown-niche", "busy")
        # free-form utterance se rebuttal match ho
        assert match_objection("solar_residential", "yeh to bahut mehenga hai")
        assert match_objection("real_estate", "abhi bas dekh raha hoon") is not None

    def test_common_objection_matches_for_every_builtin_niche(self):
        from app.niche_knowledge import match_objection
        from app.niches import _BUILTIN_KEYS

        for key in _BUILTIN_KEYS:
            assert match_objection(key, "thoda mehenga lag raha hai") is not None, key


class TestNichesAPI:
    def test_niches_endpoint_returns_25_plus(self, client: TestClient):
        r = client.get("/api/data/niches")
        assert r.status_code == 200
        assert r.json()["count"] >= 25  # builtin 25 + koi bhi custom

    def test_tier_filter(self, client: TestClient):
        r = client.get("/api/data/niches?tier=S")
        assert r.status_code == 200
        assert r.json()["count"] == 8  # S-tier (post niche rebuild)

    def test_target_type_filter(self, client: TestClient):
        r = client.get("/api/data/niches?target_type=b2c")
        assert r.status_code == 200
        data = r.json()
        assert 0 < data["count"] <= 51  # wizard catalog extension 2026-08 (was 42)
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
        assert r2.json()["created"] == []  # dobara naye agents nahi
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


class TestCustomNiches:
    def _cleanup(self, key):
        from app.niches import remove_custom_niche

        try:
            remove_custom_niche(key)
        except Exception:
            pass

    def test_add_custom_niche_via_api_and_use_everywhere(self, client: TestClient, db):
        payload = {
            "name": "Pet Grooming Studios",
            "target_type": "b2c",
            "avg_ticket_inr": "₹2,000–8,000",
        }
        r = client.post("/api/data/niches", json=payload)
        assert r.status_code == 200, r.text
        key = r.json()["id"]
        try:
            assert key == "pet_grooming_studios"
            cfg = r.json()["niche"]
            assert cfg["tier"] == "C" and cfg["custom"] is True
            assert cfg["lead_band"] in ("A", "B", "C")  # ADR-009

            # appears in listing with custom flag
            listing = client.get("/api/data/niches").json()
            ids = {n["id"]: n for n in listing["niches"]}
            assert key in ids and ids[key]["custom"] is True

            # flow builds for the new niche (voice agent kaam karega)
            from app.voice_agent.flow_builder import build_flow_for_niche

            assert build_flow_for_niche(key) is not None

            # client onboarding on the custom niche → 2 agents on that niche
            cr = client.post(
                "/api/platform/clients",
                json={
                    "business_name": "FurryCare Pets",
                    "contact_name": "Ravi",
                    "contact_email": "ravi@furrycare.example",
                    "contact_phone": "+919810000099",
                    "niche": key,
                },
            )
            assert cr.status_code == 200, cr.text
            assert cr.json()["client"]["niche"] == key
            roles = sorted(a["role"] for a in cr.json()["agents"])
            assert roles == ["data", "leads"]
        finally:
            self._cleanup(key)

    def test_duplicate_custom_niche_409(self, client: TestClient):
        r1 = client.post("/api/data/niches", json={"name": "Drone Photography"})
        key = r1.json()["id"]
        try:
            r2 = client.post("/api/data/niches", json={"name": "Drone Photography"})
            assert r2.status_code == 409
        finally:
            self._cleanup(key)

    def test_builtin_niche_delete_protected(self, client: TestClient):
        r = client.delete("/api/data/niches/ai_marketing")
        assert r.status_code == 403

    def test_delete_custom_niche(self, client: TestClient):
        r1 = client.post("/api/data/niches", json={"name": "Yacht Charters"})
        key = r1.json()["id"]
        r2 = client.delete(f"/api/data/niches/{key}")
        assert r2.status_code == 200
        from app.niches import NICHES as live

        assert key not in live


class TestNicheResolution:
    def test_resolve_exact_key(self):
        from app.platform.agent_provisioner import resolve_niche_key

        assert resolve_niche_key("solar_residential") == "solar_residential"

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
