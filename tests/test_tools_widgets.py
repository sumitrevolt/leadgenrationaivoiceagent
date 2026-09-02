"""Tests — conversion widgets batch (popup_widgets / bio_link / site_beacon).

Pure-python, tmp_path monkeypatch (no network, no DB, no LLM).
Run: pytest tests/test_tools_widgets.py -q
"""

from __future__ import annotations

import json

import pytest

from app.marketing import bio_link, loyalty, popup_widgets
from app.platform import site_beacon


@pytest.fixture()
def stores(tmp_path, monkeypatch):
    """Saare jsonl stores tmp_path pe + client/brand lookups stub."""
    monkeypatch.setattr(popup_widgets, "_CONFIG_FILE", str(tmp_path / "popup_config.jsonl"))
    monkeypatch.setattr(bio_link, "_BIO_FILE", str(tmp_path / "bio_links.jsonl"))
    monkeypatch.setattr(bio_link, "_CLICKS_FILE", str(tmp_path / "bio_clicks.jsonl"))
    monkeypatch.setattr(site_beacon, "_EVENTS_FILE", str(tmp_path / "beacon_events.jsonl"))
    monkeypatch.setattr(site_beacon, "_writes_since_check", 0)
    monkeypatch.setattr(loyalty, "_CAMPAIGNS", str(tmp_path / "loyalty_campaigns.jsonl"))
    monkeypatch.setattr(loyalty, "_REDEMPTIONS", str(tmp_path / "loyalty_redemptions.jsonl"))
    fake_client = {
        "id": "c-test-1",
        "slug": "sharma-solar",
        "business_name": "Sharma Solar",
        "phone": "9876543210",
        "upi_vpa": "sharma@upi",
        "brand_color": "#16a34a",
    }
    monkeypatch.setattr(popup_widgets, "_load_client", lambda s: dict(fake_client))
    monkeypatch.setattr(bio_link, "_load_client", lambda s: dict(fake_client))
    return tmp_path


# ------------------------------ popup_widgets ------------------------------ #
def test_popup_save_get_latest_wins(stores):
    r1 = popup_widgets.save_config("sharma-solar", {"popup": {"enabled": True, "title": "Pehla"}})
    assert r1["ok"] is True
    r2 = popup_widgets.save_config("sharma-solar", {"popup": {"enabled": True, "title": "Dusra"}})
    assert r2["ok"] is True
    cfg = popup_widgets.get_config("sharma-solar")
    assert cfg["popup"]["title"] == "Dusra"
    assert cfg["popup"]["enabled"] is True
    # doosre slug pe kuch nahi = disabled defaults
    assert popup_widgets.get_config("koi-aur")["popup"]["enabled"] is False


def test_popup_trigger_and_delay_validation(stores):
    r = popup_widgets.save_config(
        "sharma-solar",
        {"popup": {"enabled": True, "trigger": "evil_trigger", "delay_s": 99999}},
    )
    assert r["config"]["popup"]["trigger"] == "delay"  # invalid → default
    assert r["config"]["popup"]["delay_s"] == 120  # clamp
    r2 = popup_widgets.save_config("sharma-solar", {"popup": {"trigger": "exit_intent"}})
    assert r2["config"]["popup"]["trigger"] == "exit_intent"
    r3 = popup_widgets.save_config("sharma-solar", {"popup": {"trigger": "delay_s"}})  # spec alias
    assert r3["config"]["popup"]["trigger"] == "delay"


def test_wheel_segments_clamped(stores):
    segs = [{"label": f"Offer {i}"} for i in range(8)]
    r = popup_widgets.save_config("sharma-solar", {"wheel": {"enabled": True, "segments": segs}})
    assert len(r["config"]["wheel"]["segments"]) == 6  # max 6
    assert r["config"]["wheel"]["enabled"] is True
    # <2 segments = wheel render-disable
    r2 = popup_widgets.save_config(
        "sharma-solar", {"wheel": {"enabled": True, "segments": segs[:1]}}
    )
    assert r2["config"]["wheel"]["enabled"] is False


def test_render_js_escapes_and_embed_contract(stores):
    popup_widgets.save_config(
        "sharma-solar",
        {
            "popup": {
                "enabled": True,
                "title": '</script><img src=x onerror="x">',
                "body": 'He said "hi"',
            }
        },
    )
    js = popup_widgets.render_js("sharma-solar")
    # user text json-escaped — raw </script> breakout kabhi nahi
    assert "</script>" not in js
    assert '\\"hi\\"' in js or '\\"' in js
    # CORS-free contract: proven embed iframe + 1/day localStorage cap
    assert "/b/sharma-solar/embed" in js
    assert "lgpw_" in js and "localStorage" in js
    # brand color picked from client record
    assert "#16a34a" in js
    # exit-intent + scroll + conic wheel sab template me
    assert "mouseout" in js and "scroll" in js and "conic-gradient" in js


