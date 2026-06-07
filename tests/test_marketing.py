"""
Tests: marketing module (Dhanda-style posts + GBP tips + content calendar
+ GBP audit + review replies + festivals + SVG posters + WhatsApp pack
+ competitor tips + growth v3: review kit/QR, monthly report, reactivation,
drip, brand kit, CRM-lite).
No network — free_ai.chat is monkeypatched to return ("","") so every path
exercises the TEMPLATE fallback (the never-empty guarantee).
"""
from datetime import datetime

import pytest

from app.marketing import (
    brand_kit,
    competitor,
    crm_lite,
    drip,
    festivals,
    gbp_audit,
    monthly_report,
    post_generator,
    posters,
    reactivation,
    review_kit,
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


class TestReviewKit:
    def test_qr_svg_many_rects_and_deterministic(self):
        url = "https://www.google.com/maps/search/Sharma%20Solar%20Pune"
        svg = review_kit.qr_svg(url)
        assert svg.startswith("<svg")
        assert svg.count("<rect") > 100  # dark modules as rects
        assert svg == review_kit.qr_svg(url)  # deterministic
        # chhota input bhi chale, khali bhi kabhi raise nahi
        tiny = review_kit.qr_svg("hi")
        assert tiny.count("<rect") > 100
        assert review_kit.qr_svg("").startswith("<svg")

    def test_review_link_guidance(self):
        links = review_kit.review_link("Sharma Solar Pune")
        assert links["maps_search_url"].startswith(
            "https://www.google.com/maps/search/Sharma%20Solar%20Pune"
        )
        assert "writereview?placeid=" in links["direct_review_url_prefix"]
        assert links["direct_review_note"].strip()
        assert len(links["how_to_get_place_id"]) >= 2

    def test_review_ask_pack_non_empty(self):
        pack = review_kit.review_ask_pack("Sharma Solar")
        assert "Sharma Solar" in pack["wa_message"]
        assert pack["sms_line"].strip()
        card = pack["counter_card_svg"]
        assert card.startswith("<svg") and "{qr}" in card
        assert "Sharma Solar" in card
        # XML-escape check
        esc = review_kit.review_ask_pack("R&D <Solar>")
        assert "R&amp;D &lt;Solar&gt;" in esc["counter_card_svg"]
        assert "<Solar>" not in esc["counter_card_svg"]

    @pytest.mark.asyncio
    async def test_full_kit_embeds_qr(self, no_llm):
        kit = await review_kit.full_kit("Sharma Solar", "Sharma Solar Pune")
        assert "{qr}" not in kit["counter_card_svg"]
        assert kit["counter_card_svg"].count("<svg") >= 2  # nested QR svg
        assert "google.com/maps/search" in kit["wa_message"]
        assert "google.com/maps/search" in kit["sms_line"]
        assert kit["qr_svg"].count("<rect") > 100
        assert kit["provider"] == "template"


class TestMonthlyReport:
    @pytest.mark.asyncio
    async def test_report_html_contains_client_name(self, no_llm):
        result = await monthly_report.build_report(client_name="Sharma Solar")
        html = result["html"]
        assert "Sharma Solar" in html
        assert "<html" in html.lower() and "</html>" in html.lower()
        for section in ("Is Mahine Ka Kaam", "Numbers", "AI Suggestions",
                        "Next Month Plan"):
            assert section in html
        stats = result["stats"]
        assert isinstance(stats["total_actions"], int)
        assert set(stats["highlights"]) >= {"posts", "posters", "calls", "reviews"}
        assert 2 <= len(result["summary"]) <= 3
        assert all(s.strip() for s in result["summary"])
        assert len(result["plan"]) >= 3
        assert result["month"].strip() and result["month"] in html

    @pytest.mark.asyncio
    async def test_report_custom_month_label(self, no_llm):
        result = await monthly_report.build_report("Test Biz", month="May 2026")
        assert result["month"] == "May 2026"
        assert "May 2026" in result["html"]


class TestReactivation:
    @pytest.mark.asyncio
    async def test_two_customers_two_wa_links(self, no_llm):
        result = await reactivation.reactivation_campaign(
            "Sharma Solar", "solar_residential",
            customers=[
                {"name": "Ramesh", "phone": "+91 98765 43210"},
                {"name": "Suresh", "phone": "09812345678"},
            ],
            offer="20% off",
        )
        msgs = result["messages"]
        assert len(msgs) == 2
        for m in msgs:
            assert m["wa_link"].startswith("https://wa.me/91")
            assert m["name"] in m["text"]
            assert "Sharma Solar" in m["text"]
        # phone normalization (+91 / 0 prefix -> 10 digit)
        assert msgs[0]["phone"] == "9876543210"
        assert msgs[1]["phone"] == "9812345678"
        assert "20% off" in msgs[0]["text"]
        assert len(result["tips"]) == 2
        assert result["provider"] == "template"

    @pytest.mark.asyncio
    async def test_bad_phone_and_cap(self, no_llm):
        rows = [{"name": f"C{i}", "phone": "98765432" + f"{i:02d}"} for i in range(60)]
        rows[0]["phone"] = "12345"  # unusable
        result = await reactivation.reactivation_campaign("Biz", "general", rows)
        assert result["count"] == 50  # cap
        assert result["messages"][0]["wa_link"] == ""  # bad phone => no link
        assert result["messages"][1]["wa_link"].startswith("https://wa.me/91")


class TestDrip:
    @pytest.mark.asyncio
    async def test_fallback_four_steps_each_lead_type(self, no_llm):
        for lt in ("new_inquiry", "no_reply", "post_purchase"):
            result = await drip.drip_sequence("Sharma Solar", "coaching", lead_type=lt)
            steps = result["steps"]
            assert len(steps) == 4
            assert [s["day"] for s in steps] == [0, 2, 5, 9]
            for s in steps:
                assert s["goal"].strip() and s["message"].strip()
            assert "Sharma Solar" in steps[0]["message"]
            assert result["lead_type"] == lt
            assert result["provider"] == "template"
        # unknown lead_type => default new_inquiry, kabhi raise nahi
        weird = await drip.drip_sequence("X", "general", lead_type="bogus")
        assert weird["lead_type"] == "new_inquiry"
        assert len(weird["steps"]) == 4


class TestBrandKit:
    def test_save_get_roundtrip_and_merge(self, tmp_path, monkeypatch):
        monkeypatch.setattr(brand_kit, "_BRAND_DIR", str(tmp_path))
        saved = brand_kit.save_brand("client-42", {
            "business_name": "Sharma Solar",
            "tagline": "Bijli bachao",
            "phone": "9876543210",
            "colors": {"primary": "#112233", "accent": "#abcdef"},
            "tone": "friendly",
            "logo_text": "SS",
        })
        assert saved["colors"]["primary"] == "#112233"
        got = brand_kit.get_brand("client-42")
        assert got is not None
        assert got["business_name"] == "Sharma Solar"
        assert got["colors"]["accent"] == "#abcdef"
        assert brand_kit.get_brand("no-such-client") is None
        # poster-args merge: missing fields fill, brand colors attach
        merged = brand_kit.apply_brand_to_poster_args(
            "client-42", {"template_id": "clean-pro", "tagline": "Custom line"}
        )
        assert merged["business_name"] == "Sharma Solar"
        assert merged["tagline"] == "Custom line"  # explicit value jeet-ta hai
        assert merged["brand_primary"] == "#112233"
        assert merged["brand_accent"] == "#abcdef"
        # invalid color => "" (injection-safe), path-traversal id safe ho jaata
        bad = brand_kit.save_brand("../../evil", {"colors": {"primary": 'red"><x>'}})
        assert bad["colors"]["primary"] == ""
        assert "/" not in bad["client_id"] and ".." not in bad["client_id"]

    def test_brand_colors_apply_in_poster(self):
        branded = posters.generate_poster(
            "clean-pro", "Test Biz", brand_primary="#112233"
        )
        assert "#112233" in branded["svg"]
        assert "#0b5fff" not in branded["svg"]
        # default unchanged jab brand params nahi
        default = posters.generate_poster("clean-pro", "Test Biz")
        assert "#0b5fff" in default["svg"]
        # invalid color ignore (no injection)
        inj = posters.generate_poster(
            "clean-pro", "Test Biz", brand_primary='"><script>alert(1)</script>'
        )
        assert "<script>" not in inj["svg"]
        assert "#0b5fff" in inj["svg"]
        # accent slot bhi chale
        acc = posters.generate_poster(
            "generic-sale", "Test Biz", brand_accent="#ff0000"
        )
        assert "#ff0000" in acc["svg"]


class TestCrmLite:
    @pytest.mark.asyncio
    async def test_add_list_dedupe_and_wishes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(crm_lite, "_CRM_DIR", str(tmp_path))
        today = crm_lite._today_mmdd()
        res = crm_lite.add_customers("client-7", [
            {"name": "Ramesh", "phone": "9876543210",
             "birthday": f"1990-{today}", "tags": ["vip"]},
            {"name": "Suresh", "phone": "+91 98123 45678", "anniversary": today},
            {"name": "Dup", "phone": "98765 43210"},  # same as Ramesh => skip
        ])
        assert res["added"] == 2 and res["skipped"] == 1 and res["total"] == 2
        # dedupe across calls bhi
        res2 = crm_lite.add_customers("client-7", [{"name": "R2", "phone": "9876543210"}])
        assert res2["added"] == 0 and res2["skipped"] == 1 and res2["total"] == 2
        # list + tag filter
        rows = crm_lite.list_customers("client-7")
        assert len(rows) == 2
        vip = crm_lite.list_customers("client-7", tag="vip")
        assert len(vip) == 1 and vip[0]["name"] == "Ramesh"
        # aaj ke wishes (birthday + anniversary dono)
        wishes = await crm_lite.todays_wishes("client-7", "Sharma Solar")
        assert wishes["date"] == today
        assert wishes["count"] == 2
        occasions = {w["occasion"] for w in wishes["wishes"]}
        assert occasions == {"birthday", "anniversary"}
        for w in wishes["wishes"]:
            assert w["wa_link"].startswith("https://wa.me/91")
            assert w["name"] in w["message"]
            assert "Sharma Solar" in w["message"]
        # unknown client => empty store, kabhi raise nahi
        empty = await crm_lite.todays_wishes("ghost-client", "X")
        assert empty["count"] == 0 and empty["wishes"] == []
