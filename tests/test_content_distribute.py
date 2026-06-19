"""Tests — content_distribute (SP-D auto-publish to legal channels).
Project convention: sync + asyncio.run, monkeypatch deps, NO DB/network/LLM.
Telegram send + indexnow httpx are monkeypatched (pure-python).
"""

from __future__ import annotations

import asyncio


# --------------------------- flag gate (inert default) --------------------------- #
def test_autopublish_disabled_by_default(monkeypatch):
    from app.marketing import content_distribute

    monkeypatch.delenv("CONTENT_AUTOPUBLISH", raising=False)
    assert content_distribute.autopublish_enabled() is False
    # inert run -> ran False, never raises
    out = asyncio.run(content_distribute.publish_ready_to_telegram())
    assert out["ran"] is False and "off" in out["reason"].lower()


def test_autopublish_needs_token(monkeypatch):
    from app.marketing import content_distribute, telegram_publish

    monkeypatch.setenv("CONTENT_AUTOPUBLISH", "1")
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    # token unset -> telegram_publish.enabled() False -> gate False
    assert telegram_publish.enabled() is False
    assert content_distribute.autopublish_enabled() is False


# --------------------------- chat id resolution --------------------------- #
def test_self_chat_id_from_env(monkeypatch):
    from app.marketing import content_distribute

    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "@leadgenai")
    assert content_distribute._self_chat_id() == "@leadgenai"


def test_no_chat_id_is_inert(monkeypatch):
    from app.marketing import content_distribute

    monkeypatch.setenv("CONTENT_AUTOPUBLISH", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")  # gate passes
    monkeypatch.delenv("TELEGRAM_ADMIN_CHAT_ID", raising=False)
    # self client lookup -> no telegram_chat_id -> inert
    import app.marketing.clients_store as cs

    monkeypatch.setattr(cs, "get_client", lambda _id: {}, raising=False)
    out = asyncio.run(content_distribute.publish_ready_to_telegram())
    assert out["ran"] is False and "unset" in out["reason"].lower()


# --------------------------- item text builder --------------------------- #
def test_item_text_caption_and_hashtags():
    from app.marketing import content_distribute

    txt = content_distribute._item_text(
        {"caption": "Diwali offer!", "hashtags": ["#sale", "#local"]}
    )
    assert "Diwali offer!" in txt and "#sale" in txt and "#local" in txt
    # title fallback when no caption
    assert content_distribute._item_text({"title": "Festive post"}) == "Festive post"
    assert content_distribute._item_text({}) == ""
    assert content_distribute._item_text("not a dict") == ""


# --------------------------- full publish loop (monkeypatched) --------------------------- #
def test_publish_loop_posts_and_marks(monkeypatch):
    from app.marketing import auto_content, content_distribute, telegram_publish

    monkeypatch.setenv("CONTENT_AUTOPUBLISH", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "@leadgenai")

    ready_items = [
        {"id": "a1", "caption": "Post one", "status": "approved"},
        {"id": "a2", "caption": "Post two", "status": "ready"},
    ]

    def fake_list_queue(cid, status=None, limit=60):
        if status == "approved":
            return [ready_items[0]]
        if status == "ready":
            return [ready_items[1]]
        return []

    marked: list[tuple] = []

    def fake_mark(cid, item_id, st):
        marked.append((item_id, st))
        return True

    sent_texts: list[str] = []

    async def fake_send(chat_id, text, image_url=""):
        sent_texts.append(text)
        return {"sent": True}

    monkeypatch.setattr(auto_content, "list_queue", fake_list_queue)
    monkeypatch.setattr(auto_content, "mark_item", fake_mark)
    monkeypatch.setattr(telegram_publish, "send_post", fake_send)

    out = asyncio.run(content_distribute.publish_ready_to_telegram())
    assert out["ran"] is True
    assert out["sent"] == 2 and out["failed"] == 0
    assert any("Post one" in t for t in sent_texts)
    assert ("a1", "posted") in marked and ("a2", "posted") in marked


def test_publish_loop_failure_not_marked(monkeypatch):
    from app.marketing import auto_content, content_distribute, telegram_publish

    monkeypatch.setenv("CONTENT_AUTOPUBLISH", "1")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake-token")
    monkeypatch.setenv("TELEGRAM_ADMIN_CHAT_ID", "@leadgenai")

    def fake_list_queue(cid, status=None, limit=60):
        if status == "approved":
            return [{"id": "x1", "caption": "Will fail", "status": "approved"}]
        return []

    marked: list[tuple] = []

    async def fake_send(chat_id, text, image_url=""):
        return {"sent": False, "reason": "boom"}

    monkeypatch.setattr(auto_content, "list_queue", fake_list_queue)
    monkeypatch.setattr(auto_content, "mark_item", lambda *a: marked.append(a))
    monkeypatch.setattr(telegram_publish, "send_post", fake_send)

    out = asyncio.run(content_distribute.publish_ready_to_telegram())
    assert out["ran"] is True and out["failed"] == 1 and out["sent"] == 0
    assert marked == []  # failed item NOT marked posted


# --------------------------- indexnow wrappers (monkeypatched httpx) --------------------------- #
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
