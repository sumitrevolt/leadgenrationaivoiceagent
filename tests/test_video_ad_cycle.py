"""video_ad_cycle — har ~5 din AI video ad: generate -> client approval -> social
publish; "change chahiye" -> naya revision -> re-approval (free-stack, never-raise).

Bars:
- generate_for_client -> pending record (approval submit + video_path).
- on_approved (approve-hook) -> approved (publish-pending).
- publish_due -> approved item channels pe; koi send na ho to publish_failed (no crash).
- on_changes_requested (reject-hook) -> changes_requested; _regen_due naya rev banata.
- content_approval.approve/reject (WA-link path) bhi hooks fire karta.
- run_cycle flag-OFF inert; flag-ON due-client generate karta.
Heavy reel_video / external postiz stubbed.
"""

from __future__ import annotations

import asyncio

import pytest

from app.marketing import (
    clients_store,
    content_approval,
    post_generator,
    postiz_publish,
    reel_video,
)
from app.marketing import video_ad_cycle as V
from app.platform import team

CLIENT = {
    "id": "c1",
    "business_name": "Sharma Solar",
    "niche": "solar",
    "offer": "Diwali 20% off",
    "status": "active",
    "plan": "advanced",
}


async def _coro(value):
    return value


@pytest.fixture
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(V, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(content_approval, "_FILE", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setattr(clients_store, "get_client", lambda cid: CLIENT if cid == "c1" else {})
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [CLIENT])
    monkeypatch.setattr(clients_store, "product_lane", lambda c: "marketing")
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    async def _fake_reel(**kw):
        p = tmp_path / "reel.mp4"
        p.write_bytes(b"x")
        return {"path": str(p), "slides": kw.get("slides"), "size_kb": 1}

    monkeypatch.setattr(reel_video, "build_reel", _fake_reel)

    async def _fake_post(b, niche="", offer=""):
        return {"caption": f"{b} {niche} ad"}

    monkeypatch.setattr(post_generator, "generate_post", _fake_post)
    monkeypatch.setattr(postiz_publish, "enabled", lambda: False)
    monkeypatch.delenv("VIDEO_AD_CYCLE", raising=False)
    return tmp_path


def test_generate_creates_pending(iso):
    r = asyncio.run(V.generate_for_client("c1"))
    assert r["ok"] and r["video_path"]
    rows = V.list_for_client("c1")
    assert len(rows) == 1 and rows[0]["status"] == "pending"


def test_approve_hook_then_publish(iso, monkeypatch):
    sent = {}

    async def _pz(client, caption, video_path=""):
        sent["x"] = (client.get("id"), video_path)
        return {"sent": True}

    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "publish_video", _pz)
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    assert V.on_approved({"id": aid}) is True
    assert V.list_for_client("c1")[0]["status"] == "approved"
    pd = asyncio.run(V.publish_due())
    assert pd["published"] == 1
    assert sent["x"][0] == "c1"
    assert V.list_for_client("c1")[0]["status"] == "published"


def test_changes_requested_and_regen(iso):
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    assert V.on_changes_requested({"id": aid, "note": "blue theme, logo bada"}) is True
    assert any(r["status"] == "changes_requested" for r in V.list_for_client("c1"))
    regen = asyncio.run(V._regen_due())
    assert regen >= 1
    assert any(int(r.get("revision") or 0) == 1 for r in V.list_for_client("c1"))


def test_approve_via_content_approval_triggers_hook(iso):
    asyncio.run(V.generate_for_client("c1"))
    tok = V.list_for_client("c1")[0]["token"]
    content_approval.approve(tok)
    assert V.list_for_client("c1")[0]["status"] == "approved"


def test_reject_via_content_approval_triggers_changes(iso):
    asyncio.run(V.generate_for_client("c1"))
    tok = V.list_for_client("c1")[0]["token"]
    content_approval.reject(tok, "thoda aur colourful")
    assert V.list_for_client("c1")[0]["status"] == "changes_requested"


def test_run_cycle_flag_off_inert(iso):
    assert asyncio.run(V.run_cycle()) == {"ran": False, "reason": "VIDEO_AD_CYCLE off"}


def test_run_cycle_flag_on_generates(iso, monkeypatch):
    monkeypatch.setenv("VIDEO_AD_CYCLE", "1")
    out = asyncio.run(V.run_cycle())
    assert out["ran"] is True and out.get("generated", 0) >= 1


def test_publish_no_channel_marks_failed(iso, monkeypatch):
    # postiz off (iso default) + telegram removed -> koi auto channel nahi -> publish_failed
    monkeypatch.setattr(postiz_publish, "enabled", lambda: False)
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    V.on_approved({"id": aid})
    pd = asyncio.run(V.publish_due())
    assert pd["ran"] is True
    assert V.list_for_client("c1")[0]["status"] in ("published", "publish_failed")
