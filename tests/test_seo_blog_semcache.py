"""
test_seo_blog_semcache.py — semantic_cache wiring in seo_blog.generate_article.

PURE-PYTHON: free_ai.chat + semantic_complete dono monkeypatch — koi network /
LLM / Redis / Qdrant nahi. Verify:
  1. SEMANTIC_CACHE OFF (default) => wrapper invoke hota hai par factory seedha
     chalta (cache="disabled"), provider asli LLM ka rehta. Byte-identical.
  2. Cache HIT path => provider "llm-cache" set hota hai (downstream gate same).
"""

import asyncio

import pytest

from app.marketing import seo_blog


@pytest.mark.asyncio
async def test_semcache_wrapper_invoked_and_falls_through_when_off(monkeypatch):
    """Flag OFF: semantic_complete call hota hai aur factory ko pass-through karta."""
    monkeypatch.delenv("SEMANTIC_CACHE", raising=False)

    chat_calls = {"n": 0}
    sem_calls = {"n": 0}

    # Fake free_ai.chat -> valid 2-heading article so LLM branch retained.
    async def fake_chat(system, messages, **kw):
        chat_calls["n"] += 1
        text = (
            "Intro paragraph yahan hai jo kaafi lamba hai taaki gate paas ho jaye "
            "aur template fallback na ho. "
            * 6
            + "\n\n## Pehla section\nPehle section ka useful content yahan likha hai.\n\n"
            "## Doosra section\nDoosre section ka useful content yahan likha hai.\n"
        )
        return text, "groq"

    # Fake semantic_complete: factory call karo (fall-through), info=disabled.
    async def fake_semantic_complete(key_text, factory, **kw):
        sem_calls["n"] += 1
        assert "scope" in kw  # wrapper scope=niche pass karta hai
        val = factory()
        if hasattr(val, "__await__"):
            val = await val
        return val, {"cache": "disabled"}

    monkeypatch.setattr(seo_blog.free_ai, "chat", fake_chat)
    import app.cache.semantic_cache as sc

    monkeypatch.setattr(sc, "semantic_complete", fake_semantic_complete)

    art = await seo_blog.generate_article("salon_spa", "Pune", "test topic")

    assert sem_calls["n"] == 1, "semantic_complete wrapper invoke hona chahiye"
    assert chat_calls["n"] == 1, "fall-through pe factory (free_ai.chat) chala"
    # OFF => asli provider preserve, "llm-cache" NAHI.
    assert art["provider"] == "groq"
    assert art["html_body"].count("<h2>") >= 2


@pytest.mark.asyncio
async def test_semcache_hit_sets_llm_cache_provider(monkeypatch):
    """Cache HIT path: provider 'llm-cache' set, factory call NAHI hota."""
    monkeypatch.setenv("SEMANTIC_CACHE", "1")

    chat_calls = {"n": 0}

    async def fake_chat(system, messages, **kw):
        chat_calls["n"] += 1
        return "should-not-be-called", "groq"

    cached_text = (
        "Cached intro paragraph kaafi lamba hai taaki gate paas ho jaye. " * 8
        + "\n\n## Cached section ek\nContent.\n\n## Cached section do\nContent.\n"
    )

    async def fake_semantic_complete(key_text, factory, **kw):
        # HIT: factory bilkul call nahi hota.
        return cached_text, {"cache": "semantic", "score": 0.99}

    monkeypatch.setattr(seo_blog.free_ai, "chat", fake_chat)
    import app.cache.semantic_cache as sc

    monkeypatch.setattr(sc, "semantic_complete", fake_semantic_complete)

    art = await seo_blog.generate_article("salon_spa", "Pune", "test topic")

    assert chat_calls["n"] == 0, "cache HIT pe LLM call nahi hona chahiye"
    assert art["provider"] == "llm-cache"
    assert art["html_body"].count("<h2>") >= 2


if __name__ == "__main__":  # pragma: no cover
    asyncio.run(test_semcache_wrapper_invoked_and_falls_through_when_off(None))  # type: ignore
