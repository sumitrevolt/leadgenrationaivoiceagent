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


def _principal(tenant: str):
    """Server-created principal, same helper the customer route uses."""
    from app.marketing.video_production.approval_principal import from_customer_session

    return from_customer_session(tenant, tenant_verified=True, revocation_verified=True)


def test_flags_default_off(monkeypatch):
    for k in (
        "VIDEO_PRODUCTION_ENABLED",
        "VIDEO_DAILY_SCHEDULER_ENABLED",
        "VIDEO_CUSTOMER_REVIEW_ENABLED",
        "VIDEO_CUSTOMER_REVIEW_CLIENTS",
        "VIDEO_WHATSAPP_REVIEW_ENABLED",
        "VIDEO_SOCIAL_PUBLISH_ENABLED",
        "VIDEO_HARNESS_ENFORCE",
        "VIDEO_HARNESS_SHADOW_ENABLED",
        "VIDEO_OWN_BRAND_ENABLED",
        "VIDEO_AD_CYCLE",
    ):
        monkeypatch.delenv(k, raising=False)
    snap = flag_snapshot()
    assert snap["VIDEO_PRODUCTION_ENABLED"] is False
    assert snap["VIDEO_CUSTOMER_REVIEW_ENABLED"] is False
    assert snap["VIDEO_CUSTOMER_REVIEW_CLIENTS_CONFIGURED"] is False
    assert snap["VIDEO_WHATSAPP_REVIEW_ENABLED"] is False
    assert snap["VIDEO_HARNESS_ENFORCE"] is False
    assert snap["VIDEO_HARNESS_SHADOW_ENABLED"] is False
    assert snap["stage1_shadow_active"] is False


def test_customer_review_requires_explicit_tenant_allowlist(monkeypatch):
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.delenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", raising=False)
    assert flags.customer_review_allowed("tenant-a") is False
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", " tenant-a,tenant-b ")
    assert flags.customer_review_allowed("TENANT-A") is True
    assert flags.customer_review_allowed("tenant-c") is False
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", "*")
    assert flags.customer_review_allowed("tenant-c") is True


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


def test_state_transitions_and_publish_gate(monkeypatch, tmp_path):
    from app.marketing import video_pipeline
    from app.marketing.video_production.publish_gate import hash_video_file

    # Publish-eligible means the artifact really exists under the configured
    # media root (SERVABLE == APPROVABLE == PUBLISHABLE).
    root = tmp_path / "reels"
    root.mkdir()
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(root))
    artifact = root / "x.mp4"
    artifact.write_bytes(b"real-bytes" * 64)
    digest, size = hash_video_file(str(artifact))

    assert states.can_transition(states.RENDERED, states.INTERNAL_QA)
    assert not states.can_transition(states.CLIENT_REVIEW_PENDING, states.PUBLISHED)
    rec = {
        "status": "pending",
        "workflow_state": states.CLIENT_REVIEW_PENDING,
        "approval_id": "a1",
        "video_path": "data/video_ads/x.mp4",  # writer-contract shape
    }
    ok, reason = states.publish_allowed(rec)
    assert ok is False and "publish_blocked" in reason

    approved = {
        "status": "approved",
        "workflow_state": states.APPROVED,
        "approval_id": "a1",
        "video_path": str(artifact),
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
        "approved_content_sha256": digest,
        "approved_content_bytes": size,
        # Stage 3B-close: publish eligibility requires a finalized saga-owned
        # snapshot identity. Without it this record is exactly the legacy shape
        # an uncoordinated writer produced, and it must refuse.
        "approval_txn_state": "finalized",
        "approval_txn": "t" * 64,
        "approval_snapshot_path": str(artifact),
        "approval_snapshot_sha256": digest,
        "approval_snapshot_bytes": size,
    }
    gate = assert_can_publish(approved)
    assert gate["ok"] is True

    uncoordinated = {k: v for k, v in approved.items() if not k.startswith("approval_txn")}
    assert assert_can_publish(uncoordinated)["error"] == "approval_not_finalized"

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
    who = _principal("c1")
    bad = approve_version(r["id"], expected_revision=99, principal=who)
    assert bad["ok"] is False and bad["error"] == "version_mismatch"
    good = approve_version(r["id"], expected_revision=0, principal=who)
    assert good.get("ok") is True
    rows = V.list_for_client("c1")
    assert rows[0]["status"] == "approved"
    assert rows[0].get("approved_version") == 0
    assert rows[0].get("final_approved") is True


