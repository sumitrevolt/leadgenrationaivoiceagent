"""Advancement backlog tests — #4 hybrid, #5 langgraph gate, #7 stt eval, #8 LLM profile."""

from __future__ import annotations


def test_llm_profile_bulk_vs_realtime():
    from app.voice_agent import free_ai as fa

    assert fa._resolve_llm_profile(None, 90) == "realtime"
    assert fa._resolve_llm_profile("bulk", 90) == "bulk"
    assert fa._resolve_llm_profile(None, 400) == "bulk"
    bulk = [p for p, _ in fa._build_llm_chain("bulk")]
    rt = [p for p, _ in fa._build_llm_chain("realtime")]
    assert bulk.index("cerebras") < bulk.index("mistral")
    # realtime = latency-first: groq (fastest) → cerebras → mistral
    assert rt.index("groq") < rt.index("cerebras")
    assert rt.index("cerebras") < rt.index("mistral")


def test_hybrid_rrf_merge():
    from app.ml.hybrid_search import rrf_merge

    dense = [{"text": "solar pricing per kw", "score": 0.8, "source": "a"}]
    sparse = [{"text": "solar panel installation cost", "score": 0.6, "source": "b"}]
    out = rrf_merge(dense, sparse, top_k=2)
    assert len(out) == 2


def test_high_stakes_gate_off(monkeypatch):
    monkeypatch.delenv("USE_LANGGRAPH_SUPERVISOR", raising=False)
    monkeypatch.delenv("USE_LANGGRAPH_HIGH_STAKES", raising=False)
    from app.agents.staff_supervisor import high_stakes_enabled, run_high_stakes

    assert high_stakes_enabled() is False
    assert run_high_stakes("x")["ok"] is False


def test_stt_fixtures_never_raise():
    from app.voice_agent import stt_eval

    rows = stt_eval.list_transcript_fixtures(3)
    assert isinstance(rows, list)
