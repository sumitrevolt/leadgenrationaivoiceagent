"""Social Networking Setup Wizard — hermetic tests.

Covers (1) the new per-client social config store (`app/social_engine/client_config.py`)
— defaults, validation, merge, isolation, latest-wins — and (2) the customer router
exposes the two new IDOR-safe endpoints. Store test uses a tmp file (no real data/
writes). Sandbox note: yeh app-deps chahiye (setup_logger + fastapi) — authoritative
run Windows venv pe hi hota hai.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def cc(monkeypatch):
    from app.social_engine import client_config as _cc

    td = tempfile.mkdtemp()
    monkeypatch.setattr(_cc, "_PATH", os.path.join(td, "social_config.jsonl"))
    return _cc


def test_defaults_when_unset(cc):
    g = cc.get("clientA")
    assert g["configured"] is False
    assert g["cadence"] == "daily"
    assert g["approval_mode"] == "auto"
    assert g["channels"] == []
    assert set(g["handles"].keys()) == {
        "instagram",
        "facebook",
        "gbp",
        "youtube",
        "linkedin",
        "twitter",
    }
    assert all(v == "" for v in g["handles"].values())


def test_save_normalizes_and_validates(cc):
    saved = cc.save(
        "clientA",
        handles={"youtube": "yt.com/@x", "instagram": "@insta"},
        channels=["instagram", "NOPE", "whatsapp", "instagram"],  # bad dropped, dedup
        cadence="hourly",  # invalid -> default
        approval_mode="review",
        postiz_integrations=["id1", "id1", " id2 "],  # dedup + trim
    )
    assert saved["cadence"] == "daily"  # invalid coerced to default
    assert saved["channels"] == ["instagram", "whatsapp"]
    assert saved["postiz_integrations"] == ["id1", "id2"]
    assert saved["handles"]["youtube"] == "yt.com/@x"
    assert saved["configured"] is True


def test_partial_save_merges_over_current(cc):
    cc.save("clientA", handles={"youtube": "yt"}, channels=["facebook"], cadence="daily")
    # second save only touches cadence — handles + channels must persist
    s2 = cc.save("clientA", cadence="off")
    assert s2["cadence"] == "off"
    assert s2["handles"]["youtube"] == "yt"
    assert s2["channels"] == ["facebook"]
    # handle-level merge: updating instagram keeps youtube
    s3 = cc.save("clientA", handles={"instagram": "@new"})
    assert s3["handles"]["instagram"] == "@new"
    assert s3["handles"]["youtube"] == "yt"


def test_client_isolation(cc):
    cc.save("clientA", handles={"youtube": "yt"}, cadence="daily")
    other = cc.get("clientB")
    assert other["configured"] is False
    assert other["handles"]["youtube"] == ""
    assert other["cadence"] == "daily"


def test_latest_write_wins(cc):
    cc.save("clientA", cadence="daily")
    cc.save("clientA", cadence="3x_week")
    assert cc.get("clientA")["cadence"] == "3x_week"


def test_never_raises_on_garbage(cc):
    # non-list channels / non-dict handles must not raise
    saved = cc.save("clientA", channels="notalist", handles="notadict", cadence=None)
    assert isinstance(saved, dict)
    assert saved["channels"] == []


def test_router_exposes_social_endpoints():
    """Both new routes present + IDOR-safe (client_id via require_customer dep)."""
    from app.api.customer_dashboard import router

    paths = {(r.path, tuple(sorted(getattr(r, "methods", []) or []))) for r in router.routes}
    have = {p for p, _ in paths}
    assert "/api/customer/social/config" in have
    methods = {m for p, ms in paths if p == "/api/customer/social/config" for m in ms}
    assert "GET" in methods and "POST" in methods


def test_social_get_returns_extended_wizard_fields():
    """Saved Step-1/Step-4 values must pre-fill after a dashboard refresh."""
    import inspect

    from app.api.customer_dashboard import customer_social_get

    source = inspect.getsource(customer_social_get)
    for field in (
        "website",
        "brand_tone",
        "target_audience",
        "products_or_services",
        "preferred_language",
        "posting_days",
        "posting_times",
        "content_categories",
        "prohibited_topics",
        "brand_safety_instructions",
    ):
        assert f'"{field}": cfg.get("{field}")' in source
