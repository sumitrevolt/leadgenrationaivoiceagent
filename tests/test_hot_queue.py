"""Hot Queue (GTM Track 1) — interested/question replies ki workable daily queue."""

import json
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _seed(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    rows = [
        # a@x.com ke 2 rows — dedupe me sirf LATEST (at=..10T12) rehna chahiye
        {
            "from": "a@x.com",
            "subject": "old ping",
            "intent": "interested",
            "draft": "purana draft",
            "at": "2026-06-10T09:00:00+00:00",
        },
        {
            "from": "a@x.com",
            "subject": "price batao",
            "intent": "interested",
            "draft": "naya draft",
            "at": "2026-06-10T12:00:00+00:00",
        },
        {
            "from": "b@y.com",
            "subject": "kaise kaam karta?",
            "intent": "question",
            "draft": "demo link",
            "at": "2026-06-20T10:00:00+00:00",
        },
        {
            "from": "c@z.com",
            "subject": "newsletter",
            "intent": "other",
            "draft": "",
            "at": "2026-06-21T10:00:00+00:00",
        },
        {
            "from": "d@w.com",
            "subject": "unsub",
            "intent": "not_interested",
            "draft": "",
            "at": "2026-06-22T10:00:00+00:00",
        },
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {
            "a@x.com": {
                "phone": "9876543210",
                "business_name": "Test Gym",
                "niche": "gym",
                "city": "Mumbai",
                "emailed_at": "2026-06-01T10:00:00Z",
            },
            "b@y.com": {"emailed_at": "2026-06-02T10:00:00Z"},
        },
    )
    return ra


def test_hot_queue_filters_dedupes_and_joins(tmp_path, monkeypatch):
    ra = _seed(tmp_path, monkeypatch)
    q = ra.hot_queue()
    # other/not_interested bahar; a@x.com dedupe hoke 1
    assert [r["from"] for r in q] == ["b@y.com", "a@x.com"]  # newest-first
    a = q[1]
    assert a["subject"] == "price batao"  # latest wins in dedupe
    assert a["phone"] == "9876543210" and a["business_name"] == "Test Gym"
    assert a["hq_id"] and a["age_days"] is not None
    assert a["wa_link"].startswith("https://wa.me/919876543210?text=")
    assert parse_qs(urlparse(a["wa_link"]).query)["text"] == ["naya draft"]
    b = q[0]
    assert b["wa_link"] == ""
    assert b["phone"] == ""  # prospect map me nahi — graceful empty


def test_hot_queue_email_requires_confirmed_outreach_prospect(tmp_path, monkeypatch):
    """Vendor/system inbox mail must not masquerade as a sales reply."""
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    rows = [
        {
            "from": "real@prospect.in",
            "subject": "Re: pricing?",
            "intent": "question",
            "draft": "Namaste, pricing yahan hai.",
            "at": "2026-07-14T10:00:00+00:00",
        },
        {
            "from": "known-but-unsent@vendor.in",
            "subject": "Product onboarding complete",
            "intent": "interested",
            "draft": "Thanks.",
            "at": "2026-07-14T11:00:00+00:00",
        },
        {
            "from": "unknown@vendor.in",
            "subject": "Welcome to our service",
            "intent": "interested",
            "draft": "Thanks.",
            "at": "2026-07-14T12:00:00+00:00",
        },
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {
            "real@prospect.in": {"emailed_at": "2026-07-10T09:00:00Z"},
            "known-but-unsent@vendor.in": {"emailed_at": ""},
        },
    )

    assert [r["from"] for r in ra.hot_queue(limit=20)] == ["real@prospect.in"]


def test_hot_queue_does_not_turn_meta_ids_into_whatsapp_links(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "103723644784777",
                "channel": "whatsapp",
                "intent": "interested",
                "draft": "reply draft",
                "at": "2026-07-08T10:00:00+00:00",
            }
        )
        + "\n"
        + json.dumps(
            {
                "from": "919876543210",
                "channel": "whatsapp",
                "intent": "interested",
                "draft": "real phone draft",
                "at": "2026-07-08T11:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})

    rows = {r["from"]: r for r in ra.hot_queue(limit=10)}
    assert "103723644784777" not in rows
    assert rows["919876543210"]["wa_link"].startswith("https://wa.me/919876543210?text=")


def test_hot_queue_hides_saved_auto_ack_rows(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "auto@example.com",
                "subject": "Thank you for your interest in Example",
                "intent": "interested",
                "draft": "fake hot draft",
                "at": "2026-07-08T10:00:00+00:00",
            }
        )
        + "\n"
        + json.dumps(
            {
                "from": "real@example.com",
                "subject": "price batao",
                "intent": "interested",
                "draft": "real hot draft",
                "at": "2026-07-08T11:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {
            "auto@example.com": {"emailed_at": "2026-07-01T10:00:00Z"},
            "real@example.com": {"emailed_at": "2026-07-01T10:00:00Z"},
        },
    )

    rows = {r["from"]: r for r in ra.hot_queue(limit=10)}
    assert "auto@example.com" not in rows
    assert "real@example.com" in rows


def test_mark_handled_hides_row_and_is_idempotent(tmp_path, monkeypatch):
    ra = _seed(tmp_path, monkeypatch)
    q = ra.hot_queue()
    bid = q[0]["hq_id"]
    assert ra.mark_handled(bid) is True
    remaining = ra.hot_queue()
    assert [r["from"] for r in remaining] == ["a@x.com"]
    assert ra.mark_handled(bid) is False  # already done
    assert ra.mark_handled("nahi-hai") is False


def test_hot_queue_never_raises_on_missing_file(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(tmp_path / "ghost.jsonl"))
    assert ra.hot_queue() == []
    assert ra.mark_handled("x") is False


def test_endpoints_working(tmp_path, monkeypatch):
    # NOTE: tests/conftest.py globally mocks require_admin (line ~195) — anon-reject
    # ka real assert tests/security/ suite me hota hai (jo overrides strip karti hai).
    _seed(tmp_path, monkeypatch)
    r = client.get("/api/growth/reply/hot-queue")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True and data["count"] == 2
    hq_id = data["items"][0]["hq_id"]
    r2 = client.post("/api/growth/reply/hot-queue/done", json={"hq_id": hq_id})
    assert r2.status_code == 200 and r2.json()["ok"] is True
    r3 = client.post("/api/growth/reply/hot-queue/done", json={"hq_id": "bogus"})
    assert r3.status_code == 404
