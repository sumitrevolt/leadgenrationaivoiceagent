"""Boss unclear → LLM Council decide (Hot Queue + content approvals)."""

from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_parse_council_action_hq():
    from app.platform.boss_council import parse_council_action

    text = """
Kuch analysis...
ACTION: PARK_ADMIN
CONFIDENCE: high
WHY: injection-flag + unclear offer
NEXT: Admin draft rewrite kare
"""
    p = parse_council_action(text, allowed=frozenset({"DONE", "PARK_ADMIN", "KEEP", "CALL"}))
    assert p["action"] == "PARK_ADMIN"
    assert p["confidence"] == "high"
    assert "injection" in p["why"].lower() or "unclear" in p["why"].lower()


def test_parse_council_action_unknown_falls_back_keep():
    from app.platform.boss_council import parse_council_action

    p = parse_council_action(
        "ACTION: DELETE_EVERYTHING\nCONFIDENCE: high", allowed=frozenset({"KEEP", "DONE"})
    )
    assert p["action"] == "KEEP"


def test_park_for_admin_moves_to_admin_scope(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "a@x.com",
                "subject": "price?",
                "intent": "interested",
                "draft": "draft",
                "at": "2026-07-10T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"a@x.com": {"emailed_at": "2026-07-01T10:00:00Z", "phone": "9876543210"}},
    )
    q = ra.hot_queue(scope="boss")
    assert len(q) == 1
    hq_id = q[0]["hq_id"]
    assert ra.park_for_admin(hq_id, note="unclear") is True
    assert ra.hot_queue(scope="boss") == []
    admin = ra.hot_queue(scope="admin")
    assert len(admin) == 1 and admin[0]["hq_id"] == hq_id


def test_decide_hot_queue_applies_park(monkeypatch, tmp_path):
    from app.platform import boss_council
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "a@x.com",
                "subject": "price?",
                "intent": "interested",
                "draft": "draft",
                "at": "2026-07-10T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"a@x.com": {"emailed_at": "2026-07-01T10:00:00Z", "phone": "9876543210"}},
    )

    async def fake_council(q):
        return {
            "ok": True,
            "stage3": {
                "response": "ACTION: PARK_ADMIN\nCONFIDENCE: medium\nWHY: unclear\nNEXT: admin check"
            },
            "metadata": {"members_used": 2},
        }

    monkeypatch.setattr(boss_council, "_run_council", fake_council)
    hq_id = ra.hot_queue(scope="boss")[0]["hq_id"]
    out = asyncio.run(boss_council.decide_hot_queue(hq_id, apply=True))
    assert out["ok"] is True
    assert out["decision"]["action"] == "PARK_ADMIN"
    assert out["applied"] is True
    assert ra.hot_queue(scope="admin")


def test_escalate_for_client_flags_needs_admin(tmp_path, monkeypatch):
    from app.marketing import content_approval as ca

    monkeypatch.setattr(ca, "_FILE", lambda: str(tmp_path / "approvals.jsonl"), raising=False)
    sub = ca.submit("c1", {"title": "Offer", "caption": "50% off today"})
    assert sub.get("ok")
    aid = sub["approval"]["id"]
    esc = ca.escalate_for_client("c1", aid, note="boss unclear")
    assert esc.get("ok") is True
    pend = ca.pending("c1")
    assert len(pend) == 1
    assert pend[0].get("needs_admin") is True


def test_hot_queue_park_and_council_routes_registered():
    from app.api import customer_dashboard as cd
    from app.api import growth

    gpaths = [getattr(r, "path", "") for r in growth.router.routes]
    assert gpaths.count("/growth/reply/hot-queue/park") == 1
    assert gpaths.count("/growth/reply/hot-queue/council-decide") == 1
    cpaths = [getattr(r, "path", "") for r in cd.router.routes]
    assert cpaths.count("/api/customer/approvals/{approval_id}/council-decide") == 1


def test_hot_queue_park_endpoint(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text(
        json.dumps(
            {
                "from": "a@x.com",
                "subject": "hi",
                "intent": "interested",
                "draft": "x",
                "at": "2026-07-10T12:00:00+00:00",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(
        ra,
        "_full_prospect_map",
        lambda: {"a@x.com": {"emailed_at": "2026-07-01T10:00:00Z"}},
    )
    hq_id = ra.hot_queue()[0]["hq_id"]
    r = client.post("/api/growth/reply/hot-queue/park", json={"hq_id": hq_id, "note": "x"})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert client.get("/api/growth/reply/hot-queue?scope=boss").json()["count"] == 0
    assert client.get("/api/growth/reply/hot-queue?scope=admin").json()["count"] == 1