def test_render_js_invalid_slug_safe(stores):
    js = popup_widgets.render_js("../../etc/passwd")
    assert "etc/passwd" not in js  # slug regex-locked (sirf [a-z0-9-])
    assert js.startswith("/*") or "lgaiPopupPack" in js


def test_snippet_and_wheel_coupons_reuse_loyalty(stores):
    snip = popup_widgets.snippet("sharma-solar")
    assert "/api/widgets/popup.js?slug=sharma-solar" in snip
    res = popup_widgets.create_wheel_coupons(
        "c-test-1",
        "sharma-solar",
        [{"title": "Solar 20", "value": 20}, {"title": "Free Visit", "kind": "freebie"}],
    )
    assert res["ok"] is True
    codes = [s["coupon_code"] for s in res["segments"]]
    assert all(codes), codes
    # codes REAL loyalty campaigns hain (check_code valid)
    chk = loyalty.check_code(codes[0])
    assert chk["valid"] is True
    # config me wheel enable + codes baked
    cfg = popup_widgets.get_config("sharma-solar")
    assert cfg["wheel"]["enabled"] is True
    assert cfg["wheel"]["segments"][0]["coupon_code"] == codes[0]


# --------------------------------- bio_link -------------------------------- #
def test_bio_save_get_and_block_clean(stores):
    r = bio_link.save_bio(
        "sharma-solar",
        [
            {"type": "whatsapp", "label": "WhatsApp karein"},
            {"type": "evil<script>", "label": "Site", "url": "https://sharma.in"},
            {"label": ""},  # no label = drop
            {"type": "upi", "label": "UPI Pay", "id": "Pay Now!!"},
        ],
        title="Sharma Solar",
    )
    assert r["ok"] is True
    cfg = bio_link.get_bio("sharma-solar")
    assert len(cfg["blocks"]) == 3
    assert cfg["blocks"][1]["type"] == "link"  # unknown type → link
    assert cfg["blocks"][3 - 1]["id"] == "paynow"  # id sanitized
    assert cfg["blocks"][0]["id"] == "b1"  # autogen


def test_bio_resolve_targets_and_security(stores):
    bio_link.save_bio(
        "sharma-solar",
        [
            {"id": "wa", "type": "whatsapp", "label": "WA"},  # value nahi → client phone
            {"id": "call", "type": "call", "label": "Call", "value": "098765 43210"},
            {"id": "upi", "type": "upi", "label": "Pay"},
            {"id": "site", "type": "link", "label": "Site", "url": "https://sharma.in/x"},
            {"id": "bad", "type": "link", "label": "Bad", "url": "javascript:alert(1)"},
            {"id": "cat", "type": "catalog", "label": "Catalog"},
        ],
    )
    assert bio_link.resolve_block("sharma-solar", "wa") == "https://wa.me/919876543210"
    assert bio_link.resolve_block("sharma-solar", "call") == "tel:+919876543210"
    upi = bio_link.resolve_block("sharma-solar", "upi")
    assert upi.startswith("upi://pay?pa=sharma%40upi") and "cu=INR" in upi
    assert bio_link.resolve_block("sharma-solar", "site") == "https://sharma.in/x"
    assert bio_link.resolve_block("sharma-solar", "bad") is None  # javascript: blocked
    assert bio_link.resolve_block("sharma-solar", "cat") == "/b/sharma-solar"
    assert bio_link.resolve_block("sharma-solar", "nahi-hai") is None
    assert bio_link.resolve_block("unknown-slug", "wa") is None


def test_bio_clicks_logged_and_stats(stores):
    bio_link.save_bio("sharma-solar", [{"id": "wa", "type": "whatsapp", "label": "WA"}])
    for _ in range(3):
        assert bio_link.resolve_block("sharma-solar", "wa") is not None
    st = bio_link.bio_stats("sharma-solar")
    assert st["clicks_total"] == 3
    assert st["by_block"]["wa"]["clicks"] == 3
    assert st["clicks_7d"] == 3
    # failed resolve = no log
    bio_link.resolve_block("sharma-solar", "ghost")
    assert bio_link.bio_stats("sharma-solar")["clicks_total"] == 3


