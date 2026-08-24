import asyncio

from app.agents import process_library


def _run(action, inputs):
    return asyncio.run(process_library.execute_step({"action": action}, inputs))


def test_email_digest_maps_sent(monkeypatch):
    async def fake(force=False):
        return {"sent": True, "week": "W25"}

    monkeypatch.setattr("app.platform.revenue_digest.run", fake)
    r = _run("email_digest", {})
    assert r["ok"] and r["count"] == 1 and "emailed-admin" in r["detail"]


def test_email_digest_never_raises(monkeypatch):
    async def boom(force=False):
        raise RuntimeError("x")

    monkeypatch.setattr("app.platform.revenue_digest.run", boom)
    r = _run("email_digest", {})
    assert r["ok"] is False


def test_whatsapp_draft_links_default(monkeypatch):
    async def fake(items, delay_s=None):
        return {"live": False, "links": 5}

    monkeypatch.setattr("app.marketing.whatsapp_campaign.send_campaign", fake)
    r = _run("whatsapp_draft", {"items": [{"x": 1}]})
    assert r["count"] == 5 and "links" in r["detail"]


def test_crm_queue_no_push_when_flag_off(monkeypatch):
    monkeypatch.delenv("CRM_SYNC", raising=False)
    called = []

    async def fake_push(lead, client_id="", note=""):
        called.append(lead)
        return {"ok": True}

    monkeypatch.setattr("app.platform.crm_sync.push_lead", fake_push)
    r = _run("crm_queue", {"leads": [{"a": 1}, {"b": 2}]})
    assert r["ok"] and r["count"] == 0 and called == []  # draft summary, NO push
    assert "no push" in r["detail"]


def test_crm_queue_pushes_when_flag_on(monkeypatch):
    monkeypatch.setenv("CRM_SYNC", "1")
    called = []

    async def fake_push(lead, client_id="", note=""):
        called.append(lead)
        return {"ok": True}

    monkeypatch.setattr("app.platform.crm_sync.push_lead", fake_push)
    r = _run("crm_queue", {"leads": [{"a": 1}, {"b": 2}]})
    assert r["count"] == 2 and len(called) == 2


def test_seo_blog_draft_maps_title(monkeypatch):
    async def fake(niche, city="", topic=None):
        return {"title": "10 Tips", "slug": "10-tips"}

    monkeypatch.setattr("app.marketing.seo_blog.generate_article", fake)
    r = _run("seo_blog_draft", {"niche": "salon"})
    assert r["ok"] and r["count"] == 1 and "10 Tips" in r["detail"]


def test_brand_pulse_maps_mentions(monkeypatch):
    async def fake(business_name, city=None, niche=None):
        return {"ok": True, "mentions": [1, 2], "reply_drafts": [1]}

    monkeypatch.setattr("app.platform.brand_pulse.scan", fake)
    r = _run("brand_pulse", {"business_name": "Acme"})
    assert r["count"] == 2 and "drafts=1" in r["detail"]


def test_brand_pulse_requires_business_name(monkeypatch):
    r = _run("brand_pulse", {})
    assert r["ok"] is False


def test_review_scan_maps_new(monkeypatch):
    async def fake(max_clients=15):
        return {"enabled": True, "new_reviews": 4}

    monkeypatch.setattr("app.marketing.review_monitor.run_check", fake)
    r = _run("review_scan", {})
    assert r["count"] == 4


def test_review_scan_off(monkeypatch):
    async def fake(max_clients=15):
        return {"enabled": False}

    monkeypatch.setattr("app.marketing.review_monitor.run_check", fake)
    r = _run("review_scan", {})
    assert r["ok"] and r["count"] == 0 and "off" in r["detail"]


def test_client_report_draft_forces_send_false(monkeypatch):
    captured = {}

    async def fake(client_id, month="", send=None):
        captured["send"] = send
        return {"ok": True, "path": "data/reports/x.html"}

    monkeypatch.setattr("app.marketing.client_report.build_report", fake)
    r = _run("client_report_draft", {"client_id": "c1"})
    assert r["ok"] and r["count"] == 1
    assert captured["send"] is False  # CRITICAL: never emails the customer


def test_client_report_draft_requires_client_id(monkeypatch):
    r = _run("client_report_draft", {})
    assert r["ok"] is False


def test_http_request_delegates_to_flow_http(monkeypatch):
    async def fake(inputs):
        return {"ok": True, "count": 1, "detail": "GET host -> 200"}

    monkeypatch.setattr("app.automation.flow_http.run", fake)
    r = _run("http_request", {"url": "https://leadsgenai.in/health"})
    assert r["ok"] and "200" in r["detail"]


def test_new_actions_registered():
    for k in (
        "email_digest",
        "whatsapp_draft",
        "crm_queue",
        "seo_blog_draft",
        "brand_pulse",
        "review_scan",
        "client_report_draft",
        "http_request",
    ):
        assert k in process_library.EXECUTORS