def test_approve_version_never_flips_an_already_rejected_approval(iso_video):
    from app.marketing import content_approval
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import states

    r = asyncio.run(V.generate_for_client("c1"))
    assert r["ok"]
    token = r["approval"]["token"]
    assert content_approval.reject(token, "not this version")["ok"] is True

    # Simulate a stale video projection while the approval ledger is already terminal.
    V._update(
        r["id"],
        status="pending",
        workflow_state=states.CLIENT_REVIEW_PENDING,
        final_approved=False,
    )
    # A VALID principal is supplied deliberately: the point of this test is
    # reject terminality, and an identity refusal would mask whether the
    # terminality check still runs.
    out = approve_version(r["id"], expected_revision=0, principal=_principal("c1"))
    assert out["ok"] is False
    assert out["error"] == "approval_already_decided"
    rec = next(row for row in V.list_all() if row["id"] == r["id"])
    assert rec.get("approved_version") is None
    assert rec.get("final_approved") is False


def test_approve_version_does_not_infer_missing_binding_as_revision_zero(iso_video):
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import states

    V._append(
        {
            "id": "legacy-approved-without-binding",
            "client_id": "c1",
            "status": "approved",
            "workflow_state": states.APPROVED,
            "revision": 0,
            "approved_version": None,
            "final_approved": True,
        }
    )
    out = approve_version("legacy-approved-without-binding", expected_revision=0)
    assert out["ok"] is False
    assert out["error"] == "video_review_not_pending"


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
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    monkeypatch.setattr(clients_store, "get_client", lambda cid: CLIENT if cid == "c1" else {})
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [CLIENT])
    monkeypatch.setattr(clients_store, "product_lane", lambda c: "marketing")
    monkeypatch.setattr(team, "log_event", lambda *a, **k: None)

    # SERVABLE == APPROVABLE == PUBLISHABLE media root: the fake renderer must
    # write where the real one does, or the artifact is unservable by contract.
    _render_root = tmp_path / "reels"
    _render_root.mkdir(exist_ok=True)
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(_render_root))

    async def _fake_reel(**kw):
        p = _render_root / "reel.mp4"
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


def test_wa_inbound_requires_whatsapp_flag(monkeypatch, iso_video):
    """VIDEO_PRODUCTION_ENABLED alone must NOT enable WA ingest."""
    from app.marketing.video_production import review_whatsapp

    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.delenv("VIDEO_WHATSAPP_REVIEW_ENABLED", raising=False)
    out = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "mid1")
    assert out.get("handled") is False
    assert "VIDEO_WHATSAPP_REVIEW_ENABLED" in str(out.get("reason") or "")


def test_wa_inbound_multi_tenant_phone_refuses(monkeypatch, iso_video):
    from app.marketing import clients_store
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import review_whatsapp

    monkeypatch.setenv("VIDEO_WHATSAPP_REVIEW_ENABLED", "1")
    c1 = {
        "id": "c1",
        "business_name": "A",
        "phone": "9876543210",
        "status": "active",
        "niche": "solar",
        "offer": "x",
    }
    c2 = {
        "id": "c2",
        "business_name": "B",
        "phone": "9876543210",
        "status": "active",
        "niche": "salon",
        "offer": "y",
    }
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [c1, c2])
    monkeypatch.setattr(
        clients_store, "get_client", lambda cid: c1 if cid == "c1" else (c2 if cid == "c2" else {})
    )
    asyncio.run(V.generate_for_client("c1"))
    out = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "mid2")
    assert out.get("reason") == "phone_ambiguous_multi_tenant"
    assert out.get("intent") == "ambiguous"
    # Must not have approved
    assert V.list_for_client("c1")[0]["status"] == "pending"


