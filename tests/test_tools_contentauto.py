"""Tests — content/intel tools batch (repurpose, brand_pulse, month_planner,
team_report, webpush + contentauto router import). Pure-python — NO network,
NO LLM (free_ai + httpx + generators sab mocked/fallback paths)."""

from __future__ import annotations

import asyncio
import os
from datetime import date, timedelta

# ---------------------------------------------------------------------------- #
# 1) repurpose — compose 7 formats, partial-fail OK
# ---------------------------------------------------------------------------- #


def test_repurpose_composes_all_formats(monkeypatch):
    from app.marketing import carousel, gbp_text, hashtags, post_generator, reels, repurpose
    from app.voice_agent import free_ai

    async def fake_post(business_name, niche="general", occasion="", offer="", language="hinglish"):
        return {"caption": "cap", "hashtags": ["#x"], "post_text": "cap #x", "provider": "mock"}

    async def fake_carousel(business_name, niche="general", topic="", slides=4):
        return {"slides": [{"title": "s1"}], "caption": "c"}

    async def fake_reels(business_name, niche, topic="", n=3):
        return {"scripts": [{"hook": "h"}], "count": 1}

    async def fake_gbp(business_name, niche, city="", services=None):
        return {"posts": ["gbp post 1", "p2", "p3"], "tip": "t"}

    async def fake_tags(niche, city="", count=15):
        return {"hashtags": ["#a", "#b"], "best_times": []}

    async def fake_chat(system, messages, **kw):
        return ("WA: Status line ✨\nEMAIL: Email para yahan.", "mock")

    monkeypatch.setattr(post_generator, "generate_post", fake_post)
    monkeypatch.setattr(carousel, "generate_carousel", fake_carousel)
    monkeypatch.setattr(reels, "reels_scripts", fake_reels)
    monkeypatch.setattr(gbp_text, "gbp_texts", fake_gbp)
    monkeypatch.setattr(hashtags, "research", fake_tags)
    monkeypatch.setattr(free_ai, "chat", fake_chat)

    out = asyncio.run(
        repurpose.repurpose("Diwali offer", niche="solar_residential", business_name="Sharma Solar")
    )
    assert out["ok"] is True
    f = out["formats"]
    assert set(f) == {
        "post",
        "carousel",
        "reel",
        "gbp_post",
        "whatsapp_status",
        "email_paragraph",
        "hashtags",
    }
    assert out["formats_ok"] == 7
    assert f["gbp_post"]["text"] == "gbp post 1"
    assert "Status line" in f["whatsapp_status"]
    assert "Email para" in f["email_paragraph"]
    assert out["source"]["type"] == "topic"


def test_repurpose_partial_fail_ok(monkeypatch):
    from app.marketing import carousel, gbp_text, hashtags, post_generator, reels, repurpose
    from app.voice_agent import free_ai

    async def boom(*a, **k):
        raise RuntimeError("carousel down")

    async def fake_post(*a, **k):
        return {"caption": "ok"}

    async def fake_reels(*a, **k):
        return {"scripts": []}

    async def fake_gbp(*a, **k):
        return {"posts": []}

    async def fake_tags(*a, **k):
        return {"hashtags": []}

    async def fake_chat(*a, **k):
        return ("", "")  # LLM dead → wa/email template fallback

    monkeypatch.setattr(carousel, "generate_carousel", boom)
    monkeypatch.setattr(post_generator, "generate_post", fake_post)
    monkeypatch.setattr(reels, "reels_scripts", fake_reels)
    monkeypatch.setattr(gbp_text, "gbp_texts", fake_gbp)
    monkeypatch.setattr(hashtags, "research", fake_tags)
    monkeypatch.setattr(free_ai, "chat", fake_chat)

    out = asyncio.run(repurpose.repurpose("topic", niche="gym", business_name="FitZone"))
    assert out["ok"] is True  # baaki formats bane
    assert out["formats"]["carousel"].get("error")
    assert "FitZone" in out["formats"]["whatsapp_status"]  # template fallback
    assert out["formats_ok"] == 6


def test_repurpose_url_detect():
    from app.marketing.repurpose import _is_url

    assert _is_url("https://leadsgenai.in/blog/x")
    assert _is_url("http://x.in")
    assert not _is_url("diwali offer post")


# ---------------------------------------------------------------------------- #
# 2) brand_pulse — parsers, scan (mocked fetch), cache, gating
# ---------------------------------------------------------------------------- #

_RSS = (
    "<rss><channel>"
    "<item><title><![CDATA[Sharma Solar best service in Pune]]></title>"
    "<link>https://news.example/a</link><description>great work accha</description></item>"
    "<item><title>Sharma Solar worst delay</title><link>https://news.example/b</link>"
    "<description>bekaar slow service</description></item>"
    "</channel></rss>"
)


