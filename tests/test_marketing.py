"""
Tests: marketing module (Dhanda-style posts + GBP tips + content calendar
+ GBP audit + review replies + festivals + SVG posters + WhatsApp pack
+ competitor tips).
No network — free_ai.chat is monkeypatched to return ("","") so every path
exercises the TEMPLATE fallback (the never-empty guarantee).
"""
from datetime import datetime

import pytest

from app.marketing import (
    competitor,
    festivals,
    gbp_audit,
    post_generator,
    posters,
    review_replies,
    whatsapp_pack,
)


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


class TestGbpAudit:
    def test_questions_complete(self):
        qs = gbp_audit.AUDIT_QUESTIONS
        assert len(qs) >= 15
        ids = set()
        for q in qs:
            assert q["id"].strip() and q["id"] not in ids
            ids.add(q["id"])
            assert q["q"].strip()
            assert q["weight"] >= 1
            assert len(q["options"]) >= 2
            for opt in q["options"]:
                assert opt["label"].strip()
                assert 0.0 <= opt["score"] <= 1.0

    def test_scoring_perfect_zero_and_fixes(self):
        best = {}
        worst = {}
        for q in gbp_audit.AUDIT_QUESTIONS:
            scores = [o["score"] for o in q["options"]]
            best[q["id"]] = scores.index(max(scores))
            worst[q["id"]] = scores.index(min(scores))

        perfect = gbp_audit.score_audit(best)
        assert perfect["score"] >= 95
        assert perfect["grade"] == "A"
        assert perfect["impact"].strip()

        zero = gbp_audit.score_audit(worst)
        assert zero["score"] < 40
        assert zero["grade"] == "D"
        assert 1 <= len(zero["top_fixes"]) <= 5
        assert all(f.strip() for f in zero["top_fixes"])
        assert len(zero["breakdown"]) == len(gbp_audit.AUDIT_QUESTIONS)

        # Missing/garbage answers => worst-case, kabhi raise nahi
        messy = gbp_audit.score_audit({"claimed": 99, "bogus_id": 0, "photos": "x"})
        assert 0 <= messy["score"] <= 100


class TestReviewReplies:
    @pytest.mark.asyncio
    async def test_fallback_three_replies(self, no_llm):
        result = await review_replies.generate_replies(
            "Bahut accha kaam kiya, best service!", rating=5,
            business_name="Sharma Solar",
        )
        assert len(result["replies"]) == 3
        labels = [r["label"] for r in result["replies"]]
        assert labels == ["short", "medium", "detailed"]
        for r in result["replies"]:
            assert r["text"].strip()
            assert "Sharma Solar" in r["text"]
        assert result["sentiment"] == "positive"
        assert result["provider"] == "template"

        negative = await review_replies.generate_replies(
            "Worst experience, bahut kharab service", rating=1, business_name="Test Co"
        )
        assert len(negative["replies"]) == 3
        assert negative["sentiment"] == "negative"


class TestFestivals:
    def test_upcoming_non_empty_and_dates_parse(self):
        assert len(festivals.FESTIVALS_2026_27) >= 25
        for f in festivals.FESTIVALS_2026_27:
            # raises ValueError if malformed => test fail
            datetime.strptime(f["date"], "%Y-%m-%d")
            assert f["name"].strip()
            assert f["type"] in ("national", "hindu", "muslim", "sikh", "christian", "regional")
            assert f["marketing_angle"].strip()
        up = festivals.upcoming(days=600)
        assert len(up) > 0
        for f in up:
            assert f["days_away"] >= 0

    @pytest.mark.asyncio
    async def test_festival_posts_fallback(self, no_llm):
        result = await festivals.festival_posts("Gupta Sweets", "general", days=600)
        assert len(result["posts"]) >= 1
        for p in result["posts"]:
            assert p["festival"].strip()
            assert p["date"].strip()
            assert "Gupta Sweets" in p["caption"]
        assert result["provider"] == "template"


class TestPosters:
    def test_svg_escapes_inputs_and_six_templates(self):
        templates = posters.list_templates()
        assert len(templates) >= 6
        for t in templates:
            assert t["id"].strip() and t["name"].strip() and t["best_for"].strip()

        result = posters.generate_poster(
            "festival-glow", "R&D <Solar>", tagline="No.1 \"quality\"",
            offer="10% off", phone="9876543210", festival="Diwali",
        )
        svg = result["svg"]
        assert svg.startswith("<svg")
        assert "R&amp;D &lt;Solar&gt;" in svg  # XML-escaped
        assert "<Solar>" not in svg  # raw injection nahi
        assert "Diwali" in svg and "10% off" in svg and "9876543210" in svg

        # Unknown template => default, kabhi raise nahi
        fallback = posters.generate_poster("no-such-template", "Test Biz")
        assert fallback["template"] in posters.TEMPLATES
        assert "Test Biz" in fallback["svg"]


class TestWhatsAppPack:
    @pytest.mark.asyncio
    async def test_fallback_pack_non_empty(self, no_llm):
        result = await whatsapp_pack.broadcast_pack(
            "Sharma Solar", "solar_residential", occasion="Diwali", offer="10% off"
        )
        assert len(result["broadcast"]) == 2
        for msg in result["broadcast"]:
            assert msg.strip()
            assert len(msg) <= 300
        assert "Sharma Solar" in result["broadcast"][0]
        assert len(result["status_lines"]) == 3
        assert all(s.strip() for s in result["status_lines"])
        assert len(result["reply_templates"]) == 2
        assert all(r.strip() for r in result["reply_templates"])
        assert result["provider"] == "template"


class TestCompetitor:
    @pytest.mark.asyncio
    async def test_fallback_rule_based_non_empty(self, no_llm):
        result = await competitor.compare_tips(
            "Sharma Solar", "solar_residential",
            "Unke reviews zyada hain aur Instagram strong hai, par wo slow hain "
            "aur kaafi mehenga charge karte hain.",
        )
        assert 2 <= len(result["strengths_to_copy"]) <= 3
        assert 2 <= len(result["gaps_to_exploit"]) <= 3
        assert len(result["action_plan"]) == 3
        for section in ("strengths_to_copy", "gaps_to_exploit", "action_plan"):
            assert all(item.strip() for item in result[section])
        assert result["provider"] == "template"

        # Khali notes par bhi generic-but-useful output
        empty_notes = await competitor.compare_tips("Test Biz", "general", "")
        assert len(empty_notes["strengths_to_copy"]) >= 2
        assert len(empty_notes["gaps_to_exploit"]) >= 2
        assert len(empty_notes["action_plan"]) == 3
