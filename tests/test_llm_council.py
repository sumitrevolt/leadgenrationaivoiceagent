"""LLM Council — parse helpers + orchestration (mocked providers)."""

import asyncio


def test_parse_ranking_from_text():
    from app.agents.llm_council import parse_ranking_from_text

    text = """Response A is good.
Response B is ok.

FINAL RANKING:
1. Response C
2. Response A
3. Response B"""
    assert parse_ranking_from_text(text) == ["Response C", "Response A", "Response B"]

    assert parse_ranking_from_text("no ranking here Response D Response A") == [
        "Response D",
        "Response A",
    ]


def test_calculate_aggregate_rankings():
    from app.agents.llm_council import calculate_aggregate_rankings

    label_to_model = {"Response A": "Mistral", "Response B": "Groq"}
    stage2 = [
        {
            "ranking": "FINAL RANKING:\n1. Response A\n2. Response B",
            "parsed_ranking": ["Response A", "Response B"],
        },
        {
            "ranking": "FINAL RANKING:\n1. Response B\n2. Response A",
            "parsed_ranking": ["Response B", "Response A"],
        },
    ]
    agg = calculate_aggregate_rankings(stage2, label_to_model)
    assert len(agg) == 2
    assert agg[0]["model"] in ("Mistral", "Groq")
    assert agg[0]["average_rank"] <= agg[1]["average_rank"]


def test_run_full_council_mocked(monkeypatch, tmp_path):
    from app.agents import coordinator, llm_council

    members = [
        {"provider": "mistral", "model": "mistral-small-latest", "label": "Mistral"},
        {"provider": "groq", "model": "llama-3.1-8b-instant", "label": "Groq"},
    ]
    monkeypatch.setattr(llm_council, "available_members", lambda: members)
    monkeypatch.setattr(llm_council, "council_enabled", lambda: True)

    async def _fake_ask(provider, model, user, **kw):
        if "evaluating different responses" in user.lower():
            return (
                "Response A good.\nFINAL RANKING:\n1. Response A\n2. Response B",
                provider,
            )
        if "Chairman" in (kw.get("system") or ""):
            return "Final synthesized Hinglish answer from council.", provider
        if provider == "mistral":
            return "Mistral opinion A about solar outreach.", provider
        return "Groq opinion B about WhatsApp links.", provider

    monkeypatch.setattr(llm_council, "_ask", _fake_ask)
    monkeypatch.setattr(coordinator, "_RUNS", str(tmp_path / "r.jsonl"))

    result = asyncio.run(llm_council.run_full_council("Email ya WhatsApp pe focus karein?"))
    assert result["ok"] is True
    assert len(result["stage1"]) == 2
    assert result["stage3"]["response"]
    assert result["metadata"]["aggregate_rankings"]

    wrapped = asyncio.run(coordinator.council("Pricing strategy kya honi chahiye?"))
    assert wrapped["ok"] is True
    assert wrapped["pattern"] == "llm_council"
    assert wrapped["summary"]


def test_council_disabled(monkeypatch):
    from app.agents import llm_council

    monkeypatch.setattr(llm_council, "council_enabled", lambda: False)
    out = asyncio.run(llm_council.run_full_council("test question here"))
    assert out["ok"] is False
    assert "disabled" in out["error"].lower()


def test_council_insufficient_providers(monkeypatch):
    from app.agents import llm_council

    monkeypatch.setattr(llm_council, "council_enabled", lambda: True)
    monkeypatch.setattr(llm_council, "available_members", lambda: [])
    out = asyncio.run(llm_council.run_full_council("test question here"))
    assert out["ok"] is False
    assert "providers" in out["error"].lower()
