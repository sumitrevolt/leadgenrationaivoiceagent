"""RAG advancement tests — reranker + contextual ingest (no network/Qdrant)."""

from __future__ import annotations

import os


def test_lexical_rerank_reorders(monkeypatch):
    monkeypatch.delenv("USE_RERANKER", raising=False)
    from app.ml.reranker import rerank_hits

    hits = [
        {"text": "unrelated marketing fluff", "score": 0.9, "source": "a"},
        {"text": "solar panel pricing per kw installation cost", "score": 0.4, "source": "b"},
    ]
    out = rerank_hits("solar pricing kw", hits, top_k=1, vector_weight=0.15)
    assert len(out) == 1
    assert "solar" in out[0]["text"].lower()


def test_rerank_disabled_by_default(monkeypatch):
    monkeypatch.delenv("USE_RERANKER", raising=False)
    from app.ml import reranker as rr

    assert rr.rerank_enabled() is False


def test_contextual_prefix_metadata(monkeypatch):
    monkeypatch.setenv("USE_CONTEXTUAL_INGEST", "1")
    monkeypatch.delenv("USE_CONTEXTUAL_INGEST_LLM", raising=False)
    from app.voice_agent.knowledge_base import _contextual_prefix

    p = _contextual_prefix("chunk body", "niche:solar", "faq")
    assert "niche:solar" in p
    assert "faq" in p


def test_retrieve_rerank_skipped_when_false(monkeypatch):
    monkeypatch.setenv("USE_RERANKER", "1")
    from app.voice_agent.knowledge_base import KnowledgeBase

    kb = KnowledgeBase()
    ns = "rerank_off_test"
    kb.add_documents(["alpha beta gamma", "solar pricing details here"], namespace=ns)
    hits = kb.retrieve("solar pricing", k=2, namespace=ns, rerank=False)
    assert hits
    assert all("text" in h for h in hits)


def test_smart_turn_disabled_returns_none():
    from app.voice_agent import turn_detector as td

    d = td.SmartTurnDetector()
    assert d.is_endpoint(b"\x00\x01" * 800) is None
