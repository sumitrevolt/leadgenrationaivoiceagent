"""Creative Automation OS (ADR-143) — focused contract + isolation tests."""

from __future__ import annotations

import asyncio
import os

import pytest

from app.marketing.creative_os import flags, service
from app.marketing.creative_os.approval import (
    assert_exact_approved,
    bind_approval,
    can_publish_to_postiz,
    invalidate_on_mutation,
)
from app.marketing.creative_os.assets import (
    get_asset,
    register_asset,
    resolve_asset_ref,
    revoke_asset,
    sha256_bytes,
)
from app.marketing.creative_os.licence import assert_provider_allowed, is_rejected_model
from app.marketing.creative_os.providers import (
    FluxSchnellProvider,
    QwenImageProvider,
    generate_with_fallback,
    get_provider,
    normalized_response,
)
from app.marketing.creative_os.qa import detect_optional_capabilities, run_qa
from app.marketing.creative_os.recipes import build_scene_plan, recipe_allowed
from app.marketing.creative_os.spec import CreativeSpec, SceneSpec
from app.marketing.creative_os.store import save_record


@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    monkeypatch.setenv("CREATIVE_LEDGER_ROOT", str(tmp_path / "ledger"))
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_MAX_REVISIONS", "3")
    monkeypatch.setenv("CREATIVE_TENANT_DAILY_BUDGET", "20")
    monkeypatch.setenv("CREATIVE_WORKER_TIMEOUT_S", "60")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    monkeypatch.delenv("CREATIVE_PROVIDER_QWEN_IMAGE", raising=False)
    monkeypatch.delenv("VIDEO_SOCIAL_PUBLISH_ENABLED", raising=False)
    monkeypatch.delenv("VIDEO_PRODUCTION_ENABLED", raising=False)


def _base_spec(**kw) -> CreativeSpec:
    scenes = kw.pop("scenes", None) or build_scene_plan(
        "offer_announcement", business_name="Test Salon", offer="20% off"
    )
    data = {
        "creative_id": CreativeSpec.new_id(),
        "tenant_id": "disposable-test-tenant",
        "goal": "salon",
        "audience": "Test Salon",
        "offer": "20% off",
        "language": "hinglish",
        "platform": "instagram",
        "aspect_ratio": "9:16",
        "recipe": "offer_announcement",
        "scenes": scenes,
        "captions": {"primary": scenes[0].text},
        "cta": scenes[-1].text,
        "provider": "deterministic",
        "model_name": "ffmpeg-template",
        "model_version": "pinned",
        "status": "approval_pending",
        "output_hash": "a" * 64,
    }
    data.update(kw)
    return CreativeSpec(**data)


def test_flags_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("CREATIVE_OS_ENABLED", raising=False)
    assert flags.os_enabled() is False
    snap = flags.flag_snapshot()
    assert snap["CREATIVE_OS_ENABLED"] is False
    assert snap["CREATIVE_PROVIDER_QWEN_IMAGE"] is False
    assert snap["PLATFORM_DIAL_DAILY_HARD_OFF"] is True


def test_creativespec_validation_and_determinism():
    a = _base_spec()
    b = CreativeSpec.from_dict(a.to_dict())
    assert a.spec_hash() == b.spec_hash()
    assert a.validate() == []
    bad = _base_spec(tenant_id="!!", claims=["Guaranteed 100% results"])
    errs = bad.validate()
    assert any("tenant_id" in e for e in errs)
    assert any("prohibited" in e or "claim" in e for e in errs)


def test_recipe_determinism_and_blocked_sources():
    s1 = build_scene_plan("faq_reel", business_name="X", offer="Y")
    s2 = build_scene_plan("faq_reel", business_name="X", offer="Y")
    assert [x.text for x in s1] == [x.text for x in s2]
    assert all(isinstance(x, SceneSpec) for x in s1)
    assert recipe_allowed("before_after")["ok"] is False
    assert recipe_allowed("testimonial")["ok"] is False
    assert recipe_allowed("offer_announcement")["ok"] is True


def test_aspect_4_5_in_pipeline_map():
    from app.marketing import video_pipeline

    assert "4:5" in video_pipeline._ASPECT
    assert video_pipeline._ASPECT["4:5"] == (1080, 1350)


def test_provider_normalization_and_skeletons_fail_closed():
    r = normalized_response(ok=True, provider="deterministic", model="ffmpeg-template")
    assert set(r.keys()) >= {
        "ok",
        "provider",
        "model",
        "model_revision",
        "assets",
        "timing_ms",
        "cost_units",
        "warnings",
        "error",
    }
    out = asyncio.run(QwenImageProvider().generate(_base_spec(provider="qwen_image")))
    assert out["ok"] is False
    assert out["error"] == "provider_unavailable"
    flux = asyncio.run(
        FluxSchnellProvider().generate(_base_spec(provider="flux_schnell", model_name="FLUX.1-dev"))
    )
    assert flux["ok"] is False
    assert flux["error"] == "provider_unavailable"


def test_licence_allowlist_and_unknown_rejection():
    ok = assert_provider_allowed("deterministic", "ffmpeg-template")
    assert ok["ok"] is True
    bad = assert_provider_allowed("qwen_image", "Qwen-Image")
    assert bad["ok"] is False
    unknown = assert_provider_allowed("made_up_provider", "x")
    assert unknown["ok"] is False
    assert is_rejected_model("FLUX.1-dev") is True
    assert is_rejected_model("hunyuanvideo") is True


def test_asset_hash_tenant_isolation_and_revocation(tmp_path):
    digest = sha256_bytes(b"hello-asset")
    reg = register_asset(
        tenant_id="tenant-a",
        source_type="upload",
        ref=str(tmp_path / "a.png"),
        sha256=digest,
        mime_type="image/png",
        consent_status="granted",
        licence="owner",
    )
    assert reg["ok"] is True
    aid = reg["asset"]["asset_id"]
    assert get_asset("tenant-a", aid)["ok"] is True
    assert resolve_asset_ref("tenant-b", aid)["ok"] is False
    rev = revoke_asset("tenant-a", aid)
    assert rev["ok"] is True
    assert get_asset("tenant-a", aid)["ok"] is False


def test_exact_approval_and_mutation_invalidates():
    spec = _base_spec()
    spec.compute_input_hashes()
    save_record(spec)
    ap = bind_approval(spec, actor="test")
    assert ap["ok"] is True, ap
    gate = assert_exact_approved(spec.creative_id, spec.tenant_id)
    assert gate["ok"] is True, gate
    mut = invalidate_on_mutation(spec.tenant_id, spec.creative_id, note="change CTA")
    assert mut["ok"] is True, mut
    gate2 = assert_exact_approved(spec.creative_id, spec.tenant_id)
    assert gate2["ok"] is False


def test_qa_fail_blocks_publish_and_optional_degraded(tmp_path):
    path = tmp_path / "tiny.mp4"
    path.write_bytes(b"x")
    spec = _base_spec()
    qa = run_qa(path=str(path), spec=spec, brand_name="Test Salon")
    assert qa["ok"] is False
    caps = detect_optional_capabilities()
    assert "paddleocr" in caps
    assert qa.get("degraded") is not None


def test_revision_cap(monkeypatch):
    monkeypatch.setenv("CREATIVE_MAX_REVISIONS", "1")
    spec = _base_spec(approval_revision=1)
    save_record(spec)
    out = invalidate_on_mutation(spec.tenant_id, spec.creative_id, note="again")
    assert out["ok"] is False
    assert out["error"] == "max_revisions"


