"""
Tests: marketing module (Dhanda-style posts + GBP tips + content calendar).
No network — free_ai.chat is monkeypatched to return ("","") so every path
exercises the TEMPLATE fallback (the never-empty guarantee).
"""
import pytest

from app.marketing import post_generator


@pytest.fixture
def no_llm(monkeypatch):
    """free_ai.chat ko hamesha ("","") return karwao — template path force."""
    async def _empty(*args, **kwargs):
        return "", ""

    if post_generator.free_ai is not None:
        monkeypatch.setattr(post_generator.free_ai, "chat", _empty)


class TestGeneratePost:
    @pytest.mark.asyncio
    async def test_template_fallback_never_empty(self, no_llm):
        result = await post_generator.generate_post(
            "Sharma Solar", niche="solar_residential", offer="10% off this week"
        )
        assert result["caption"].strip()
        assert "Sharma Solar" in result["post_text"]
        assert "10% off this week" in result["caption"]
        assert isinstance(result["hashtags"], list) and len(result["hashtags"]) >= 8
        assert result["image_idea"].strip()
        assert result["provider"] == "template"
        # post_text = caption + hashtags, ready-to-copy
        for tag in result["hashtags"]:
            assert tag in result["post_text"]

    @pytest.mark.asyncio
    async def test_hashtags_non_empty_even_for_unknown_niche(self, no_llm):
        result = await post_generator.generate_post(
            "Test Biz", niche="totally_unknown_niche", occasion="Diwali"
        )
        assert len(result["hashtags"]) >= 8
        assert all(t.startswith("#") for t in result["hashtags"])
        # dedupe check
        lowered = [t.lower() for t in result["hashtags"]]
        assert len(lowered) == len(set(lowered))
        # festival template used the occasion
        assert "Diwali" in result["caption"]


class TestGbpTips:
    def test_min_10_tips_with_required_keys(self):
        tips = post_generator.gbp_tips("real_estate")
        assert len(tips) >= 10
        for t in tips:
            assert t["tip"].strip()
            assert t["why"].strip()
            assert t["impact"] in ("high", "med")

    def test_unknown_niche_still_works(self):
        tips = post_generator.gbp_tips("ev_charging_custom")
        assert len(tips) >= 10


class TestContentCalendar:
    @pytest.mark.asyncio
    async def test_fallback_length_equals_days(self, no_llm):
        cal = await post_generator.content_calendar("Test Biz", "coaching", days=7)
        assert len(cal) == 7
        for entry in cal:
            assert entry["day"].strip()
            assert entry["theme"].strip()
            assert entry["caption_short"].strip()
            assert "Test Biz" in entry["caption_short"]

    @pytest.mark.asyncio
    async def test_fallback_custom_days(self, no_llm):
        cal = await post_generator.content_calendar("Test Biz", "general", days=10)
        assert len(cal) == 10
