from __future__ import annotations


def test_kb_tries_the_docker_baked_embedding_before_runtime_download_models():
    from app.voice_agent import knowledge_base

    assert knowledge_base._EMBED_CANDIDATES[0] == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


def test_cold_embedder_timeout_does_not_permanently_disable_qdrant(monkeypatch):
    from app.voice_agent import knowledge_base

    monkeypatch.setattr(knowledge_base, "_QDRANT_DISABLED", False)
    monkeypatch.setattr(knowledge_base, "_QDRANT_EMBEDDER", None)
    monkeypatch.setattr(
        knowledge_base,
        "_get_qdrant_embedder",
        lambda: (_ for _ in ()).throw(
            RuntimeError("fastembed model not ready within 20s — qdrant is still warming")
        ),
    )

    assert knowledge_base.KnowledgeBase._try_qdrant("default") is None
    assert knowledge_base._QDRANT_DISABLED is False
