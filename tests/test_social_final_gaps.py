"""Loops-social-19/20/21 (2026-07-11): final gap-closure regression bundle.

Covers:
- Loop-social-19: extended /social/config schema (timezone, website,
  brand_tone, target_audience, products_or_services, preferred_language,
  posting_days, posting_times, content_categories, prohibited_topics,
  brand_safety_instructions) round-trips through client_config.
- Loop-social-20: edit_caption, replace_media, change_scheduled_time — each
  appends an audit row, locks after dispatch, refuses bad inputs.
- Loop-social-21: store.enqueue accepts media_assets + approval_status.
"""

from __future__ import annotations

import datetime
import os
import tempfile

import pytest


# =========================================================================== #
# Loop-social-19: wizard schema completeness                                   #
# =========================================================================== #
@pytest.fixture()
def cc(monkeypatch):
    from app.social_engine import client_config as _cc

    td = tempfile.mkdtemp()
    monkeypatch.setattr(_cc, "_PATH", os.path.join(td, "social_config.jsonl"))
    return _cc


def test_extended_defaults_present(cc):
    g = cc.get("cA")
    assert g["timezone"] == "Asia/Kolkata"
    assert g["preferred_language"] == "hinglish"
    assert g["posting_days"] == []
    assert g["posting_times"] == []
    assert g["content_categories"] == []
    assert g["prohibited_topics"] == []
    assert g["brand_safety_instructions"] == ""
    assert g["brand_tone"] == ""
    assert g["website"] == ""


def test_save_extended_fields_roundtrip(cc):
    saved = cc.save(
        "cA",
        timezone="Asia/Kolkata",
        website="https://shop.example.com",
        brand_tone="friendly",
        target_audience="Working women 25-40",
        products_or_services="makeup, hair care",
        preferred_language="hi",
        posting_days=["mon", "wed", "fri"],
        posting_times=["09:30", "18:00"],
        content_categories=["promo", "tips", "testimonials"],
        prohibited_topics=["politics", "competitors"],
        brand_safety_instructions="Never mention competitors by name.",
    )
    assert saved["preferred_language"] == "hi"
    assert saved["posting_days"] == ["mon", "wed", "fri"]
    assert saved["posting_times"] == ["09:30", "18:00"]
    assert "competitors" in saved["prohibited_topics"]
    assert saved["brand_safety_instructions"].startswith("Never mention")


def test_invalid_posting_day_dropped(cc):
    saved = cc.save("cA", posting_days=["mon", "moon", "fri"])
    assert saved["posting_days"] == ["mon", "fri"]


def test_invalid_time_format_dropped(cc):
    saved = cc.save("cA", posting_times=["9:00", "25:00", "18:30", "abc"])
    # "9:00" invalid (needs zero-pad or 09:00 form); regex allows [01]?\d so 9:00 IS ok
    assert "18:30" in saved["posting_times"]
    assert "25:00" not in saved["posting_times"]
    assert "abc" not in saved["posting_times"]


def test_invalid_language_falls_back_to_default(cc):
    saved = cc.save("cA", preferred_language="martian")
    assert saved["preferred_language"] == "hinglish"


# =========================================================================== #
# Loop-social-20: approval edit/replace/reschedule actions                     #
# =========================================================================== #
@pytest.fixture()
def ca(monkeypatch):
    from app.marketing import content_approval as _ca

    td = tempfile.mkdtemp()
    monkeypatch.setattr(_ca, "_FILE", lambda: os.path.join(td, "approvals.jsonl"))
    return _ca


def _submit(ca, cid="cA") -> str:
    r = ca.submit(cid, {"title": "Test", "caption": "old caption"})
    return r["approval"]["id"]


def test_edit_caption_updates_content(ca):
    aid = _submit(ca)
    r = ca.edit_caption(aid, "brand-new caption", actor="customer")
    assert r["ok"] is True
    # Latest state should reflect the new caption.
    latest = ca._latest_states()[aid]
    assert latest["content"]["caption"] == "brand-new caption"


