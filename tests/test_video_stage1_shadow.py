"""Stage 1 video shadow harness — posture, matrix, isolation, rollback."""

from __future__ import annotations

import os

import pytest

from app.agents.harness.registry import REGISTRY, RiskLane
from app.marketing.video_production import flags
from app.marketing.video_production.shadow import (
    apply_stage1_env,
    counters,
    reset_counters,
    rollback_stage1_env,
    run_shadow_matrix,
)


@pytest.fixture(autouse=True)
def _clean_video_flags(monkeypatch):
    for k in (
        "VIDEO_PRODUCTION_ENABLED",
        "VIDEO_HARNESS_SHADOW_ENABLED",
        "VIDEO_HARNESS_ENFORCE",
        "VIDEO_DAILY_SCHEDULER_ENABLED",
        "VIDEO_CUSTOMER_REVIEW_ENABLED",
        "VIDEO_WHATSAPP_REVIEW_ENABLED",
        "VIDEO_SOCIAL_PUBLISH_ENABLED",
        "VIDEO_OWN_BRAND_ENABLED",
        "VIDEO_AD_CYCLE",
    ):
        monkeypatch.delenv(k, raising=False)
    yield
    rollback_stage1_env()


def test_customer_review_not_implied_by_production(monkeypatch):
    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.delenv("VIDEO_CUSTOMER_REVIEW_ENABLED", raising=False)
    assert flags.production_enabled() is True
    assert flags.customer_review_enabled() is False


def test_stage1_posture(monkeypatch):
    apply_stage1_env()
    snap = flags.flag_snapshot()
    assert snap["stage1_shadow_active"] is True
    assert snap["VIDEO_HARNESS_SHADOW_ENABLED"] is True
    assert snap["VIDEO_HARNESS_ENFORCE"] is False
    assert snap["VIDEO_WHATSAPP_REVIEW_ENABLED"] is False
    assert snap["VIDEO_SOCIAL_PUBLISH_ENABLED"] is False
    assert snap["VIDEO_CUSTOMER_REVIEW_ENABLED"] is False
    assert snap["VIDEO_OWN_BRAND_ENABLED"] is False


def test_shadow_matrix_zero_side_effects():
    import app.marketing.video_production  # noqa: F401

    report = run_shadow_matrix(write_report=False)
    assert report["ok"] is True
    assert report["side_effect_zero"] is True
    c = report["counters"]
    assert c["whatsapp_outbound_attempts"] == 0
    assert c["whatsapp_inbound_mutations"] == 0
    assert c["postiz_api_attempts"] == 0
    assert c["social_publishes"] == 0
    assert c["customer_approval_mutations"] == 0
    assert c["jiya_records_touched"] == 0
    assert c["shadow_failures"] == 0
    assert not report["mismatches"]


def test_shadow_matrix_idempotent_repeat():
    import app.marketing.video_production  # noqa: F401

    a = run_shadow_matrix(write_report=False)
    b = run_shadow_matrix(write_report=False)
    assert a["ok"] and b["ok"]
    assert a["input_hash"] == b["input_hash"]
    assert a["counters"]["shadow_runs"] == b["counters"]["shadow_runs"]


def test_rollback_drill():
    apply_stage1_env()
    assert flags.stage1_shadow_active() is True
    rollback_stage1_env()
    snap = flags.flag_snapshot()
    assert snap["VIDEO_PRODUCTION_ENABLED"] is False
    assert snap["VIDEO_HARNESS_SHADOW_ENABLED"] is False
    assert snap["stage1_shadow_active"] is False


def test_publish_blocked_when_social_off_cell_on(monkeypatch):
    from app.marketing.video_production import states
    from app.marketing.video_production.publish_gate import assert_can_publish

    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "0")
    rec = {
        "status": "approved",
        "workflow_state": states.APPROVED,
        "approval_id": "a1",
        "video_path": "fixture.mp4",
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
    }
    gate = assert_can_publish(rec)
    assert gate["ok"] is False
    assert "VIDEO_SOCIAL_PUBLISH_ENABLED" in str(gate.get("error") or "")


def test_harness_video_tools_shadow_eval_no_execute():
    import app.marketing.video_production  # noqa: F401

    apply_stage1_env()
    reset_counters()
    ev = REGISTRY.evaluate_action(
        tool_name="video.review.whatsapp_send",
        tool_version="1.0.0",
        arguments={"video_ad_id": "v1", "client_id": "fixture-tenant-a"},
        agent_id="isha",
        tenant_id="fixture-tenant-a",
        idempotency_key="shadow-wa-1",
        claimed_risk=RiskLane.AMBER,
    )
    assert ev.get("would_require_approval") is True
    assert "executed" not in ev or ev.get("executed") is not True
    assert counters()["whatsapp_outbound_attempts"] == 0


def test_own_brand_allowlist_denies_customer(monkeypatch):
    from app.marketing.video_production.allowlist import assert_own_brand_allowlist

    monkeypatch.setenv("VIDEO_OWN_BRAND_ENABLED", "1")
    denied = assert_own_brand_allowlist("jiya-makeover")
    assert denied["ok"] is False
    assert denied["error"] == "own_brand_allowlist_denied"
    ok = assert_own_brand_allowlist("leadgenai-self")
    assert ok["ok"] is True


def test_own_brand_allowlist_noop_when_flag_off(monkeypatch):
    from app.marketing.video_production.allowlist import assert_own_brand_allowlist

    monkeypatch.delenv("VIDEO_OWN_BRAND_ENABLED", raising=False)
    assert assert_own_brand_allowlist("jiya-makeover")["ok"] is True
