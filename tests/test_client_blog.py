"""Per-client blog (#29) — generate + store + render. Was a dormant gap: customer
got a template only, no live indexable per-client blog page. Now /b/{slug}/blog is real.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.mark.asyncio
async def test_generate_store_list_render(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from app.marketing import client_blog
    from app.voice_agent import free_ai

    monkeypatch.setattr(client_blog, "_DIR", tmp_path / "blogs")

    async def _fake_chat(system, messages, **kw):
        return ("TITLE: Solar Bachat Tips\nBODY: Pehla para.\n\nDoosra para.", "test")

    monkeypatch.setattr(free_ai, "chat", _fake_chat)

    post = await client_blog.generate_and_store(
        "c1", business_name="Sharma Solar", niche="solar", topic="Tips", keyword="solar nagpur"
    )
    assert post["title"] == "Solar Bachat Tips"
    assert post["slug"] and post["body"]

    posts = client_blog.list_posts("c1")
    assert len(posts) == 1 and posts[0]["slug"] == post["slug"]
    assert client_blog.get_post("c1", post["slug"]) is not None
    assert client_blog.get_post("c1", "nope") is None

    client = {"id": "c1", "business_name": "Sharma Solar", "brand": {"primary": "#0a0"}}
    idx = client_blog.render_index(client, "sharma-solar")
    assert "Sharma Solar" in idx and post["title"] in idx and "/b/sharma-solar/blog/" in idx
    pg = client_blog.render_post(client, "sharma-solar", post)
    assert post["title"] in pg and "Pehla para" in pg


@pytest.mark.asyncio
async def test_generate_never_empty_on_llm_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from app.marketing import client_blog
    from app.voice_agent import free_ai

    monkeypatch.setattr(client_blog, "_DIR", tmp_path / "blogs")

    async def _boom(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(free_ai, "chat", _boom)

    post = await client_blog.generate_and_store("c2", business_name="X", niche="general")
    assert post["title"] and post["body"]  # template fallback, never empty


def test_render_index_empty_safe() -> None:
    from app.marketing import client_blog

    html = client_blog.render_index({"id": "zzz", "business_name": "Empty Biz"}, "empty-biz")
    assert "Empty Biz" in html and "koi blog post nahi" in html  # graceful empty state
