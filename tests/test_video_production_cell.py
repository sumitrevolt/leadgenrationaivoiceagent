"""Video Production Cell — state machine, feedback, publish gate, harness tools."""

from __future__ import annotations

import asyncio

import pytest

from app.agents.harness.registry import REGISTRY, RiskLane
from app.marketing.video_production import (
    assert_can_publish,
    classify_feedback,
    create_daily_brief,
    flag_snapshot,
    flags,
    states,
    write_script,
)
from app.marketing.video_production.cell import approve_version, ops_summary
from app.marketing.video_production.profiles import ratios_for_channels, resolve_profile


def test_flags_default_off(monkeypatch):
    for k in (
        "VIDEO_PRODUCTION_ENABLED",
        "VIDEO_DAILY_SCHEDULER_ENABLED",
        "VIDEO_WHATSAPP_REVIEW_ENABLED",
        "VIDEO_SOCIAL_PUBLISH_ENABLED",
        "VIDEO_HARNESS_ENFORCE",
        "VIDEO_OWN_BRAND_ENABLED",
        "VIDEO_AD_CYCLE",
    ):
        monkeypatch.delenv(k, raising=False)
    snap = flag_snapshot()
    assert snap["VIDEO_PRODUCTION_ENABLED"] is False
    assert snap["VIDEO_WHATSAPP_REVIEW_ENABLED"] is False
    assert snap["VIDEO_HARNESS_ENFORCE"] is False


def test_feedback_approve_changes_reject_ambiguous():
    assert classify_feedback("APPROVE")["intent"] == "approve"
    assert classify_feedback("Video theek hai, post kar do")["intent"] == "approve"
    ch = classify_feedback("Logo bada karo aur music change karo")
    assert ch["intent"] == "changes"
    assert "branding" in ch["categories"] or "music" in ch["categories"]
    assert classify_feedback("REJECT")["intent"] == "reject"
    amb = classify_feedback("theek")
    assert amb["intent"] == "ambiguous" and amb["ambiguous"] is True
    assert classify_feedback("👍")["intent"] == "ambiguous"
    assert classify_feedback("looks okay")["intent"] == "ambiguous"
    price = classify_feedback("Price ₹999 nahi ₹1299 hai")
    assert price["intent"] == "changes"
    assert "pricing" in price["categories"]


def test_state_transitions_and_publish_gate():
    assert states.can_transition(states.RENDERED, states.INTERNAL_QA)
    assert not states.can_transition(states.CLIENT_REVIEW_PENDING, states.PUBLISHED)
    rec = {
        "status": "pending",
        "workflow_state": states.CLIENT_REVIEW_PENDING,
        "approval_id": "a1",
        "video_path": "/tmp/x.mp4",
    }
    ok, reason = states.publish_allowed(rec)
    assert ok is False and "publish_blocked" in reason

    approved = {
        "status": "approved",
        "workflow_state": states.APPROVED,
        "approval_id": "a1",
        "video_path": "/tmp/x.mp4",
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
    }
    gate = assert_can_publish(approved)
    assert gate["ok"] is True

    mismatch = {**approved, "approved_version": 1}
    assert assert_can_publish(mismatch)["ok"] is False


def test_brief_script_no_fabricated_offer(monkeypatch):
    from app.marketing import clients_store

    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda cid: (
            {"id": cid, "business_name": "Fixture Salon", "niche": "salon", "offer": ""}
            if cid == "fixture-tenant-a"
            else {}
        ),
    )
    brief = create_daily_brief("fixture-tenant-a")
    assert brief["ok"]
    assert brief["brief"]["offer_missing"] is True
    script = write_script(brief["brief"])
    assert script["ok"]
    assert script["script"]["fabricated_claims"] is False
    assert "₹" not in script["script"]["body"] or "999" not in script["script"]["body"]


def test_aspect_profiles():
    assert resolve_profile("9:16")["width"] == 720
    assert resolve_profile("1:1") == {
        "width": 1080,
        "height": 1080,
        "label": "square_feed",
        "platforms": ("ig_feed", "fb_feed"),
    }
    assert ratios_for_channels([]) == ["9:16"]
    assert "1:1" in ratios_for_channels(["ig_feed", "postiz"])


