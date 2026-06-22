"""Tests — content_distribute (IndexNow SEO ping wrappers).
Project convention: sync + asyncio.run, monkeypatch deps, NO DB/network/LLM.
indexnow.submit_urls is monkeypatched (pure-python).
"""

from __future__ import annotations

import asyncio


# --------------------------- indexnow wrappers (monkeypatched) --------------------------- #
def test_submit_indexnow_empty():
    from app.marketing import content_distribute

    out = asyncio.run(content_distribute.submit_indexnow([]))
    assert out["ok"] is False


def test_submit_indexnow_reuses_indexnow(monkeypatch):
    from app.marketing import content_distribute, indexnow

    async def fake_submit(urls):
        return {"ok": True, "submitted": len(urls)}

    monkeypatch.setattr(indexnow, "submit_urls", fake_submit)
    out = asyncio.run(content_distribute.submit_indexnow(["/blog/a", "/blog/b"]))
    assert out["ok"] is True and out["submitted"] == 2


def test_submit_new_blog_urls(monkeypatch):
    from app.marketing import content_distribute, indexnow, seo_blog

    monkeypatch.setattr(
        seo_blog, "list_articles", lambda limit=50: [{"slug": "x"}, {"slug": "y"}, {}]
    )
    captured: dict = {}

    async def fake_submit(urls):
        captured["urls"] = urls
        return {"ok": True, "submitted": len(urls)}

    monkeypatch.setattr(indexnow, "submit_urls", fake_submit)
    out = asyncio.run(content_distribute.submit_new_blog_urls())
    assert out["ok"] is True and out["submitted"] == 2
    assert captured["urls"] == ["/blog/x", "/blog/y"]
