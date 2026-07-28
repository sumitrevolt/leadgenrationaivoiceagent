"""Tests for the engagement batch (UPI QR, short-links, reviews widget, lead alerts).

Offline + isolated: koi network/DB nahi. File-stores tmp_path pe monkeypatch,
outbound HTTP (Telegram/email) fakes se. Style: tests/test_parity_conversion.py.
"""

import asyncio
import json


# --------------------------------------------------------------------------- #
# F1: upi_qr — build_upi_uri / qr_image_url / payment_qr_pack
# --------------------------------------------------------------------------- #
def test_build_upi_uri_valid_and_encoding():
    from app.marketing.upi_qr import build_upi_uri

    uri = build_upi_uri("sharma.solar@oksbi", "Sharma Solar", amount=499, note="Site visit")
    assert uri.startswith("upi://pay?")
    assert "pa=sharma.solar@oksbi" in uri
    assert "pn=Sharma%20Solar" in uri
    assert "am=499" in uri
    assert "tn=Site%20visit" in uri and "cu=INR" in uri
    # no amount/note → params skip
    bare = build_upi_uri("a@ybl", "Biz")
    assert "am=" not in bare and "tn=" not in bare


def test_build_upi_uri_invalid_vpa():
    from app.marketing.upi_qr import build_upi_uri

    assert build_upi_uri("not-a-vpa", "Biz") == ""
    assert build_upi_uri("", "Biz") == ""
    assert build_upi_uri(None, "Biz") == ""


def test_qr_image_url_encodes():
    from app.marketing.upi_qr import qr_image_url

    url = qr_image_url("upi://pay?pa=a@ybl&pn=Biz", size=400)
    assert url.startswith("https://api.qrserver.com/v1/create-qr-code/?size=400x400&data=")
    assert "upi%3A%2F%2Fpay" in url  # fully URL-encoded
    # size clamp
    assert "100x100" in qr_image_url("x", size=5)


def test_payment_qr_pack_with_client(tmp_path, monkeypatch):
    from app.marketing import clients_store
    from app.marketing.upi_qr import payment_qr_pack

    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(clients_store, "brand_kit", None)
    rec = clients_store.add_client("Sharma Solar", "solar", phone="9876500001")
    cid = rec["id"]

    # bina upi_vpa → friendly error
    res = payment_qr_pack(cid)
    assert res["ok"] is False and "upi_vpa" in res["error"]

    # upi_vpa set (naya allowed field) → full pack
    assert clients_store.update_client(cid, upi_vpa="sharma@oksbi") is not None
    assert clients_store.get_client(cid)["upi_vpa"] == "sharma@oksbi"
    res2 = payment_qr_pack(cid, amount=999, note="advance")
    assert res2["ok"] is True and res2["vpa_valid"] is True
    assert res2["upi_uri"].startswith("upi://pay?pa=sharma@oksbi")
    assert "am=999" in res2["upi_uri"]
    assert res2["qr_url"].startswith("https://api.qrserver.com/")
    assert "<svg" in res2["poster_svg"]
    assert "sharma@oksbi" in res2["share_text"]
    assert res2["wa_share_url"].startswith("https://wa.me/?text=")

    # unknown client → error, no raise
    assert payment_qr_pack("nahi-hai")["ok"] is False


# --------------------------------------------------------------------------- #
# F2: short_links — create / resolve / stats / bandit credit
# --------------------------------------------------------------------------- #
def _fresh_short_links(tmp_path, monkeypatch):
    from app.platform import short_links

    monkeypatch.setattr(short_links, "_LINKS_FILE", str(tmp_path / "links.jsonl"))
    monkeypatch.setattr(short_links, "_CLICKS_FILE", str(tmp_path / "clicks.jsonl"))
    monkeypatch.setattr(short_links, "_cache", {})
    monkeypatch.setattr(short_links, "_cache_loaded", False)
    return short_links


def test_short_link_create_resolve_stats(tmp_path, monkeypatch):
    sl = _fresh_short_links(tmp_path, monkeypatch)

    res = sl.create("https://leadsgenai.in/pricing", label="pricing", channel="quora")
    assert res["ok"] is True and len(res["code"]) == 6
    assert res["short_url"].endswith("/r/" + res["code"])
    code = res["code"]

    url = sl.resolve(code, ua="Mozilla/5.0 test", ref="https://quora.com/q")
    assert url == "https://leadsgenai.in/pricing"
    sl.resolve(code)  # second click

    st = sl.stats()
    assert st["ok"] is True and st["total_clicks"] == 2 and st["total_links"] == 1
    assert st["by_code"][code] == 2
    assert st["by_channel"]["quora"] == 2
    assert st["links"][0]["clicks"] == 2

    # invalid / unknown
    assert sl.resolve("zzzzzz") is None
    assert sl.resolve("..") is None
    assert sl.resolve("") is None
    assert sl.create("notaurl")["ok"] is False
    assert sl.create("javascript:alert(1)")["ok"] is False