def test_edit_caption_locked_after_publish(ca):
    aid = _submit(ca)
    ca.transition(aid, "approved")
    ca.transition(aid, "publishing")
    ca.transition(aid, "published")
    r = ca.edit_caption(aid, "too late", actor="customer")
    assert r["ok"] is False
    assert r["error"] == "edit_locked"


def test_replace_media_requires_url_or_path(ca):
    aid = _submit(ca)
    r = ca.replace_media(aid, actor="customer")
    assert r["ok"] is False
    assert r["error"] == "media_required"


def test_replace_media_rejects_bad_type(ca):
    aid = _submit(ca)
    r = ca.replace_media(aid, media_url="https://x/y.mp4", media_type="hologram", actor="customer")
    assert r["ok"] is False
    assert r["error"] == "invalid_media_type"


def test_replace_media_happy_path(ca):
    aid = _submit(ca)
    r = ca.replace_media(
        aid,
        media_url="https://cdn.example.com/new.jpg",
        media_type="image",
        actor="customer",
        note="better resolution",
    )
    assert r["ok"] is True
    latest = ca._latest_states()[aid]
    assert latest["content"]["media"]["url"] == "https://cdn.example.com/new.jpg"
    assert latest["content"]["media"]["type"] == "image"


def test_change_scheduled_time_rejects_past(ca):
    aid = _submit(ca)
    past = (datetime.datetime.utcnow() - datetime.timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    r = ca.change_scheduled_time(aid, past, actor="customer")
    assert r["ok"] is False
    assert r["error"] == "past_time"


def test_change_scheduled_time_rejects_malformed(ca):
    aid = _submit(ca)
    r = ca.change_scheduled_time(aid, "not-a-date", actor="customer")
    assert r["ok"] is False
    assert r["error"] == "invalid_iso"


def test_change_scheduled_time_happy_path(ca):
    aid = _submit(ca)
    future = (datetime.datetime.utcnow() + datetime.timedelta(hours=6)).strftime(
        "%Y-%m-%dT%H:%M:%S"
    )
    r = ca.change_scheduled_time(aid, future, tz="Asia/Kolkata", actor="customer")
    assert r["ok"] is True
    latest = ca._latest_states()[aid]
    assert latest["content"]["schedule"]["scheduled_time"] == future
    assert latest["content"]["schedule"]["timezone"] == "Asia/Kolkata"


def test_edit_after_cancel_locked(ca):
    aid = _submit(ca)
    ca.cancel(aid, actor="customer")
    r = ca.edit_caption(aid, "revive", actor="customer")
    assert r["ok"] is False
    assert r["error"] == "edit_locked"


# =========================================================================== #
# Loop-social-21: store schema fields                                          #
# =========================================================================== #
def test_store_accepts_media_assets_and_approval_status(monkeypatch, tmp_path):
    from app.social_engine import store

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)

    jid = store.enqueue(
        {
            "client_id": "cA",
            "platform": "instagram",
            "caption": "hi",
            "media_assets": [
                {"url": "https://cdn/x.jpg", "type": "image"},
                {"url": "https://cdn/y.jpg", "type": "image"},
            ],
            "approval_status": "approved",
        }
    )
    assert jid
    row = store.get(jid)
    assert isinstance(row.get("media_assets"), list)
    assert len(row["media_assets"]) == 2
    assert row["approval_status"] == "approved"


def test_store_backfills_empty_new_fields(monkeypatch, tmp_path):
    """Legacy callers without new fields still enqueue cleanly."""
    from app.social_engine import store

    monkeypatch.setattr(store, "_PATH", str(tmp_path / "jobs.jsonl"))
    monkeypatch.setattr(store, "_mirror", lambda job: None)

    jid = store.enqueue({"client_id": "cA", "platform": "facebook", "caption": "old-shape call"})
    row = store.get(jid)
    assert row.get("media_assets") == []
    assert row.get("approval_status") == ""