def test_pulse_parsers():
    from app.platform import brand_pulse

    news = brand_pulse.parse_news_rss(_RSS)
    assert len(news) == 2 and news[0]["source"] == "google_news"
    assert news[0]["url"] == "https://news.example/a"

    reddit = brand_pulse.parse_reddit_json(
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Review of Sharma Solar",
                            "permalink": "/r/pune/1",
                            "selftext": "good",
                        }
                    }
                ]
            }
        }
    )
    assert len(reddit) == 1 and reddit[0]["url"].startswith("https://www.reddit.com/r/")
    assert brand_pulse.parse_reddit_json({}) == []  # defensive


def test_pulse_scan_sentiment_and_drafts(tmp_path, monkeypatch):
    from app.platform import brand_pulse

    monkeypatch.setattr(brand_pulse, "_CACHE_FILE", str(tmp_path / "cache.jsonl"))

    async def fake_news(q):
        return brand_pulse.parse_news_rss(_RSS)

    async def fake_reddit(q):
        return []

    monkeypatch.setattr(brand_pulse, "_fetch_google_news", fake_news)
    monkeypatch.setattr(brand_pulse, "_fetch_reddit", fake_reddit)

    d = asyncio.run(brand_pulse.scan("Sharma Solar", city="Pune"))
    assert d["ok"] is True and len(d["mentions"]) == 2
    assert d["breakdown"].get("negative", 0) >= 1
    assert len(d["reply_drafts"]) == d["breakdown"]["negative"]
    assert "Sharma Solar" in d["reply_drafts"][0]["draft"]
    assert d["cached"] is False

    # 2nd scan → cache hit (fetchers na bhi chalein to)
    async def boom(q):
        raise RuntimeError("no net")

    monkeypatch.setattr(brand_pulse, "_fetch_google_news", boom)
    d2 = asyncio.run(brand_pulse.scan("Sharma Solar", city="Pune"))
    assert d2["cached"] is True and len(d2["mentions"]) == 2


def test_pulse_weekly_gated_off(monkeypatch):
    from app.platform import brand_pulse

    monkeypatch.delenv("BRAND_PULSE", raising=False)
    out = asyncio.run(brand_pulse.run_weekly_if_enabled())
    assert out["ok"] is False and out["reason"] == "flag_off"


def test_pulse_scan_requires_name():
    from app.platform import brand_pulse

    out = asyncio.run(brand_pulse.scan(""))
    assert out["ok"] is False


# ---------------------------------------------------------------------------- #
# 3) month_planner — dry-run plan + commit dedupe
# ---------------------------------------------------------------------------- #


def test_month_plan_dry_run(monkeypatch):
    from app.marketing import month_planner

    out = month_planner.plan_month(niche="solar_residential", business_name="Sharma Solar", days=30)
    assert out["ok"] is True and len(out["plan"]) == 30
    assert out["dry_run"] is True and out["committed"] == 0
    # Friday = offer day
    fridays = [
        p
        for p in out["plan"]
        if date.fromisoformat(p["date"]).weekday() == 4 and not p["is_festival"]
    ]
    assert all(p["theme"] == "Offer / Deal" and p["offer"] for p in fridays)
    # future dates only
    assert min(p["date"] for p in out["plan"]) > date.today().isoformat()


def test_month_plan_festival_day(monkeypatch):
    from app.marketing import festivals, month_planner

    fest_date = (date.today() + timedelta(days=5)).isoformat()
    monkeypatch.setattr(
        festivals,
        "upcoming",
        lambda days=45: [{"date": fest_date, "name": "Test Parv", "marketing_angle": "angle"}],
    )
    out = month_planner.plan_month(niche="gym", business_name="FitZone", days=15)
    hit = [p for p in out["plan"] if p["date"] == fest_date]
    assert hit and hit[0]["is_festival"] and hit[0]["occasion"] == "Test Parv"


def test_month_plan_commit_dedupes(tmp_path, monkeypatch):
    from app.marketing import content_schedule, month_planner

    monkeypatch.setattr(content_schedule, "_FILE", str(tmp_path / "sched.jsonl"))
    out1 = month_planner.plan_month(
        niche="gym", business_name="FitZone", days=10, commit=True, dry_run=False
    )
    assert out1["committed"] == 10 and out1["skipped"] == 0
    assert len(content_schedule.list_scheduled()) == 10
    # repeat commit → sab dup-skip
    out2 = month_planner.plan_month(
        niche="gym", business_name="FitZone", days=10, commit=True, dry_run=False
    )
    assert out2["committed"] == 0 and out2["skipped"] == 10
    assert len(content_schedule.list_scheduled()) == 10


