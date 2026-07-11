from __future__ import annotations


def test_kb_tries_the_docker_baked_embedding_before_runtime_download_models():
    from app.voice_agent import knowledge_base

    assert knowledge_base._EMBED_CANDIDATES[0] == (
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )
