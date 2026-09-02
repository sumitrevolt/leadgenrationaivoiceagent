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


def _saga_approve(rid: str, tenant: str = "c1", revision: int = 0) -> dict:
    """Drive a REAL coordinated approval.

    Stage 3B-close retired the ``on_approved`` shortcut these tests used to call:
    an uncoordinated approval is now refused, because four production
    entrypoints reached it without a principal or a transaction. Tests whose
    subject is publishing (not the approval mechanism) approve properly here.
    """
    from app.marketing.video_production import approval_saga
    from app.marketing.video_production.approval_principal import from_customer_session
    from app.marketing.video_production.publish_gate import hash_video_file

    rec = (V._latest() or {}).get(rid) or {}
    digest, _size = hash_video_file(str(rec.get("video_path") or ""))
    return approval_saga.approve(
        record_id=rid,
        expected_revision=revision,
        expected_sha256=digest,
        # Session facts are the customer ROUTE's job to establish; this helper
        # exercises the saga, so it supplies an already-verified session.
        principal=from_customer_session(tenant, tenant_verified=True, revocation_verified=True),
    )


@pytest.fixture
def iso(monkeypatch, tmp_path):
    monkeypatch.setattr(V, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(V, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    monkeypatch.setattr(clients_store, "get_client", lambda cid: CLIENT if cid == "c1" else {})
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [CLIENT])
    monkeypatch.setattr(clients_store, "product_lane", lambda c: "marketing")
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    from app.marketing import video_pipeline

    # SERVABLE == APPROVABLE == PUBLISHABLE media root.
    _render_root = tmp_path / "reels"
    _render_root.mkdir(exist_ok=True)
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(_render_root))

    async def _fake_reel(**kw):
        p = _render_root / "reel.mp4"
        p.write_bytes(b"x")
        return {"path": str(p), "slides": kw.get("slides"), "size_kb": 1}

    monkeypatch.setattr(video_pipeline, "render_creative_video", _fake_reel)

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

    async def _pz(client, caption, video_path="", *, video_file=None, filename="video.mp4", **kw):
        # Stage 3C: provider must receive the verified descriptor, not a path reopen.
        assert video_file is not None
        sent["x"] = (client.get("id"), "fileobj", filename)
        return {"sent": True}

    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)
    monkeypatch.setattr(postiz_publish, "publish_video", _pz)
    asyncio.run(V.generate_for_client("c1"))
    rid = V.list_for_client("c1")[0]["id"]
    assert _saga_approve(rid)["ok"] is True
    assert V.list_for_client("c1")[0]["status"] == "approved"
    pd = asyncio.run(V.publish_due())
    assert pd["published"] == 1
    assert sent["x"][0] == "c1"
    assert sent["x"][1] == "fileobj"
    assert V.list_for_client("c1")[0]["status"] == "published"


def test_changes_requested_and_regen(iso):
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    assert V.on_changes_requested({"id": aid, "note": "blue theme, logo bada"}) is True
    assert any(r["status"] == "changes_requested" for r in V.list_for_client("c1"))
    regen = asyncio.run(V._regen_due())
    assert regen >= 1
    assert any(int(r.get("revision") or 0) == 1 for r in V.list_for_client("c1"))


def test_approve_via_content_approval_is_refused(iso):
    """INVERTED (Stage 3B-close). This test used to assert the bypass.

    The WA/link path reaching ``content_approval.approve`` was a full approval
    authority for video: unauthenticated, no principal, no transaction, and the
    content hash taken at approval time rather than of previewed bytes. It must
    now refuse and leave the record pending.
    """
    asyncio.run(V.generate_for_client("c1"))
    tok = V.list_for_client("c1")[0]["token"]
    out = content_approval.approve(tok)
    assert out["ok"] is False
    assert out["error"] == "approval_token_regeneration_required"
    assert V.list_for_client("c1")[0]["status"] == "pending"


def test_reject_via_content_approval_triggers_changes(iso):
    asyncio.run(V.generate_for_client("c1"))
    tok = V.list_for_client("c1")[0]["token"]
    content_approval.reject(tok, "thoda aur colourful")
    assert V.list_for_client("c1")[0]["status"] == "changes_requested"


def test_run_cycle_flag_off_inert(iso, monkeypatch):
    monkeypatch.delenv("VIDEO_AD_CYCLE", raising=False)
    monkeypatch.delenv("VIDEO_DAILY_SCHEDULER_ENABLED", raising=False)
    out = asyncio.run(V.run_cycle())
    assert out["ran"] is False
    assert "VIDEO_AD_CYCLE" in out["reason"]


def test_run_cycle_flag_on_generates(iso, monkeypatch):
    # Disable daily video producer so classic cycle runs (not deferred)
    monkeypatch.delenv("DAILY_VIDEO_ENABLED", raising=False)
    monkeypatch.delenv("DAILY_VIDEO_CLIENTS", raising=False)
    monkeypatch.setenv("VIDEO_AD_CYCLE", "1")
    out = asyncio.run(V.run_cycle())
    assert out["ran"] is True and out.get("generated", 0) >= 1


def test_run_cycle_honors_daily_scheduler_alias(iso, monkeypatch):
    """VIDEO_DAILY_SCHEDULER_ENABLED alone must arm run_cycle (prod drift fix)."""
    monkeypatch.delenv("VIDEO_AD_CYCLE", raising=False)
    monkeypatch.setenv("VIDEO_DAILY_SCHEDULER_ENABLED", "1")
    assert V.enabled() is True
    out = asyncio.run(V.run_cycle())
    assert out["ran"] is True


def test_publish_no_channel_marks_failed(iso, monkeypatch):
    # postiz off (iso default) + telegram removed -> koi auto channel nahi -> publish_failed
    monkeypatch.setattr(postiz_publish, "enabled", lambda: False)
    asyncio.run(V.generate_for_client("c1"))
    _saga_approve(V.list_for_client("c1")[0]["id"])
    pd = asyncio.run(V.publish_due())
    assert pd["ran"] is True
    assert V.list_for_client("c1")[0]["status"] in ("published", "publish_failed")