def test_wa_inbound_phone_bind_mismatch(monkeypatch, iso_video):
    from app.marketing import clients_store
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import review_whatsapp

    monkeypatch.setenv("VIDEO_WHATSAPP_REVIEW_ENABLED", "1")
    c1 = {
        "id": "c1",
        "business_name": "A",
        "phone": "9876543210",
        "status": "active",
        "niche": "solar",
        "offer": "x",
    }
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [c1])
    monkeypatch.setattr(clients_store, "get_client", lambda cid: c1 if cid == "c1" else {})
    asyncio.run(V.generate_for_client("c1"))
    rid = V.list_for_client("c1")[0]["id"]
    V._update(rid, review_phone="9111111111")
    out = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "mid3")
    assert out.get("handled") is False
    assert out.get("reason") in ("no_pending_review", "phone_mismatch")


def test_wa_inbound_reject_is_terminal_and_not_regenerated(monkeypatch, iso_video):
    from app.marketing import clients_store
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import review_whatsapp, states

    monkeypatch.setenv("VIDEO_WHATSAPP_REVIEW_ENABLED", "1")
    c1 = {
        "id": "c1",
        "business_name": "A",
        "phone": "9876543210",
        "status": "active",
        "niche": "solar",
        "offer": "x",
    }
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [c1])
    monkeypatch.setattr(clients_store, "get_client", lambda cid: c1 if cid == "c1" else {})
    made = asyncio.run(V.generate_for_client("c1"))
    assert made["ok"] is True

    out = review_whatsapp.ingest_inbound("919876543210", "REJECT", "mid-reject")
    assert out.get("handled") is True and out.get("intent") == "reject"
    rec = next(row for row in V.list_all() if row["id"] == made["id"])
    assert rec["status"] == "held_max_revisions"
    assert rec["workflow_state"] == states.CLIENT_REJECTED
    assert rec["final_approved"] is False
    assert asyncio.run(V._regen_due()) == 0


def test_wa_inbound_never_reports_approve_for_rejected_ledger(monkeypatch, iso_video):
    from app.marketing import clients_store, content_approval
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import review_whatsapp, states

    monkeypatch.setenv("VIDEO_WHATSAPP_REVIEW_ENABLED", "1")
    c1 = {
        "id": "c1",
        "business_name": "A",
        "phone": "9876543210",
        "status": "active",
        "niche": "solar",
        "offer": "x",
    }
    monkeypatch.setattr(clients_store, "list_clients", lambda status=None: [c1])
    monkeypatch.setattr(clients_store, "get_client", lambda cid: c1 if cid == "c1" else {})
    made = asyncio.run(V.generate_for_client("c1"))
    assert content_approval.reject(made["approval"]["token"], "no")["ok"] is True
    V._update(
        made["id"],
        status="pending",
        workflow_state=states.CLIENT_REVIEW_PENDING,
        final_approved=False,
    )

    out = review_whatsapp.ingest_inbound("919876543210", "APPROVE", "mid-stale")
    assert out.get("handled") is False
    # COVERAGE SHIFT (Stage 3B), recorded rather than silently re-baselined:
    # WhatsApp now fails at the identity boundary, so it can no longer reach
    # the reject-terminality check and the reason changed. The invariant this
    # test exists for — WA never reports approve for a terminal ledger, and
    # writes nothing — still holds and is asserted below. Terminality itself is
    # proven with a valid principal in
    # test_approve_version_never_flips_an_already_rejected_approval.
    assert out.get("reason") == "whatsapp_approval_identity_unavailable"
    assert out.get("intent") == "approve"
    rec = next(row for row in V.list_all() if row["id"] == made["id"])
    assert rec.get("approved_version") is None
    assert rec.get("final_approved") is False


def test_publish_gate_exception_fail_closed_when_cell_on(monkeypatch, iso_video):
    from app.marketing import postiz_publish
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    asyncio.run(V.generate_for_client("c1"))
    aid = V.list_for_client("c1")[0]["approval_id"]
    V.on_approved({"id": aid})

    def _boom(_rec):
        raise RuntimeError("simulated gate crash")

    monkeypatch.setattr(publish_gate, "assert_can_publish", _boom)
    monkeypatch.setattr(postiz_publish, "enabled", lambda: True)

    async def _pz(*a, **k):
        return {"sent": True}

    monkeypatch.setattr(postiz_publish, "publish_video", _pz)
    pd = asyncio.run(V.publish_due())
    assert pd.get("published", 0) == 0
