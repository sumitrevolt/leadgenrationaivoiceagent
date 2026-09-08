"""Tests — bulk competitor-parity batch (carousel, meme, deliverability,
booking reminders, review monitor, outbound webhooks, website auditor, multilang).
Sync + asyncio.run, tmp stores, no network (LLM calls fallback pe girte).
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from tests._api_helpers import iter_mounted_routes


def test_carousel_fallback_slides():
    from app.marketing import carousel

    out = asyncio.run(carousel.generate_carousel("Sharma Solar", "solar", "subsidy", 4))
    assert 3 <= len(out["slides"]) <= 5
    for s in out["slides"]:
        assert s["title"] and s["svg"].startswith("<svg")
    assert "caption" in out


def test_meme_generation():
    from app.marketing import meme_gen

    out = asyncio.run(meme_gen.generate_meme("Test Gym", "gym_fitness"))
    assert out["top"] and out["bottom"]
    assert out["svg"].startswith("<svg")
    assert out["hashtags"]


def test_deliverability_pure_parts(monkeypatch):
    from app.platform import deliverability_monitor as dm

    # records check kabhi raise nahi (DNS fail = False flags)
    rec = dm.check_records("nonexistent-domain-xyz-123.invalid")
    assert rec["spf_ok"] is False and rec["dmarc_ok"] is False
    bl = dm.check_blacklists("not-an-ip")
    assert bl["listed_on"] == []
    # gate off
    monkeypatch.delenv("DELIVERABILITY_MONITOR", raising=False)
    assert dm._enabled_alerts() is False


def test_booking_reminders_record_and_gate(tmp_path, monkeypatch):
    from app.platform import booking_reminders as br

    monkeypatch.setattr(br, "_STORE", str(tmp_path / "b.jsonl"))
    monkeypatch.setattr(br, "_RUNS", str(tmp_path / "br.jsonl"))
    monkeypatch.delenv("BOOKING_REMINDERS", raising=False)

    slot = (datetime.now(timezone.utc) + timedelta(hours=20)).isoformat()
    r1 = br.record_booking(slot, "Ravi", "9876543210", "ravi@x.co")
    assert r1.get("id")
    r2 = br.record_booking(slot, "Ravi dup", "9876543210")
    assert r2["id"] == r1["id"]  # dedupe
    msg = br.build_reminder(r1)
    assert "appointment" in msg["subject"].lower() or "reminder" in msg["subject"].lower()
    assert asyncio.run(br.run_due()) == {"enabled": False}  # gated off
    # gated on -> reminder draft banta (email send fail ho sakta, draft recorded)
    monkeypatch.setenv("BOOKING_REMINDERS", "1")
    out = asyncio.run(br.run_due())
    assert out["enabled"] is True and out["reminders"] == 1
    assert br.upcoming() == []  # reminded ho gaya


def test_review_monitor_gates(tmp_path, monkeypatch):
    from app.marketing import review_monitor as rm

    monkeypatch.delenv("REVIEW_MONITOR", raising=False)
    assert asyncio.run(rm.run_check()) == {"enabled": False}
    monkeypatch.setenv("REVIEW_MONITOR", "1")
    monkeypatch.delenv("GOOGLE_MAPS_API_KEY", raising=False)
    monkeypatch.setattr(rm, "_api_key", lambda: "")
    out = asyncio.run(rm.run_check())
    assert out.get("skipped")  # bina key graceful


def test_outbound_webhooks_register_emit(tmp_path, monkeypatch):
    from app.platform import outbound_webhooks as ow

    monkeypatch.setattr(ow, "_STORE", str(tmp_path / "wh.jsonl"))
    monkeypatch.setattr(ow, "_DELIVERIES", str(tmp_path / "whd.jsonl"))

    bad = ow.register("http://insecure.example")
    assert bad["ok"] is False  # https only
    r = ow.register("https://example.invalid/hook", ["inquiry_received"])
    assert r["ok"] is True and r.get("secret")
    assert len(ow.list_webhooks()) == 1
    # emit: URL unreachable -> delivered 0, par kabhi raise nahi + delivery logged
    n = asyncio.run(ow.emit("inquiry_received", {"name": "Test"}))
    assert n == 0
    assert ow.recent_deliveries(5)
    # non-matching event -> inert
    assert asyncio.run(ow.emit("signup", {})) == 0
    assert ow.remove(r["webhook"]["id"]) is True


def test_website_auditor_pure():
    from app.marketing import website_auditor as wa

    good_html = (
        '<html><head><title>Best Solar in Pune</title><meta name="description" content="x">'
        '<meta name="viewport" content="width=device-width"></head>'
        '<body><h1>Solar</h1><form></form><a href="https://wa.me/919876543210">WA</a> Call 9876543210</body></html>'
    )
    res = wa.analyze_html(good_html, "https://example.com")
    assert res["score"] >= 80 and not res["missing"]
    poor = wa.analyze_html("<html><body>hi</body></html>", "http://example.com")
    assert poor["score"] < 40 and "meta_description" in poor["missing"]
    # bad URL graceful
    out = asyncio.run(wa.audit_url(""))
    assert out["ok"] is False


def test_multilang_fallback():
    from app.marketing import multilang_post as ml

    out = asyncio.run(ml.translate_post("Diwali offer! 20% off ☀️ #solar"))
    assert out["ok"] is True
    # Default = DEFAULT_LANGS (3, backward-compat); LANGS ab 9 (regional add hue)
    assert set(out["versions"].keys()) == set(ml.DEFAULT_LANGS)
    assert set(ml.DEFAULT_LANGS) <= set(ml.LANGS.keys())
    for v in out["versions"].values():
        assert v  # fallback = original, kabhi empty nahi
    assert asyncio.run(ml.translate_post(""))["ok"] is False


def test_growth_router_has_bulk_routes():
    from app.api.growth import router

    paths = {r.path for r in iter_mounted_routes(router)}
    for p in (
        "/growth/content/carousel",
        "/growth/content/meme",
        "/growth/content/multilang",
        "/growth/deliverability",
        "/growth/bookings/remind-run",
        "/growth/reviews/monitor-run",
        "/growth/webhooks/register",
        "/growth/tools/website-audit",
    ):
        assert p in paths, f"route missing: {p}"
