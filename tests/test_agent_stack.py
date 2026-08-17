"""
Tests: agent stack (P1 Qdrant RAG + P2 LangGraph supervisor).

Sab tests network/Qdrant/Gemini ke BINA chalte hain — pure logic + TestClient.
- /api/agents/* endpoints (status hamesha; run ko stub karke, taaki langgraph
  installed ho tab bhi koi graph/LLM call na ho).
- route_for_task() rule-based router directly (no langgraph needed).
- KnowledgeBase backend selection with qdrant_url empty (keyword fallback),
  add/retrieve roundtrip + namespace isolation.
- Qdrant availability checks short-circuit on empty URL (no crash, no network).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.agents import supervisor as sup
from app.voice_agent import knowledge_base as kbmod
from app.voice_agent.knowledge_base import KnowledgeBase


@pytest.fixture
def no_qdrant(monkeypatch):
    """Force qdrant_url empty so the KB kabhi Qdrant try na kare (no network)."""
    from app.config import settings

    monkeypatch.setattr(settings, "qdrant_url", "", raising=False)
    return settings


class TestAgentsAPI:
    def test_status_endpoint(self, client: TestClient):
        r = client.get("/api/agents/status")
        assert r.status_code == 200
        data = r.json()
        assert data["engine"] == "langgraph-supervisor"
        assert isinstance(data["available"], bool)
        assert isinstance(data["nodes"], list)
        assert "workforce_runtime" not in data
        for node in ("supervisor", "data_agent", "leads_agent"):
            assert node in data["nodes"]

    def test_run_endpoint_200_or_501(self, client: TestClient, monkeypatch):
        # Stub the graph runner: langgraph installed ho to bhi koi LLM/network
        # call nahi. AGENTS_AVAILABLE=False par 501 stub se pehle hi aata hai.
        async def _stub(task, client_id=None, niche="general"):
            return {"route": "leads_agent", "result": "stub", "niche": niche or "general"}

        monkeypatch.setattr("app.api.agents.run_supervisor_task", _stub)
        r = client.post("/api/agents/run", json={"task": "qualify lead call campaign"})
        assert r.status_code in (200, 501)
        if r.status_code == 200:
            assert "route" in r.json()

    def test_run_rejects_too_short_task(self, client: TestClient):
        # AgentRunRequest.task has min_length=3 — validation 422 deta hai,
        # availability se pehle hi (deterministic dono environments me).
        r = client.post("/api/agents/run", json={"task": "x"})
        assert r.status_code == 422


class TestSupervisorRouting:
    """route_for_task — pure function, langgraph ki zaroorat nahi."""

    def test_data_task_routes_to_data_agent(self):
        assert sup.route_for_task("seed kb research profile") == "data_agent"

    def test_leads_task_routes_to_leads_agent(self):
        assert sup.route_for_task("qualify lead call campaign") == "leads_agent"

    def test_default_route_is_leads_agent(self):
        assert sup.route_for_task("totally unrelated gibberish") == "leads_agent"
        assert sup.route_for_task("") == "leads_agent"

    def test_data_keywords_checked_before_leads(self):
        # mixed task: "research" (data) + "leads"/"campaign" (leads) → data wins
        assert sup.route_for_task("research leads for campaign") == "data_agent"

    def test_routing_is_case_insensitive(self):
        assert sup.route_for_task("SEED KB RESEARCH") == "data_agent"
        assert sup.route_for_task("Qualify LEAD") == "leads_agent"

    def test_supervisor_node_uses_router(self, monkeypatch):
        # Phase-2: node ab ASYNC hai (semantic free-LLM router + keyword
        # fallback). LLM ko deterministic keyword fallback se replace karo —
        # no network — aur node ke route-contract ko assert karo.
        async def _kw_only(task):
            return sup.route_for_task(task)

        monkeypatch.setattr(sup, "semantic_route_for_task", _kw_only)

        def run(state):
            return asyncio.run(sup.supervisor_node(state))

        assert run({"task": "seed kb"})["route"] == "data_agent"
        assert run({"task": "call campaign"})["route"] == "leads_agent"
        assert run({})["route"] == "leads_agent"

    def test_graph_nodes_constant(self):
        assert sup.GRAPH_NODES == ["supervisor", "data_agent", "leads_agent"]

    @pytest.mark.skipif(not sup.AGENTS_AVAILABLE, reason="langgraph not installed")
    def test_workflow_built_when_langgraph_available(self):
        assert sup._WORKFLOW is not None


class TestKnowledgeBackends:
    @pytest.fixture
    def kb(self, no_qdrant):
        # prefer_chroma=False => deterministic pure-python keyword backend
        # (Chroma path heavyweight embedder load try kar sakta hai — tests me nahi).
        return KnowledgeBase(prefer_chroma=False)

    def test_backend_not_qdrant_when_url_empty(self, kb):
        backend = kb.backend("t1")
        assert backend != "qdrant"
        assert backend in ("chroma", "keyword")

    def test_add_retrieve_roundtrip(self, kb):
        added = kb.add_documents(
            ["Solar rooftop subsidy 40 percent tak milti hai residential customers ko."],
            source="faq",
            namespace="t1",
        )
        assert added >= 1
        hits = kb.retrieve("solar subsidy kitni milti hai", k=3, namespace="t1")
        assert hits, "same-namespace retrieve should hit"
        top = hits[0]
        assert set(top.keys()) >= {"text", "score", "source"}
        assert "subsidy" in top["text"].lower()
        assert top["score"] > 0
        assert top["source"] == "faq"

    def test_namespace_isolation(self, kb):
        hidden_fact = "Wedding venue package costs two lakh rupees flat."
        kb.add_documents([hidden_fact], namespace="t1")
        hits = kb.retrieve("wedding venue package cost rupees", k=5, namespace="t2")
        assert all(hidden_fact not in h.get("text", "") for h in hits)

    def test_grounded_answer_safe_fallback_on_empty_namespace(self, kb):
        ans = kb.grounded_answer("koi bhi sawaal", namespace="empty_ns")
        assert ans == kbmod._SAFE_FALLBACK

    def test_stats_reports_non_qdrant_backend(self, kb):
        kb.add_documents(["Pricing per qualified lead ₹200-500 hoti hai."], namespace="t1")
        s = kb.stats("t1")
        assert s["backend"] != "qdrant"
        assert s["chunks"] >= 1


class TestQdrantIndexUnit:
    def test_url_helper_empty_and_stripped(self, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "qdrant_url", "", raising=False)
        assert kbmod._get_qdrant_url() == ""
        monkeypatch.setattr(settings, "qdrant_url", "   ", raising=False)
        assert kbmod._get_qdrant_url() == ""  # whitespace bhi disabled

    def test_try_qdrant_returns_none_without_url(self, no_qdrant):
        # availability check: empty url => None, no crash, no network
        assert KnowledgeBase._try_qdrant("any_ns") is None

    def test_try_qdrant_empty_url_does_not_set_disabled_flag(self, no_qdrant, monkeypatch):
        # empty url ko _QDRANT_DISABLED se PEHLE short-circuit hona chahiye —
        # warna baad me URL configure karne par bhi backend permanently band rehta.
        monkeypatch.setattr(kbmod, "_QDRANT_DISABLED", False)
        assert KnowledgeBase._try_qdrant("ns") is None
        assert kbmod._QDRANT_DISABLED is False