def test_harness_video_tools_registered():
    # Import package ensures registration
    import app.marketing.video_production  # noqa: F401

    t = REGISTRY.resolve("video.brief.create")
    assert t is not None and t.risk_class is RiskLane.GREEN
    pub = REGISTRY.resolve("video.social.schedule")
    assert pub is not None and pub.risk_class is RiskLane.AMBER and pub.requires_approval
    ev = REGISTRY.evaluate_action(
        tool_name="video.social.schedule",
        tool_version="1.0.0",
        arguments={"video_ad_id": "abc"},
        agent_id="zara",
        tenant_id="fixture-tenant-a",
        idempotency_key="idem-1",
        claimed_risk=RiskLane.AMBER,
    )
    assert ev["would_require_approval"] is True
    deny = REGISTRY.evaluate_action(
        tool_name="video.social.schedule",
        tool_version="1.0.0",
        arguments={"video_ad_id": "abc"},
        agent_id="swara",
        tenant_id="fixture-tenant-a",
        idempotency_key="idem-1",
        claimed_risk=RiskLane.AMBER,
    )
    assert deny["would_deny"] is True


def test_approve_version_mismatch(iso_video):
    from app.marketing import video_ad_cycle as V

    r = asyncio.run(V.generate_for_client("c1"))
    assert r["ok"]
    bad = approve_version(r["id"], expected_revision=99)
    assert bad["ok"] is False and bad["error"] == "version_mismatch"
    good = approve_version(r["id"], expected_revision=0)
    assert good.get("ok") is True
    rows = V.list_for_client("c1")
    assert rows[0]["status"] == "approved"
    assert rows[0].get("approved_version") == 0
    assert rows[0].get("final_approved") is True


def test_ops_summary(iso_video):
    from app.marketing import video_ad_cycle as V

    asyncio.run(V.generate_for_client("c1"))
    s = ops_summary("c1")
    assert s["ok"] and s["count"] >= 1
    assert "flags" in s


def test_production_publish_flag_blocks(monkeypatch, iso_video):
    from app.marketing import postiz_publish
    from app.marketing import video_ad_cycle as V

    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.delenv("VIDEO_SOCIAL_PUBLISH_ENABLED", raising=False)
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    V.on_approved({"id": aid})
    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)

    async def _pz(*a, **k):
        return {"sent": True}

    monkeypatch.setattr(postiz_publish, "publish_video", _pz)
    pd = asyncio.run(V.publish_due())
    # Gate should block — no successful publish
    assert pd.get("published", 0) == 0


@pytest.fixture
def iso_video(monkeypatch, tmp_path):
    from app.marketing import video_ad_cycle as V
    from app.platform import team

    from app.marketing import (  # isort: skip
        clients_store,
        content_approval,
        post_generator,
        postiz_publish,
        video_pipeline,
    )

    CLIENT = {
        "id": "c1",
        "business_name": "Sharma Solar",
        "niche": "solar",
        "offer": "Diwali 20% off",
        "status": "active",
        "plan": "advanced",
    }
    monkeypatch.setattr(V, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(V, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(content_approval, "_FILE", str(tmp_path / "approvals.jsonl"))
    monkeypatch.setattr(clients_store, "get_client", lambda cid: CLIENT if cid == "c1" else {})
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [CLIENT])
    monkeypatch.setattr(clients_store, "product_lane", lambda c: "marketing")
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    async def _fake_reel(**kw):
        p = tmp_path / "reel.mp4"
        p.write_bytes(b"x" * 2000)
        return {"path": str(p), "slides": kw.get("slides"), "size_kb": 2}

    monkeypatch.setattr(video_pipeline, "render_creative_video", _fake_reel)

    async def _fake_post(b, niche="", offer=""):
        return {"caption": f"{b} {niche} ad"}

    monkeypatch.setattr(post_generator, "generate_post", _fake_post)
    monkeypatch.setattr(postiz_publish, "enabled", lambda: False)
    monkeypatch.delenv("VIDEO_AD_CYCLE", raising=False)
    monkeypatch.delenv("VIDEO_PRODUCTION_ENABLED", raising=False)
    return tmp_path


def test_cross_tenant_video_list_isolation(iso_video, monkeypatch):
    from app.marketing import clients_store
    from app.marketing import video_ad_cycle as V

    asyncio.run(V.generate_for_client("c1"))
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: cid)
    rows_other = V.list_for_client("other-tenant")
    assert rows_other == []
    rows = V.list_for_client("c1")
    assert len(rows) == 1
