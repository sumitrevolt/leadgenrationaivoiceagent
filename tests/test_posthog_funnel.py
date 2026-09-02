"""Tests: PostHog inquiry → paid funnel split by business_type/niche.

- insight_payload() — FUNNELS filters shape (pure).
- client_business_type() — client record se niche + wizard label.
- ensure_insight() — INERT bina phx_ key; created/exists path via mocked HTTP.
- Event plumbing — lead_captured + payment_activated dono business_type/niche
  carry karte hain (isliye funnel split ho sakta hai).
"""

from __future__ import annotations

from app.integrations import posthog_funnel as pf


def test_insight_payload_is_funnel_with_business_type_breakdown():
    p = pf.insight_payload()
    f = p["filters"]
    assert f["insight"] == "FUNNELS"
    assert [e["id"] for e in f["events"]] == ["lead_captured", "payment_activated"]
    assert f["funnel_order_type"] == "strict"
    assert f["breakdown_type"] == "event"
    assert f["breakdown"] == "business_type"
    assert p["name"] == "Inquiry → Paid (by business type)"


def test_client_business_type_resolves_from_client_record(monkeypatch):
    def _fake_get_client(cid):
        assert cid == "c1"
        return {"id": "c1", "niche": "salon_spa", "business_name": "Sharma Salon"}

    monkeypatch.setattr("app.marketing.clients_store.get_client", _fake_get_client)
    out = pf.client_business_type("c1")
    assert out["niche"] == "salon_spa"
    assert out["business_type"] == "Salon / Beauty Parlour"


def test_client_business_type_missing_client_is_empty(monkeypatch):
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda cid: None)
    assert pf.client_business_type("nope") == {}


def test_ensure_insight_inert_without_personal_key(monkeypatch):
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    out = pf.ensure_insight(create=True)
    assert out["status"] == "inert"
    assert "POSTHOG_PERSONAL_API_KEY" in out["note"]


def test_ensure_insight_creates_via_api(monkeypatch):
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "phx_test")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "12345")

    class _FakeResp:
        def __init__(self, status_code, json_body):
            self.status_code = status_code
            self._json = json_body

        def json(self):
            return self._json

    calls: list[tuple[str, str, object]] = []

    def _fake_get(url, **kw):
        calls.append(("get", url, kw))
        return _FakeResp(200, {"results": []})

    def _fake_post(url, **kw):
        calls.append(("post", url, kw))
        assert "business_type" in str(kw.get("json"))
        return _FakeResp(201, {"short_id": "abc123", "id": 9})

    import httpx

    monkeypatch.setattr(httpx, "get", _fake_get)
    monkeypatch.setattr(httpx, "post", _fake_post)

    out = pf.ensure_insight(create=True)
    assert out["status"] == "created"
    assert "abc123" in out["url"]
    # pehle search, phir create — dono /api/projects/12345/insights/ pe
    assert len(calls) == 2
    assert calls[0][0] == "get" and calls[1][0] == "post"


def test_ensure_insight_finds_existing(monkeypatch):
    monkeypatch.setenv("POSTHOG_PERSONAL_API_KEY", "phx_test")
    monkeypatch.setenv("POSTHOG_PROJECT_ID", "12345")

    class _FakeResp:
        def __init__(self, status_code, json_body):
            self.status_code = status_code
            self._json = json_body

        def json(self):
            return self._json

    import httpx

    monkeypatch.setattr(
        httpx,
        "get",
        lambda url, **kw: _FakeResp(200, {"results": [{"short_id": "zzz9"}]}),
    )

    out = pf.ensure_insight(create=False)
    assert out["status"] == "exists"
    assert "zzz9" in out["url"]


# --------------------------------------------------------------------------- #
# Event plumbing — funnel ke dono steps pe split dimension
# --------------------------------------------------------------------------- #
async def test_lead_captured_carries_business_type(client, monkeypatch):
    import app.platform.inquiry_hooks as hooks

    captured: list[tuple] = []
    monkeypatch.setattr(
        "app.analytics.posthog_client.capture",
        lambda cid, ev, props: captured.append((cid, ev, props)),
    )

    rec = {
        "source": "website",
        "niche": "salon_spa",
        "business_type": "Salon / Beauty Parlour",
        "client_id": "",
        "business_name": "X",
        "phone": "9876543210",
    }
    await hooks.run_after_inquiry(rec, mini_client_id=None)
    hits = [c for c in captured if c[1] == "lead_captured"]
    assert hits, "lead_captured fire hona chahiye"
    # Platform lead (client_id empty) bhi funnel me aana chahiye — distinct_id = phone
    assert hits[0][0] == "9876543210"
    assert hits[0][2]["niche"] == "salon_spa"
    assert hits[0][2]["business_type"] == "Salon / Beauty Parlour"


def test_payment_activated_carries_niche_and_business_type(monkeypatch):
    import app.platform.upi_payments as up

    captured: list[tuple] = []

    class _FakeUsage:
        @staticmethod
        def activate_plan(cid, plan, **kw):
            return True

        @staticmethod
        def reset_usage_period(cid):
            return None

    monkeypatch.setattr("app.billing.usage.activate_plan", _FakeUsage.activate_plan)
    monkeypatch.setattr("app.billing.usage.reset_usage_period", _FakeUsage.reset_usage_period)
    monkeypatch.setattr(
        "app.analytics.posthog_client.capture",
        lambda cid, ev, props: captured.append((cid, ev, props)),
    )
    monkeypatch.setattr(
        "app.integrations.posthog_funnel.client_business_type",
        lambda cid: {
            "niche": "salon_spa",
            "business_type": "Salon / Beauty Parlour",
            "phone": "9876543210",
        },
    )

    ok = up._try_activate("c1", "starter", amount=1999, enforce_floor=False)
    assert ok is True
    hits = [c for c in captured if c[1] == "payment_activated"]
    assert hits
    # distinct_id = phone (inquiry side se match — funnel same person pe)
    assert hits[0][0] == "9876543210"
    props = hits[0][2]
    assert props["niche"] == "salon_spa"
    assert props["business_type"] == "Salon / Beauty Parlour"
    assert props["gateway"] == "upi"
    assert "phone" not in props  # properties me nahi — distinct_id ban gaya


def test_admin_funnel_endpoint_reports_inert_without_phx_key(client, monkeypatch):
    monkeypatch.delenv("POSTHOG_PERSONAL_API_KEY", raising=False)
    r = client.get("/api/clientops/posthog/funnel")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "capture_enabled" in data
    assert data["insight"]["status"] == "inert"
