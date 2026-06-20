"""Tests — social page kit generator (LLM-down fallback me bhi complete)."""

from __future__ import annotations

import asyncio


def test_page_kit_complete_without_llm(monkeypatch):
    from app.marketing import social_page_kit as spk

    async def _no_llm(*a, **k):
        return None

    monkeypatch.setattr(spk, "_llm_bios", _no_llm)
    kit = asyncio.run(
        spk.build_page_kit(
            "Sharma Solar",
            niche="solar_residential",
            city="Pune",
            phone="98XXXXXX07",
            posts_count=3,
        )
    )
    pages = kit["pages"]
    for platform in ("facebook", "instagram", "linkedin", "x_twitter", "gbp", "whatsapp_business"):
        assert isinstance(pages.get(platform), dict) and pages[platform], platform
    assert pages["facebook"]["page_name"] and pages["facebook"]["about"]
    assert len(pages["instagram"]["bio"]) <= 160
    assert pages["gbp"]["description"]
    assert len(kit["first_posts"]) == 3 and all(p["caption"] for p in kit["first_posts"])
    assert kit["cover_image_prompt"] and "Sharma Solar" in kit["cover_image_prompt"]


def test_handle_slug():
    from app.marketing.social_page_kit import _slug_handle

    assert _slug_handle("Sharma Solar & Co.") == "sharmasolarco"
    assert _slug_handle("") == "business"