def test_render_bio_html_escapes_and_tracking(stores):
    bio_link.save_bio(
        "sharma-solar",
        [{"id": "wa", "type": "whatsapp", "label": "<script>alert(1)</script>"}],
        title="Sharma & Sons <b>",
    )
    res = bio_link.render_bio_html("sharma-solar")
    assert res["ok"] is True
    html_out = res["html"]
    assert "<script>alert(1)</script>" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "Sharma &amp; Sons" in html_out
    assert "/api/widgets/bio/sharma-solar/c/wa" in html_out  # tracking redirect href
    assert "#16a34a" in html_out  # brand color
    # config na ho par CLIENT ho → default blocks (WA/call/website) auto-render
    res2 = bio_link.render_bio_html("koi-aur")
    assert res2["ok"] is True
    assert "WhatsApp" in res2["html"]
    # client bhi na ho → ok False (caller redirect kare)
    import types

    orig = bio_link._load_client
    bio_link._load_client = lambda s: {}
    try:
        assert bio_link.render_bio_html("bilkul-anjaan")["ok"] is False
    finally:
        bio_link._load_client = orig


# -------------------------------- site_beacon ------------------------------ #
def test_beacon_record_coarse_privacy(stores):
    r = site_beacon.record_event(
        {
            "slug": "sharma-solar",
            "type": "pageview",
            "path": "/",
            "ref": "https://instagram.com/x",
            "source": "",
        },
        ip="103.21.45.67",
        ua="Mozilla/5.0 Test",
    )
    assert r["ok"] is True
    line = open(site_beacon._EVENTS_FILE, encoding="utf-8").read().strip()
    rec = json.loads(line)
    assert rec["ip"] == "103.21.45.x"  # last octet masked
    assert rec["ua"] != "Mozilla/5.0 Test" and len(rec["ua"]) == 10  # hash only
    # invalid type/slug = drop
    assert site_beacon.record_event({"slug": "sharma-solar", "type": "evil"})["ok"] is False
    assert site_beacon.record_event({"slug": "", "type": "pageview"})["ok"] is False


def test_beacon_stats_and_summary(stores):
    for i in range(4):
        site_beacon.record_event(
            {
                "slug": "sharma-solar",
                "type": "pageview",
                "path": "/" if i < 3 else "/pricing",
                "ref": "https://www.instagram.com/p/x",
                "source": "instagram" if i == 0 else "",
            },
            ip=f"1.2.3.{i}",
            ua=f"UA-{i}",
        )
    site_beacon.record_event(
        {"slug": "sharma-solar", "type": "click", "kind": "wa"}, ip="1.2.3.1", ua="UA-1"
    )
    site_beacon.record_event(
        {"slug": "sharma-solar", "type": "click", "kind": "tel"}, ip="1.2.3.1", ua="UA-1"
    )
    site_beacon.record_event(
        {"slug": "sharma-solar", "type": "click", "kind": "track", "name": "cta_hero"}
    )
    st = site_beacon.stats("sharma-solar", days=7)
    assert st["pageviews"] == 4
    assert st["visitors"] == 4  # 4 alag (ip,ua) same day... approx unique
    assert st["wa_clicks"] == 1 and st["tel_clicks"] == 1
    assert st["top_paths"][0][0] == "/"
    assert ("instagram", 1) in st["top_sources"] or ("Instagram", 3) in st["top_sources"]
    assert st["tracked_clicks"][0][0] == "cta_hero"
    assert "visitors" in st["summary"] and "WhatsApp" in st["summary"]
    # dusra slug = zero
    assert site_beacon.stats("koi-aur")["pageviews"] == 0


def test_beacon_trim(stores, monkeypatch):
    monkeypatch.setattr(site_beacon, "_MAX_LINES", 5)
    monkeypatch.setattr(site_beacon, "_TRIM_EVERY", 1)
    for i in range(9):
        site_beacon.record_event({"slug": "sharma-solar", "type": "pageview", "path": f"/p{i}"})
    lines = [
        x for x in open(site_beacon._EVENTS_FILE, encoding="utf-8").read().splitlines() if x.strip()
    ]
    assert len(lines) <= 5
    assert json.loads(lines[-1])["path"] == "/p8"  # newest kept


def test_beacon_js_contract(stores):
    js = site_beacon.beacon_js("sharma-solar")
    assert "sendBeacon" in js
    assert '"sharma-solar"' in js
    assert "utm_source" in js
    assert "/api/widgets/beacon" in js
    assert "data-lg-track" in js and "wa\\.me" in js and "tel:" in js
    # fully-invalid slug (sanitize ke baad khali) = harmless comment
    assert site_beacon.beacon_js("!!!").startswith("/*")


def test_api_module_imports():
    """Router import-safe (mount kabhi crash na kare)."""
    from app.api.widgets import router

    paths = {r.path for r in router.routes}
    assert "/widgets/popup.js" in paths
    assert "/widgets/beacon" in paths
    assert "/widgets/bio/{slug}/c/{block_id}" in paths
