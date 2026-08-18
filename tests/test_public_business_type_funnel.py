"""Tests: wizard business-type selection wired into lead-magnet pages.

- GET /api/public/business-types -> wizard catalog (id/label/emoji/niche), no auth.
- POST /api/public/inquiry accepts business_type + niche (audit funnel).
- audit.html / site-audit.html dropdown + payload wiring (frontend contract).
"""

from __future__ import annotations


def test_business_types_endpoint_returns_wizard_catalog(client):
    r = client.get("/api/public/business-types")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("ok") is True
    bts = data.get("business_types") or []
    assert len(bts) >= 20  # wizard me 21 types hain (incl. general fallback)
    for b in bts:
        assert b["id"] and b["label"] and b["niche"]
    by_id = {b["id"]: b for b in bts}
    assert by_id["salon"]["niche"] == "salon_spa"
    assert by_id["restaurant"]["niche"] == "restaurant_cafe"
    assert by_id["laundry"]["niche"] == "laundry_dryclean"
    assert "emoji" in by_id["salon"]


def test_inquiry_captures_business_type_and_niche(client, monkeypatch):
    import app.api.public_site as ps
    import app.platform.inquiry_hooks as hooks

    captured: dict = {}

    def _fake_append(rec):
        captured.update(rec)
        return True

    monkeypatch.setattr(ps, "_append_jsonl", _fake_append)
    monkeypatch.setattr(ps, "_save_lead_db", lambda rec: None)

    async def _noop_run_after_inquiry(*args, **kwargs):
        return None

    monkeypatch.setattr(hooks, "run_after_inquiry", _noop_run_after_inquiry)

    r = client.post(
        "/api/public/inquiry",
        json={
            "name": "Audit Owner",
            "business_name": "Sharma Salon",
            "phone": "9876543210",
            "package": "Free Audit Lead",
            "utm_source": "audit",
            "business_type": "Salon / Beauty Parlour",
            "niche": "salon_spa",
            "message": "GBP audit score: 42/100",
        },
    )
    assert r.status_code == 200, r.text
    assert captured["business_type"] == "Salon / Beauty Parlour"
    assert captured["niche"] == "salon_spa"
    assert captured["utm_source"] == "audit"


def test_inquiry_notes_include_business_type(client, monkeypatch):
    """_save_lead_db ki notes me business type bhi aana chahiye (admin view)."""
    import app.api.public_site as ps

    # fake Lead + db — capture the kwargs _save_lead_db passes to Lead()
    created: dict = {}

    class _FakeLead:
        phone = None  # db.query().filter(Lead.phone == ...) ke liye
        id = "fake-lead-id"

        def __init__(self, **kw):
            created.update(kw)

    class _FakeDB:
        def __init__(self):
            self._leads = []

        def query(self, model):
            return self

        def filter(self, *a, **k):
            return self

        def first(self):
            return None

        def add(self, lead):
            self._leads.append(lead)

        def commit(self):
            pass

        def close(self):
            pass

    import app.models.lead as lead_mod

    monkeypatch.setattr(ps, "_db", lambda: _FakeDB())
    monkeypatch.setattr(lead_mod, "Lead", _FakeLead)  # _save_lead_db lazy-import karta hai

    rec = {
        "name": "X",
        "business_name": "Y",
        "phone": "9812345670",
        "message": "hello",
        "niche": "salon_spa",
        "business_type": "Salon / Beauty Parlour",
        "package": "Free Audit Lead",
    }
    lead_id = ps._save_lead_db(rec)
    assert lead_id is not None
    assert "Business type: Salon / Beauty Parlour" in created.get("notes", "")
    assert "Niche: salon_spa" in created.get("notes", "")


def test_lead_magnet_pages_wire_business_type_dropdown():
    """audit/site-audit/demo forms me business-type select + inquiry payload contract."""
    import pathlib

    audit = pathlib.Path("frontend/website/audit.html").read_text(encoding="utf-8")
    site = pathlib.Path("frontend/website/site-audit.html").read_text(encoding="utf-8")
    demo = pathlib.Path("frontend/website/demo.html").read_text(encoding="utf-8")

    # dropdown populated from the public catalog (all three lead magnets)
    for html in (audit, site, demo):
        assert "/api/public/business-types" in html
    assert 'id="a-type"' in audit
    assert 'id="ltype"' in site
    assert 'id="d-niche"' in demo

    # inquiry payload sends business_type + niche (funnel niche-aware)
    assert "business_type: bt ? bt.label : ''" in audit
    assert "niche: bt ? bt.niche : ''" in audit
    assert "business_type:bt?bt.label:''" in site
    assert "niche:bt?bt.niche:''" in site

    # demo: same dropdown + ai-demo niche-key resolve + CTA inquiry form
    assert "business_type: bt ? bt.label : ''" in demo
    assert "niche: bt ? bt.niche : ''" in demo
    assert 'id="demoLeadForm"' in demo
    assert "'Free AI Demo Lead'" in demo
    assert "selectedBiz()" in demo


def test_inquiry_dry_run_query_param_threads_to_chain(client, monkeypatch):
    """POST /api/public/inquiry?dry_run=1 — chain trigger hota hai par dial nahi.
    (dry_run query param → run_after_inquiry(dry_run=True); bina param → False.)"""
    import app.api.public_site as ps
    import app.platform.inquiry_hooks as hooks

    seen: dict = {}

    monkeypatch.setattr(ps, "_append_jsonl", lambda rec: True)
    monkeypatch.setattr(ps, "_save_lead_db", lambda rec: None)

    async def _capture_run_after_inquiry(rec, **kwargs):
        seen.update(kwargs)
        return None

    monkeypatch.setattr(hooks, "run_after_inquiry", _capture_run_after_inquiry)

    r = client.post(
        "/api/public/inquiry?dry_run=1",
        json={
            "name": "Smoke",
            "phone": "+919999999903",
            "business_name": "Arm Smoke Salon",
            "business_type": "Salon / Beauty Parlour",
            "niche": "salon_spa",
        },
    )
    assert r.status_code == 200, r.text
    assert seen.get("dry_run") is True

    # default (no param) → dry_run False — real path unchanged
    seen.clear()
    r2 = client.post(
        "/api/public/inquiry",
        json={"name": "Smoke2", "phone": "+919999999904", "business_name": "B"},
    )
    assert r2.status_code == 200, r2.text
    assert seen.get("dry_run") is False