# ---------------------------------------------------------------------------- #
# 4) team_report — narrative (mocked events + LLM-down fallback) + gating
# ---------------------------------------------------------------------------- #


def _fake_events():
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).isoformat()
    mk = lambda action: {"action": action, "at": now, "member": "isha", "detail": ""}  # noqa: E731
    return [
        mk("content_generated"),
        mk("post_created"),
        mk("lead_scored"),
        mk("review_drafted"),
        mk("email_outreach"),
    ]


def test_team_report_narrative(monkeypatch):
    from app.platform import team, team_report
    from app.voice_agent import free_ai

    monkeypatch.setattr(team, "recent_events", lambda limit=300, member=None: _fake_events())

    async def dead_llm(*a, **k):
        raise RuntimeError("llm down")

    monkeypatch.setattr(free_ai, "chat", dead_llm)
    out = asyncio.run(team_report.weekly_narrative())
    assert out["ok"] is True
    assert out["counts"]["content"] == 2 and out["counts"]["leads"] == 1
    assert "<html" in out["html"] and "AI Team" in out["html"]
    assert any("content" in ln or "Isha" in ln for ln in out["lines"])


def test_team_report_empty_events_never_empty(monkeypatch):
    from app.platform import team, team_report
    from app.voice_agent import free_ai

    monkeypatch.setattr(team, "recent_events", lambda limit=300, member=None: [])

    async def dead_llm(*a, **k):
        return ("", "")

    monkeypatch.setattr(free_ai, "chat", dead_llm)
    out = asyncio.run(team_report.weekly_narrative())
    assert out["ok"] is True and out["lines"]  # standby line


def test_team_report_gated_off(monkeypatch):
    from app.platform import team_report

    monkeypatch.delenv("TEAM_REPORT", raising=False)
    out = asyncio.run(team_report.run_weekly_if_enabled())
    assert out["ok"] is False and out["reason"] == "flag_off"


# ---------------------------------------------------------------------------- #
# 5) webpush — inert without keys, sub dedupe, draft-only send, JS snippet
# ---------------------------------------------------------------------------- #


def test_webpush_inert_without_keys(tmp_path, monkeypatch):
    from app.platform import webpush

    monkeypatch.delenv("VAPID_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("VAPID_PUBLIC_KEY", raising=False)
    av = webpush.available()
    assert av["ok"] is False and av["reason"] == "pywebpush_or_keys_missing"

    monkeypatch.setattr(webpush, "_DRAFTS_FILE", str(tmp_path / "drafts.jsonl"))
    res = webpush.send_push("client1", "Title", "Body")
    assert res["ok"] is False and res["draft_recorded"] is True
    assert os.path.exists(str(tmp_path / "drafts.jsonl"))


def test_webpush_subscription_dedupe(tmp_path, monkeypatch):
    from app.platform import webpush

    monkeypatch.setattr(webpush, "_SUBS_FILE", str(tmp_path / "subs.jsonl"))
    sub = {"endpoint": "https://fcm.googleapis.com/x/abc", "keys": {"p256dh": "k1", "auth": "a1"}}
    r1 = webpush.save_subscription("client1", sub)
    assert r1["ok"] is True and r1["saved"] is True
    r2 = webpush.save_subscription("client1", sub)
    assert r2["ok"] is True and r2["saved"] is False  # dedupe by endpoint
    assert len(webpush.list_subs("client1")) == 1
    # invalid sub
    bad = webpush.save_subscription("c", {"endpoint": "notaurl"})
    assert bad["ok"] is False


def test_webpush_status_and_js(tmp_path, monkeypatch):
    from app.platform import webpush

    monkeypatch.setattr(webpush, "_SUBS_FILE", str(tmp_path / "subs.jsonl"))
    monkeypatch.setattr(webpush, "_DRAFTS_FILE", str(tmp_path / "drafts.jsonl"))
    monkeypatch.setenv("VAPID_PUBLIC_KEY", "BTestPublicKey123")
    st = webpush.status()
    assert st["subscriptions"] == 0 and st["vapid_public_set"] is True

    js = webpush.subscribe_js("client1")
    assert "client1" in js and "/api/contentauto/push/subscribe" in js
    assert "BTestPublicKey123" in js and "pushManager.subscribe" in js


# ---------------------------------------------------------------------------- #
# 6) router import-safe (mount snippet ka precondition)
# ---------------------------------------------------------------------------- #


def test_contentauto_router_imports():
    from app.api.contentauto import router

    paths = {r.path for r in router.routes}
    assert "/contentauto/repurpose" in paths
    assert "/contentauto/pulse" in paths
    assert "/contentauto/month-plan" in paths
    assert "/contentauto/team-report" in paths
    assert "/contentauto/push/subscribe" in paths
    assert "/contentauto/push/send" in paths
    assert len(paths) >= 10
