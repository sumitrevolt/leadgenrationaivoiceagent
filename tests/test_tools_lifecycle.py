"""Tests — lifecycle/email tools batch (newsletter, winback, email_signature, lead_magnet).

Pure-python: koi network/LLM/SMTP nahi — sab monkeypatched. Stores tmp_path pe.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from app.marketing import email_signature, lead_magnet, newsletter
from app.platform import winback


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _iso_days_ago(days: float) -> str:
    from datetime import datetime, timedelta, timezone

    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


@pytest.fixture()
def nl_store(tmp_path, monkeypatch):
    monkeypatch.setattr(newsletter, "_SUBS_PATH", str(tmp_path / "subs.jsonl"))
    monkeypatch.setattr(newsletter, "_RUNS_PATH", str(tmp_path / "runs.jsonl"))
    return tmp_path


# --------------------------------------------------------------------------- #
# Newsletter — subscribers + unsub
# --------------------------------------------------------------------------- #
def test_newsletter_add_subscribers_dedupe(nl_store):
    res = newsletter.add_subscribers(
        "c1",
        [
            {"name": "Amit", "email": "amit@example.com"},
            {"name": "Amit dup", "email": "AMIT@example.com"},  # same email (case)
            {"name": "Bad", "email": "not-an-email"},
            {"name": "Riya", "email": "riya@example.com"},
        ],
    )
    assert res["ok"] is True
    assert res["added"] == 2
    assert res["skipped"] == 2
    subs = newsletter.subscribers("c1")
    assert {s["email"] for s in subs} == {"amit@example.com", "riya@example.com"}
    # other client isolated
    assert newsletter.subscribers("c2") == []


def test_newsletter_unsubscribe_token_flow(nl_store):
    newsletter.add_subscribers("c1", [{"name": "Amit", "email": "amit@example.com"}])
    token = newsletter.subscribers("c1")[0]["token"]
    res = newsletter.unsubscribe(token)
    assert res["ok"] is True and res["email"] == "amit@example.com"
    assert newsletter.subscribers("c1") == []  # active me nahi
    # unsub persists in include_unsub view + re-import respects opt-out
    again = newsletter.add_subscribers("c1", [{"name": "Amit", "email": "amit@example.com"}])
    assert again["added"] == 0
    # bad tokens never raise
    assert newsletter.unsubscribe("../../etc")["ok"] is False
    assert newsletter.unsubscribe("")["ok"] is False
    html = newsletter.unsub_html({"ok": True})
    assert "hata diye" in html and "<html" in html


# --------------------------------------------------------------------------- #
# Newsletter — compose + run + rss
# --------------------------------------------------------------------------- #
def test_newsletter_compose_deterministic_fallback(nl_store, monkeypatch):
    async def _no_llm(*a, **k):
        return ""

    monkeypatch.setattr(newsletter, "_llm_intro", _no_llm)
    news = asyncio.run(newsletter.compose("no-such-client"))
    assert news["ok"] is True
    assert news["subject"]
    assert "Namaste" in news["html"]
    assert "review" in news["html"].lower()
    assert news["month"]


def test_newsletter_run_flag_off_record_only(nl_store, monkeypatch):
    monkeypatch.delenv("NEWSLETTER_ENGINE", raising=False)
    sent = []

    async def _fake_send(to, subject, text, html):
        sent.append(to)
        return True

    monkeypatch.setattr(newsletter, "_send_one", _fake_send)
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda *a, **k: [{"id": "c1", "business_name": "Sharma Solar"}],
    )
    newsletter.add_subscribers("c1", [{"name": "Amit", "email": "amit@example.com"}])
    out = asyncio.run(newsletter.run_due_if_enabled())
    assert out["enabled"] is False
    assert out["recorded"] == 1
    assert out["sent"] == 0 and sent == []  # record-only, koi send nahi


def test_newsletter_run_flag_on_sends_and_month_dedupes(nl_store, monkeypatch):
    monkeypatch.setenv("NEWSLETTER_ENGINE", "1")
    sent = []

    async def _fake_send(to, subject, text, html):
        assert "unsub" in html.lower() or "Unsubscribe" in html
        sent.append(to)
        return True

    async def _no_llm(*a, **k):
        return ""

    monkeypatch.setattr(newsletter, "_send_one", _fake_send)
    monkeypatch.setattr(newsletter, "_llm_intro", _no_llm)
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "list_clients",
        lambda *a, **k: [{"id": "c1", "business_name": "Sharma Solar"}],
    )
    newsletter.add_subscribers(
        "c1",
        [{"name": "Amit", "email": "amit@example.com"}, {"name": "R", "email": "r@example.com"}],
    )
    out = asyncio.run(newsletter.run_due_if_enabled())
    assert out["enabled"] is True and out["sent"] == 2
    # month dedupe — dusri run me kuch nahi
    out2 = asyncio.run(newsletter.run_due_if_enabled())
    assert out2["sent"] == 0 and out2["recorded"] == 0
    assert len(sent) == 2


def test_newsletter_rss_to_email(nl_store, monkeypatch):
    from app.marketing import seo_blog

    monkeypatch.setattr(
        seo_blog,
        "list_articles",
        lambda *a, **k: [
            {
                "slug": "post-1",
                "title": "Post 1",
                "meta_description": "d1",
                "created_at": "2026-06-01",
            },
            {
                "slug": "post-2",
                "title": "Post 2",
                "meta_description": "d2",
                "created_at": "2026-06-02",
            },
        ],
    )
    d = newsletter.rss_to_email()
    assert d["ok"] is True and len(d["posts"]) == 2
    assert "post-1" in d["html"] and d["status"] == "draft"
    # marker likha — same posts dobara nahi
    d2 = newsletter.rss_to_email()
    assert d2["posts"] == []


# --------------------------------------------------------------------------- #
# Winback
# --------------------------------------------------------------------------- #
@pytest.fixture()
def wb_store(tmp_path, monkeypatch):
    monkeypatch.setattr(winback, "_DRAFTS_PATH", str(tmp_path / "winback_drafts.jsonl"))
    # customer source quiet by default
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "list_clients", lambda *a, **k: [])
    return tmp_path


def test_winback_find_inactive(wb_store, monkeypatch):
    from app.platform import prospector

    rows = [
        {
            "id": "p1",
            "business_name": "Old Gym",
            "phone": "9876543210",
            "email": "gym@example.com",
            "status": "ready",
            "created_at": _iso_days_ago(90),
        },
        {
            "id": "p2",
            "business_name": "Fresh Cafe",
            "phone": "9876500000",
            "status": "ready",
            "created_at": _iso_days_ago(5),
        },
        {
            "id": "p3",
            "business_name": "Dead Co",
            "phone": "9876511111",
            "status": "dead",
            "created_at": _iso_days_ago(200),
        },
        {"id": "p4", "business_name": "No Date", "phone": "9876522222", "status": "ready"},
    ]
    monkeypatch.setattr(prospector, "list_prospects", lambda *a, **k: rows)
    inactive = winback.find_inactive(days=60)
    assert [r["id"] for r in inactive] == ["p1"]  # fresh/dead/no-date skip
    assert inactive[0]["days_inactive"] >= 89


def test_winback_draft_shapes(wb_store):
    d = winback.draft(
        {
            "type": "customer",
            "name": "Amit",
            "phone": "9876543210",
            "business_name": "Sharma Salon",
            "days_inactive": 65,
        }
    )
    assert d["ok"] is True and d["status"] == "draft"
    assert "wa.me/919876543210" in d["wa_link"]
    assert "15%" in d["wa_message"] and "mahine" in d["wa_message"]
    assert d["email_subject"] and "Sharma Salon" in d["email_body"]
    # prospect variant + never-raise on garbage
    p = winback.draft({"type": "prospect", "name": "Old Gym", "phone": "9876543210"})
    assert p["ok"] is True and "audit" in p["wa_message"]
    assert winback.draft(None)["ok"] is True  # defaults, no raise


def test_winback_run_gated_and_dedupes(wb_store, monkeypatch):
    from app.platform import prospector

    rows = [
        {
            "id": "p1",
            "business_name": "Old Gym",
            "phone": "9876543210",
            "email": "gym@example.com",
            "status": "ready",
            "created_at": _iso_days_ago(90),
        },
    ]
    monkeypatch.setattr(prospector, "list_prospects", lambda *a, **k: rows)
    monkeypatch.delenv("WINBACK_ENGINE", raising=False)
    out = asyncio.run(winback.run_due_if_enabled())
    assert out.get("skipped") is True  # default OFF

    monkeypatch.setenv("WINBACK_ENGINE", "1")
    out = asyncio.run(winback.run_due_if_enabled())
    assert out["ok"] is True and out["drafts_created"] == 1
    assert winback.list_drafts()[0]["phone"] == "9876543210"
    # 30-din dedupe — dobara draft nahi
    out2 = asyncio.run(winback.run_due_if_enabled())
    assert out2["drafts_created"] == 0


# --------------------------------------------------------------------------- #
# Email signature
# --------------------------------------------------------------------------- #
def test_email_signature_branded(monkeypatch):
    from app.marketing import clients_store

    fake = {
        "id": "c9",
        "business_name": "Sharma Solar",
        "slug": "sharma-solar",
        "phone": "9876543210",
        "niche": "solar",
    }
    monkeypatch.setattr(
        clients_store, "get_by_slug", lambda s: fake if s == "sharma-solar" else None
    )
    monkeypatch.setattr(clients_store, "get_client", lambda c: None)
    kit = email_signature.generate(
        slug="sharma-solar", campaign_banner_text="Diwali offer — 20% off!"
    )
    assert kit["ok"] is True
    assert "Sharma Solar" in kit["html"]
    assert "wa.me/919876543210" in kit["html"]
    assert "/b/sharma-solar?utm_source=email_signature" in kit["html"]
    assert "Diwali offer" in kit["html"] and "Diwali offer" in kit["text"]
    assert "GMAIL" in kit["instructions"] and "OUTLOOK" in kit["instructions"]


def test_email_signature_unknown_client_never_raises(monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "get_by_slug", lambda s: None)
    monkeypatch.setattr(clients_store, "get_client", lambda c: None)
    kit = email_signature.generate(client_id="nope")
    assert kit["ok"] is True  # generic kit, kabhi fail nahi
    assert kit["html"] and kit["text"] and kit["instructions"]


# --------------------------------------------------------------------------- #
# Lead magnet
# --------------------------------------------------------------------------- #
def test_lead_magnet_static_fallback_and_save(tmp_path, monkeypatch):
    monkeypatch.setattr(lead_magnet, "_DIR", str(tmp_path / "lead_magnets"))

    async def _no_llm(*a, **k):
        return []

    monkeypatch.setattr(lead_magnet, "_llm_points", _no_llm)
    res = asyncio.run(
        lead_magnet.generate("real_estate", "Pune", "Sharma Properties", slug="sharma-prop")
    )
    assert res["ok"] is True
    assert res["points_source"] == "static"
    assert 8 <= len(res["points"]) <= 10
    assert os.path.isfile(res["file"])
    assert res["name"].endswith(".html")
    assert res["url"].startswith("/api/lifecycle/lead-magnet-file/")
    content = open(res["file"], encoding="utf-8").read()
    assert "Sharma Properties" in content and "Free Google Audit" in content
    assert "widget.js" in res["capture_note"]


def test_lead_magnet_safe_file_path_locked(tmp_path, monkeypatch):
    monkeypatch.setattr(lead_magnet, "_DIR", str(tmp_path / "lead_magnets"))
    os.makedirs(lead_magnet._DIR, exist_ok=True)
    with open(os.path.join(lead_magnet._DIR, "good-guide.html"), "w", encoding="utf-8") as f:
        f.write("<html>ok</html>")
    assert lead_magnet.safe_file_path("good-guide.html")  # legit
    assert lead_magnet.safe_file_path("../secrets.html") is None
    assert lead_magnet.safe_file_path("..\\..\\boot.ini") is None
    assert lead_magnet.safe_file_path("evil.exe") is None
    assert lead_magnet.safe_file_path("missing.html") is None
    assert lead_magnet.safe_file_path("") is None
    assert lead_magnet.available().keys() == {"weasyprint", "pdfkit"}


def test_lead_magnet_unknown_niche_generic_points(tmp_path, monkeypatch):
    monkeypatch.setattr(lead_magnet, "_DIR", str(tmp_path / "lm"))

    async def _no_llm(*a, **k):
        return []

    monkeypatch.setattr(lead_magnet, "_llm_points", _no_llm)
    res = asyncio.run(lead_magnet.generate("totally_unknown_niche", "", "Test Biz"))
    assert res["ok"] is True and len(res["points"]) >= 8  # generic checklist tail


# --------------------------------------------------------------------------- #
# Router import smoke (mount sanity — no app boot needed)
# --------------------------------------------------------------------------- #
def test_lifecycle_router_imports_and_routes():
    from app.api.lifecycle import router

    paths = {r.path for r in router.routes}
    assert "/lifecycle/newsletter/subscribers" in paths
    assert "/lifecycle/newsletter/unsub/{token}" in paths
    assert "/lifecycle/winback/run" in paths
    assert "/lifecycle/email-signature" in paths
    assert "/lifecycle/lead-magnet-file/{name}" in paths
