"""Tests — marketing AI upgrades (content_feedback, trends, kb_personalize,
reel_video). No network, no LLM — sab defensive paths."""

from __future__ import annotations

import asyncio

from app.marketing import content_feedback, kb_personalize, reel_video, trends


def test_feedback_record_and_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(content_feedback, "_PATH", str(tmp_path / "fb.jsonl"))
    content_feedback.record_feedback("diwali-offer", True, fmt="post", niche="solar")
    content_feedback.record_feedback("diwali-offer", False, fmt="post", niche="solar")
    content_feedback.record_feedback("tip", True, fmt="reel", niche="solar")
    st = content_feedback.theme_stats("solar")
    assert st["total_feedback"] == 3
    top = st["themes"][0]
    assert top["theme"] == "tip" and top["score"] > 0.6  # (1+1)/(1+2)
    assert "tip" in content_feedback.best_themes("solar")


def test_tracked_link_adds_utm(monkeypatch):
    monkeypatch.setattr(content_feedback, "shorten", lambda u: u)
    out = content_feedback.tracked_link("https://leadsgenai.in/audit", "quora", "june")
    assert "utm_source=quora" in out and "utm_campaign=june" in out
    assert content_feedback.tracked_link("", "x") == ""


def test_shorten_never_raises(monkeypatch):
    import httpx

    def boom(*a, **k):
        raise httpx.ConnectError("no net")

    monkeypatch.setattr(httpx, "get", boom)
    assert content_feedback.shorten("https://x.in/page") == "https://x.in/page"


def test_trends_rss_parse_and_fallback(monkeypatch):
    xml = "<rss><item><title><![CDATA[IPL Final]]></title></item><item><title>Monsoon</title></item></rss>"
    assert trends.parse_rss_titles(xml) == ["IPL Final", "Monsoon"]
    monkeypatch.setattr(trends, "trending", lambda *a, **k: [])
    out = asyncio.run(trends.trend_angles("solar"))
    assert out["provider"] == "fallback" and len(out["angles"]) == 3


def test_kb_context_defensive():
    # bina KB seed / bad id — empty list, no raise
    assert kb_personalize.client_context("") == []
    assert isinstance(kb_personalize.client_context("nonexistent-xyz"), list)


def test_reel_available_and_missing_dep(monkeypatch):
    av = reel_video.available()
    assert set(av) == {"ffmpeg", "pillow", "edge_tts", "ok"}
    import shutil

    monkeypatch.setattr(shutil, "which", lambda *_: None)
    res = asyncio.run(reel_video.build_reel("Test Biz", "solar"))
    if not reel_video.available()["ok"]:
        assert "error" in res


def test_reel_default_slides():
    s = reel_video._default_slides("Sharma Solar", "solar", "")
    assert len(s) == 3 and "Sharma Solar" in s[0]


def test_ai_image_new_api_key_safety(monkeypatch):
    from app.marketing import ai_image

    # no key → direct URL, no key leak
    monkeypatch.delenv("POLLINATIONS_API_KEY", raising=False)
    monkeypatch.delenv("POLLINATIONS_TOKEN", raising=False)
    u = ai_image.image_url("diwali poster")
    assert u.startswith("https://gen.pollinations.ai/image/") and "key=" not in u
    # pk_ (publishable, client-safe) → embedded
    monkeypatch.setenv("POLLINATIONS_API_KEY", "pk_test123")
    assert "key=pk_test123" in ai_image.image_url("x")
    assert "key=pk_test123" in ai_image.video_url("x")
    # sk_ (secret) → NEVER in URL; marketing flows use proxy path
    monkeypatch.setenv("POLLINATIONS_API_KEY", "sk_secret")
    assert "sk_secret" not in ai_image.image_url("x")
    assert ai_image.logo_url("Biz").startswith("/api/marketing/ai-image-proxy?")
    assert ai_image.proxy_path("p").startswith("/api/marketing/ai-image-proxy?prompt=p")
