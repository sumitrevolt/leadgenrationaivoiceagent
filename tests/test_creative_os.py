"""Creative Automation OS P1 — enqueue, worker, approval, QA, budget, isolation."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from app.marketing.creative_os import flags, service
from app.marketing.creative_os.approval import (
    assert_exact_approved,
    bind_approval,
    can_publish_to_postiz,
)
from app.marketing.creative_os.assets import get_asset, register_asset, revoke_asset, sha256_file
from app.marketing.creative_os.budget import count_attempts_today, record_attempt
from app.marketing.creative_os.licence import assert_provider_allowed, is_rejected_model
from app.marketing.creative_os.providers import (
    FluxSchnellProvider,
    QwenImageProvider,
    get_provider,
    normalized_response,
)
from app.marketing.creative_os.qa import detect_optional_capabilities, run_qa
from app.marketing.creative_os.recipes import build_scene_plan
from app.marketing.creative_os.spec import CreativeSpec
from app.marketing.creative_os.states import assert_transition
from app.marketing.creative_os.store import get_record, save_record


@pytest.fixture(autouse=True)
def _isolated_roots(tmp_path, monkeypatch):
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    monkeypatch.setenv("CREATIVE_LEDGER_ROOT", str(tmp_path / "ledger"))
    monkeypatch.setenv("CREATIVE_BUDGET_ROOT", str(tmp_path / "budget"))
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_MAX_REVISIONS", "3")
    monkeypatch.setenv("CREATIVE_TENANT_DAILY_BUDGET", "20")
    monkeypatch.setenv("CREATIVE_WORKER_TIMEOUT_S", "60")
    monkeypatch.setenv("CREATIVE_OS_EAGER_WORKER", "0")
    monkeypatch.setenv("PLATFORM_DIAL_DAILY", "0")
    monkeypatch.delenv("CREATIVE_PROVIDER_QWEN_IMAGE", raising=False)
    monkeypatch.delenv("VIDEO_SOCIAL_PUBLISH_ENABLED", raising=False)
    Path("data/reels").mkdir(parents=True, exist_ok=True)
    # Default: brief gate passes so existing enqueue lifecycle tests stay focused.
    # Refuse-path coverage lives in test_enqueue_generate_brief_gate_*.
    monkeypatch.setattr(
        service,
        "resolve_brief",
        lambda **kw: {
            "ok": True,
            "outcome": "ready",
            "brief": object(),
            "missing": [],
            "reason": "",
            "error": "",
        },
    )


def _mp4(name: str = "out.mp4", size: int = 5000) -> Path:
    dest = Path("data/reels") / f"test_{name}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"x" * size)
    return dest


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
        "qa_results": {"ok": True, "checks": [], "blockers": []},
    }
    data.update(kw)
    return CreativeSpec(**data)


def _ready_spec_with_file(**kw) -> CreativeSpec:
    path = _mp4(kw.pop("fname", "ready.mp4"))
    digest = sha256_file(str(path.resolve()))
    tenant = kw.get("tenant_id", "disposable-test-tenant")
    reg = register_asset(
        tenant_id=tenant,
        source_type="generated",
        ref=str(path.resolve()),
        sha256=digest,
        mime_type="video/mp4",
        consent_status="granted",
        licence="n/a",
        model_provider="deterministic",
    )
    assert reg["ok"], reg
    kw.setdefault("status", "approval_pending")
    kw.setdefault("qa_results", {"ok": True, "checks": [], "blockers": []})
    spec = _base_spec(
        output_hash=digest,
        output_asset_id=reg["asset"]["asset_id"],
        **kw,
    )
    save_record(spec)
    return spec


def test_flags_default_off_when_unset(monkeypatch):
    monkeypatch.delenv("CREATIVE_OS_ENABLED", raising=False)
    assert flags.os_enabled() is False
    assert flags.flag_snapshot()["PLATFORM_DIAL_DAILY_HARD_OFF"] is True


def test_api_enqueues_without_rendering(monkeypatch):
    rendered = {"called": False}

    def boom(*a, **k):
        rendered["called"] = True
        raise AssertionError("renderer must not run in API process")

    monkeypatch.setattr(service, "generate_with_fallback", boom)
    monkeypatch.setattr(service, "process_generation", boom)

    def fake_enqueue(tenant_id, creative_id, revision):
        return {"ok": True, "job_id": "job-test-1", "queue": "video"}

    monkeypatch.setattr(service, "_enqueue_celery", fake_enqueue)
    out = service.enqueue_generate(
        tenant_id="disposable-test-tenant",
        business_name="Test Salon",
        recipe="offer_announcement",
        aspect_ratio="4:5",
    )
    assert out["ok"] is True
    assert out["accepted"] is True
    assert out["status"] == "queued"
    assert out["job_id"] == "job-test-1"
    assert rendered["called"] is False


def test_enqueue_generate_brief_gate_needs_customer_input(monkeypatch):
    monkeypatch.setattr(
        service,
        "resolve_brief",
        lambda **kw: {
            "ok": False,
            "outcome": "needs_customer_input",
            "brief": None,
            "missing": ["primary_color"],
            "reason": "missing_required_fields",
            "error": "missing required customer input: primary_color",
        },
    )
    called = {"n": 0}

    def boom(*a, **k):
        called["n"] += 1
        raise AssertionError("must not enqueue when brief incomplete")

    monkeypatch.setattr(service, "_enqueue_celery", boom)
    out = service.enqueue_generate(tenant_id="acme01", business_name="Acme")
    assert out["ok"] is False
    assert out["outcome"] == "needs_customer_input"
    assert "primary_color" in out["missing"]
    assert called["n"] == 0


def test_enqueue_generate_brief_gate_blocked_entitlement(monkeypatch):
    monkeypatch.setattr(
        service,
        "resolve_brief",
        lambda **kw: {
            "ok": False,
            "outcome": "blocked",
            "brief": None,
            "missing": [],
            "reason": "inactive_subscription",
            "error": "inactive subscription",
        },
    )
    monkeypatch.setattr(
        service,
        "_enqueue_celery",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no enqueue")),
    )
    out = service.enqueue_generate(tenant_id="acme01", business_name="Acme")
    assert out["ok"] is False and out["outcome"] == "blocked"
    assert out["reason"] == "inactive_subscription"


def test_enqueue_generate_binds_verified_brand_not_caller_business_name(monkeypatch):
    """Caller business_name must not leak into scenes when brief brand differs."""
    from app.marketing.creative_os.brief import BrandProfile, CustomerVideoBrief

    brand = BrandProfile(
        tenant_id="acme01",
        business_name="Acme Salon",
        niche="salon",
        primary_color="#101820",
        accent_color="#f2aa4c",
    )
    brief = CustomerVideoBrief(
        tenant_id="acme01",
        objective="salon",
        platform="instagram",
        aspect_ratio="9:16",
        language="hinglish",
        brand=brand,
        offer="Monsoon special",
        cta="Book now",
    )
    monkeypatch.setattr(
        service,
        "resolve_brief",
        lambda **kw: {
            "ok": True,
            "outcome": "ready",
            "brief": brief,
            "missing": [],
            "reason": "",
            "error": "",
        },
    )
    captured: dict = {}
    from app.marketing.creative_os import recipes as recipes_mod

    real_plan = recipes_mod.build_scene_plan

    def wrap_plan(recipe, **kw):
        captured.update(kw)
        return real_plan(recipe, **kw)

    monkeypatch.setattr(service, "build_scene_plan", wrap_plan)
    monkeypatch.setattr(
        service,
        "_enqueue_celery",
        lambda *a, **k: {"ok": True, "job_id": "job-bind", "queue": "video"},
    )
    out = service.enqueue_generate(
        tenant_id="acme01",
        business_name="Acme — sirf ₹1,299",
        niche="general",
        offer="Monsoon special",
    )
    assert out["ok"] is True
    assert captured.get("business_name") == "Acme Salon"
    assert "1299" not in str(captured.get("business_name") or "")
    assert captured.get("niche") == "salon"


def test_worker_lifecycle_and_idempotency(monkeypatch):
    path = _mp4("life.mp4")

    async def fake(spec):
        return normalized_response(
            ok=True,
            provider="deterministic",
            model="ffmpeg-template",
            assets=[{"path": str(path.resolve()), "width": 720, "height": 1280}],
            timing_ms=5,
        )

    monkeypatch.setattr(service, "generate_with_fallback", fake)
    monkeypatch.setattr(
        service,
        "run_qa",
        lambda **kw: {"ok": True, "degraded": [], "checks": [], "blockers": []},
    )
    monkeypatch.setattr(service, "_enqueue_celery", lambda *a, **k: {"ok": True, "job_id": "j1"})
    enq = service.enqueue_generate(tenant_id="disposable-test-tenant", business_name="Test Salon")
    cid = enq["creative_id"]
    out = service.process_generation("disposable-test-tenant", cid)
    assert out["ok"] is True
    assert out["status"] == "approval_pending"
    out2 = service.process_generation("disposable-test-tenant", cid)
    assert out2.get("idempotent") is True


def test_change_request_regenerates(monkeypatch):
    path1 = _mp4("v1.mp4")
    path2 = _mp4("v2.mp4", size=6000)
    paths = {"n": 0, "files": [path1, path2]}

    async def fake(spec):
        p = paths["files"][min(paths["n"], 1)]
        paths["n"] += 1
        return normalized_response(
            ok=True,
            provider="deterministic",
            model="ffmpeg-template",
            assets=[{"path": str(p.resolve()), "width": 720, "height": 1280}],
        )

    monkeypatch.setattr(service, "generate_with_fallback", fake)
    monkeypatch.setattr(
        service,
        "run_qa",
        lambda **kw: {"ok": True, "degraded": [], "checks": [], "blockers": []},
    )
    monkeypatch.setattr(
        service, "_enqueue_celery", lambda *a, **k: {"ok": True, "job_id": "j", "queue": "video"}
    )
    g = service.enqueue_generate(tenant_id="disposable-test-tenant", business_name="Test Salon")
    cid = g["creative_id"]
    assert service.process_generation("disposable-test-tenant", cid)["ok"] is True
    assert service.approve_exact("disposable-test-tenant", cid)["ok"] is True
    ch = service.request_changes("disposable-test-tenant", cid, note="longer hook")
    assert ch["ok"] is True
    assert ch["revision"] == 1
    assert ch["status"] == "queued"
    assert assert_exact_approved(cid, "disposable-test-tenant")["ok"] is False
    assert service.process_generation("disposable-test-tenant", cid)["ok"] is True
    assert int(get_record("disposable-test-tenant", cid)["record"]["approval_revision"]) == 1


def test_approval_blocked_states():
    for st in ("generating", "failed", "qa_failed", "changes_requested", "quarantined"):
        spec = _ready_spec_with_file(status=st, fname=f"{st}.mp4")
        out = bind_approval(spec)
        assert out["ok"] is False, st


def test_missing_qa_blocks_approval():
    spec = _ready_spec_with_file(fname="noqa.mp4")
    spec.qa_results = {}
    save_record(spec)
    assert bind_approval(spec)["ok"] is False


def test_quarantine_cannot_approve():
    spec = _ready_spec_with_file(fname="q.mp4")
    assert service.quarantine(spec.tenant_id, spec.creative_id, reason="bad")["ok"] is True
    assert service.approve_exact(spec.tenant_id, spec.creative_id)["ok"] is False


def test_file_mutation_blocks_publish(monkeypatch):
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    spec = _ready_spec_with_file(fname="mut.mp4")
    assert bind_approval(spec)["ok"] is True
    aid = get_record(spec.tenant_id, spec.creative_id)["record"]["spec"]["output_asset_id"]
    ref = Path(get_asset(spec.tenant_id, aid)["asset"]["ref"])
    data = bytearray(ref.read_bytes())
    data[0] = (data[0] + 1) % 256
    ref.write_bytes(bytes(data))
    assert can_publish_to_postiz(spec.tenant_id, spec.creative_id)["ok"] is False


def test_revoked_asset_blocks_approval():
    spec = _ready_spec_with_file(fname="rev.mp4")
    revoke_asset(spec.tenant_id, spec.output_asset_id)
    assert bind_approval(spec)["ok"] is False


def test_deterministic_fallback_metadata_e2e(monkeypatch):
    path = _mp4("fb.mp4")

    async def fake_det(self, spec):
        return normalized_response(
            ok=True,
            provider="deterministic",
            model="ffmpeg-template",
            assets=[{"path": str(path.resolve()), "width": 720, "height": 1280}],
        )

    monkeypatch.setattr(type(get_provider("deterministic")), "generate", fake_det)
    monkeypatch.setattr(
        service,
        "run_qa",
        lambda **kw: {"ok": True, "degraded": [], "checks": [], "blockers": []},
    )
    monkeypatch.setattr(service, "_enqueue_celery", lambda *a, **k: {"ok": True, "job_id": "j"})
    enq = service.enqueue_generate(
        tenant_id="disposable-test-tenant",
        business_name="Test Salon",
        provider="qwen_image",
    )
    out = service.process_generation("disposable-test-tenant", enq["creative_id"])
    assert out["ok"] is True
    spec = CreativeSpec.from_dict(
        get_record("disposable-test-tenant", enq["creative_id"])["record"]["spec"]
    )
    assert spec.provider == "deterministic"
    assert spec.fallback_from == "qwen_image"
    assert assert_provider_allowed(spec.provider, spec.model_name)["ok"] is True


def test_budget_counts_attempts_not_metadata():
    assert count_attempts_today("disposable-test-tenant") == 0
    record_attempt("disposable-test-tenant", creative_id="cr_1", kind="initial")
    record_attempt("disposable-test-tenant", creative_id="cr_1", kind="regeneration", revision=1)
    assert count_attempts_today("disposable-test-tenant") == 2
    save_record(_base_spec())
    assert count_attempts_today("disposable-test-tenant") == 2


def test_invalid_transition_fail_closed():
    assert assert_transition("quarantined", "approved")["ok"] is False
    assert assert_transition("queued", "generating")["ok"] is True


def test_qa_optional_not_fake_pass(tmp_path):
    caps = detect_optional_capabilities()
    assert "paddleocr" in caps
    p = tmp_path / "tiny.mp4"
    p.write_bytes(b"x")
    qa = run_qa(path=str(p), spec=_base_spec())
    assert qa["ok"] is False
    for c in qa["checks"]:
        if c["name"] in ("text_safe_zone", "brand_presence_ocr"):
            assert c["result"] in ("degraded_missing_dependency", "not_evaluated")


def test_skeleton_fail_closed():
    out = asyncio.run(QwenImageProvider().generate(_base_spec(provider="qwen_image")))
    assert out["error"] == "provider_unavailable"
    flux = asyncio.run(
        FluxSchnellProvider().generate(_base_spec(provider="flux_schnell", model_name="FLUX.1-dev"))
    )
    assert flux["ok"] is False
    assert is_rejected_model("FLUX.1-dev") is True


def test_aspect_4_5():
    from app.marketing import video_pipeline

    assert video_pipeline._ASPECT["4:5"] == (1080, 1350)


def test_calling_hard_off():
    assert os.getenv("PLATFORM_DIAL_DAILY", "0") in ("0", "", "false", "False")


def test_automation_flags_registry():
    from app.api.automation_flags import AUTOMATION_FLAGS

    assert "CREATIVE_OS_ENABLED" in AUTOMATION_FLAGS


def test_customer_view_no_paths():
    spec = _ready_spec_with_file(fname="cust.mp4")
    view = service.customer_view(spec.tenant_id, spec.creative_id)
    blob = str(view)
    assert "data/reels" not in blob
    assert view.get("ok") is True


def test_budget_concurrent_attempts(tmp_path, monkeypatch):
    import concurrent.futures

    monkeypatch.setenv("CREATIVE_BUDGET_ROOT", str(tmp_path / "budget"))
    tid = "disposable-concurrency"

    def _one(i: int):
        return record_attempt(tid, creative_id=f"cr_{i}", kind="initial")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(_one, range(20)))
    assert all(r.get("ok") for r in results)
    assert count_attempts_today(tid) == 20


def test_customer_api_tenant_isolation_and_billing_alias(monkeypatch, tmp_path):
    """JWT-derived tenant only; billing alias resolves to marketing id; cross-tenant 404."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("CREATIVE_OS_ENABLED", "1")
    monkeypatch.setenv("CREATIVE_ASSET_ROOT", str(tmp_path / "assets"))
    monkeypatch.setenv("CREATIVE_LEDGER_ROOT", str(tmp_path / "ledger"))

    from fastapi.testclient import TestClient

    from app.api.customer_auth import require_customer
    from app.main import app
    from app.marketing import clients_store

    disposable = _ready_spec_with_file(tenant_id="disposable-test-tenant", fname="iso_a.mp4")
    jiya = _ready_spec_with_file(tenant_id="jiya-makeover", fname="iso_j.mp4")

    def _canon(cid: str) -> str:
        c = (cid or "").strip()
        # Fixture-only alias ids (not live billing secrets).
        if c in ("jiya-billing-alias", "billing-alias-jiya-fixture", "jiya-makeover"):
            return "jiya-makeover"
        return c

    monkeypatch.setattr(clients_store, "canonical_client_id", _canon)

    async def _as_disposable():
        return "disposable-test-tenant"

    async def _as_jiya_alias():
        return "jiya-billing-alias"

    app.dependency_overrides[require_customer] = _as_disposable
    try:
        with TestClient(app) as c:
            r = c.get("/api/customer/creative-os")
            assert r.status_code == 200
            body = r.json()
            assert body.get("ok") is True
            ids = {x.get("creative_id") for x in (body.get("creatives") or [])}
            assert disposable.creative_id in ids
            assert jiya.creative_id not in ids
            leak = str(body)
            assert "data/reels" not in leak
            assert "model_version" not in leak
            assert "licence_snapshot" not in leak
            for item in body.get("creatives") or []:
                assert "provider" not in item
                assert "output_path" not in item
                assert "local_path" not in item

            # Cross-tenant media must 404
            r404 = c.get(
                f"/api/customer/creative-os/{jiya.creative_id}/media",
                params={"revision": 0},
            )
            assert r404.status_code == 404

        app.dependency_overrides[require_customer] = _as_jiya_alias
        with TestClient(app) as c:
            r = c.get("/api/customer/creative-os")
            assert r.status_code == 200
            body = r.json()
            ids = {x.get("creative_id") for x in (body.get("creatives") or [])}
            assert jiya.creative_id in ids
            assert disposable.creative_id not in ids
            assert clients_store.canonical_client_id("jiya-billing-alias") == "jiya-makeover"
    finally:
        app.dependency_overrides.clear()


def test_customer_creative_os_requires_auth():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/customer/creative-os")
        assert r.status_code in (401, 403)