def test_short_link_bandit_credit_once_per_day(tmp_path, monkeypatch):
    sl = _fresh_short_links(tmp_path, monkeypatch)
    from app.marketing import channel_experiments

    credited = []
    monkeypatch.setattr(
        channel_experiments,
        "record_outcome",
        lambda ch, kind="inquiry", value=1, note="": credited.append((ch, kind)) or {"ok": True},
    )
    code = sl.create("https://leadsgenai.in/audit", channel="quora")["code"]
    sl.resolve(code)
    sl.resolve(code)
    sl.resolve(code)
    assert credited == [("quora", "click")]  # 3 clicks → sirf 1 credit/day

    # channel-less link → no credit at all
    code2 = sl.create("https://leadsgenai.in/")["code"]
    sl.resolve(code2)
    assert len(credited) == 1


def test_short_link_cache_miss_reload(tmp_path, monkeypatch):
    sl = _fresh_short_links(tmp_path, monkeypatch)
    code = sl.create("https://leadsgenai.in/blog")["code"]
    # simulate dusra worker: cache empty, file me record hai
    monkeypatch.setattr(sl, "_cache", {})
    monkeypatch.setattr(sl, "_cache_loaded", True)  # loaded-but-stale
    assert sl.resolve(code) == "https://leadsgenai.in/blog"


# --------------------------------------------------------------------------- #
# F3: reviews_widget — approved-only render + injector + snippet
# --------------------------------------------------------------------------- #
def test_reviews_widget_approved_only(tmp_path, monkeypatch):
    from app.api import minisite_builder as mb
    from app.marketing import clients_store, reviews_widget

    monkeypatch.setattr(mb, "_REVIEWS_DIR", str(tmp_path / "reviews"))
    monkeypatch.setattr(clients_store, "_CLIENTS_FILE", lambda: str(tmp_path / "clients.jsonl"))
    monkeypatch.setattr(clients_store, "brand_kit", None)

    slug = "test-biz"
    mb.add_review(slug, "Ravi", 5, "Bahut accha kaam <script>x</script>", approved=True)
    mb.add_review(slug, "Pending Guy", 1, "SECRET-PENDING-TEXT", approved=False)

    html = reviews_widget.reviews_widget_html(slug)
    assert "Ravi" in html and "Bahut accha kaam" in html
    assert "SECRET-PENDING-TEXT" not in html  # moderation respected
    assert "<script>x</script>" not in html  # escaped
    assert "★★★★★" in html
    assert "Powered by" in html and "LeadsGenAI" in html

    # empty feed → graceful placeholder (never raises)
    html2 = reviews_widget.reviews_widget_html("no-reviews-slug")
    assert "pehla review" in html2


def test_reviews_widget_js_and_snippet():
    from app.marketing import reviews_widget

    js = reviews_widget.widget_js("test-biz")
    assert "/api/engage/reviews-widget/test-biz" in js
    assert "iframe" in js and "document.currentScript" in js
    snip = reviews_widget.snippet("Test-Biz")
    assert snip.endswith("</script>")
    assert "/api/engage/reviews-widget.js/test-biz" in snip  # lowercased


# --------------------------------------------------------------------------- #
# F4: lead_alerts — dedupe + gating + bg scheduler
# --------------------------------------------------------------------------- #
def test_lead_alert_send_and_dedupe(tmp_path, monkeypatch):
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: {})

    sent = []

    async def fake_email(subject, body):
        sent.append((subject, body))
        return True

    monkeypatch.setattr(lead_alerts, "_send_email", fake_email)

    rec = {
        "name": "Ravi Kumar",
        "phone": "9876543210",
        "source": "widget",
        "message": "solar chahiye",
    }
    res = asyncio.run(lead_alerts.notify_new_lead(rec))
    assert res["ok"] is True and res["deduped"] is False
    assert res["email_sent"] is True
    # Hinglish alert body: phone + wa.me + naam
    body = sent[0][1]
    assert "9876543210" in body and "wa.me/919876543210" in body and "Ravi Kumar" in body
    assert "NAYA LEAD" in body

    # same phone within hour → dedupe, no extra sends
    n_before = len(sent)
    res2 = asyncio.run(lead_alerts.notify_new_lead(rec))
    assert res2["deduped"] is True
    assert len(sent) == n_before

    # alert log persisted
    lines = [
        json.loads(x) for x in (tmp_path / "alerts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert lines and lines[0]["phone"] == "9876543210"


def test_lead_alert_gated_silent_skip(tmp_path, monkeypatch):
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))
    monkeypatch.setattr(lead_alerts, "_notify_email_to", lambda: "")  # NOTIFY_EMAIL unset
    monkeypatch.setattr(lead_alerts, "_lookup_client", lambda rec: {})

    res = asyncio.run(lead_alerts.notify_new_lead({"name": "X", "phone": "9812345678"}))
    assert res["ok"] is True
    assert res["email_sent"] is False  # silent skip


def test_lead_alert_bg_never_raises(tmp_path, monkeypatch):
    from app.platform import lead_alerts

    monkeypatch.setattr(lead_alerts, "_PATH", str(tmp_path / "alerts.jsonl"))

    async def fake_notify(rec):
        return {"ok": True}

    monkeypatch.setattr(lead_alerts, "notify_new_lead", fake_notify)
    # no running loop (sync context) → daemon thread path, no raise
    lead_alerts.notify_new_lead_bg({"name": "BG", "phone": "9000000001"})
    # garbage input bhi safe
    lead_alerts.notify_new_lead_bg(None)

    # running-loop path → create_task, no raise
    async def in_loop():
        lead_alerts.notify_new_lead_bg({"name": "Loop", "phone": "9000000002"})
        await asyncio.sleep(0)

    asyncio.run(in_loop())