def test_tenant_budget(monkeypatch):
    monkeypatch.setenv("CREATIVE_TENANT_DAILY_BUDGET", "1")
    spec = _base_spec()
    save_record(spec)
    out = asyncio.run(
        service.generate_preview(
            tenant_id=spec.tenant_id,
            business_name="Test Salon",
            recipe="offer_announcement",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "tenant_budget_exceeded"


def test_worker_timeout(monkeypatch):
    monkeypatch.setenv("CREATIVE_WORKER_TIMEOUT_S", "1")
    monkeypatch.setattr(flags, "worker_timeout_s", lambda: 1)

    async def _slow(spec):
        await asyncio.sleep(3)
        return normalized_response(ok=True, provider="deterministic", model="ffmpeg-template")

    monkeypatch.setattr("app.marketing.creative_os.service.generate_with_fallback", _slow)
    out = asyncio.run(
        service.generate_preview(
            tenant_id="disposable-test-tenant",
            business_name="Test Salon",
            recipe="offer_announcement",
        )
    )
    assert out["ok"] is False
    assert out["error"] == "worker_timeout"


def test_postiz_only_approved_exact_and_publish_flag(monkeypatch):
    spec = _base_spec()
    save_record(spec)
    ap = bind_approval(spec)
    assert ap["ok"] is True, ap
    monkeypatch.setenv("VIDEO_PRODUCTION_ENABLED", "1")
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "0")
    gate = can_publish_to_postiz(spec.tenant_id, spec.creative_id)
    assert gate["ok"] is False, gate
    assert "VIDEO_SOCIAL_PUBLISH" in str(gate.get("error") or "")


def test_deterministic_fallback_from_skeleton(monkeypatch):
    async def _det(self, spec):
        return normalized_response(
            ok=True,
            provider="deterministic",
            model="ffmpeg-template",
            assets=[{"path": "/tmp/x.mp4", "width": 720, "height": 1280}],
        )

    monkeypatch.setattr(type(get_provider("deterministic")), "generate", _det)
    spec = _base_spec(provider="qwen_image")
    out = asyncio.run(generate_with_fallback(spec))
    assert out["ok"] is True
    assert out["provider"] == "deterministic"
    assert any("fell_back_from" in w for w in out.get("warnings") or [])


def test_generate_preview_mocked_pipeline(monkeypatch, tmp_path):
    mp4 = tmp_path / "out.mp4"
    mp4.write_bytes(b"x" * 5000)

    async def _fake(spec):
        return normalized_response(
            ok=True,
            provider="deterministic",
            model="ffmpeg-template",
            assets=[{"path": str(mp4), "width": 720, "height": 1280}],
            timing_ms=12,
        )

    monkeypatch.setattr(service, "generate_with_fallback", _fake)

    def _qa(**kwargs):
        return {
            "ok": True,
            "degraded": ["paddleocr_missing"],
            "checks": [],
            "blockers": [],
        }

    monkeypatch.setattr(service, "run_qa", _qa)
    out = asyncio.run(
        service.generate_preview(
            tenant_id="disposable-test-tenant",
            business_name="Test Salon",
            recipe="offer_announcement",
            aspect_ratio="4:5",
        )
    )
    assert out["ok"] is True
    assert out["status"] == "approval_pending"
    assert out["aspect_ratio"] == "4:5"
    assert len(out["output_hash"]) == 64
    ap = service.approve_exact("disposable-test-tenant", out["creative_id"])
    assert ap["ok"] is True
    ch = service.request_changes("disposable-test-tenant", out["creative_id"], note="longer hook")
    assert ch["ok"] is True
    assert assert_exact_approved(out["creative_id"], "disposable-test-tenant")["ok"] is False


def test_calling_remains_hard_off():
    assert os.getenv("PLATFORM_DIAL_DAILY", "0") in ("0", "", "false", "False")
    assert flags.flag_snapshot()["PLATFORM_DIAL_DAILY_HARD_OFF"] is True


def test_automation_flags_registry_contains_creative_os():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "CREATIVE_OS_ENABLED" in AUTOMATION_FLAGS
    assert "CREATIVE_PROVIDER_FLUX_SCHNELL" in AUTOMATION_FLAGS
