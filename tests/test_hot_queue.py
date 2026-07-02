"""Hot Queue (GTM Track 1) — interested/question replies ki workable daily queue."""

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _seed(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    rows = [
        # a@x.com ke 2 rows — dedupe me sirf LATEST (at=..10T12) rehna chahiye
        {"from": "a@x.com", "subject": "old ping", "intent": "interested",
         "draft": "purana draft", "at": "2026-06-10T09:00:00+00:00"},
        {"from": "a@x.com", "subject": "price batao", "intent": "interested",
         "draft": "naya draft", "at": "2026-06-10T12:00:00+00:00"},
        {"from": "b@y.com", "subject": "kaise kaam karta?", "intent": "question",
         "draft": "demo link", "at": "2026-06-20T10:00:00+00:00"},
        {"from": "c@z.com", "subject": "newsletter", "intent": "other",
         "draft": "", "at": "2026-06-21T10:00:00+00:00"},
        {"from": "d@w.com", "subject": "unsub", "intent": "not_interested",
         "draft": "", "at": "2026-06-22T10:00:00+00:00"},
    ]
    f.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"a@x.com": {"phone": "9876543210", "business_name": "Test Gym",
                             "niche": "gym", "city": "Mumbai"}},
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
    b = q[0]
    assert b["phone"] == ""  # prospect map me nahi — graceful empty


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
