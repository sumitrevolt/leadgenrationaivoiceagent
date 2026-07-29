"""Stage 3C adversarial proofs — provider must consume the immutable snapshot.

Red-first: every refusal path leaves provider counters at zero; the success
path permits exactly one fake-provider call with the snapshot identity.
Durable exactly-once is proven via the publish idempotency key + stored
``publish_result``, not merely a mock spy count.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.marketing.video_production import publish_gate as pg
from app.marketing.video_production import states
from app.marketing.video_production.publish_snapshot import (
    canonical_publish_identity,
    publish_idempotency_key,
)


@pytest.fixture(autouse=True)
def _gates_open(monkeypatch):
    monkeypatch.setattr(pg.flags, "production_enabled", lambda: False)
    monkeypatch.setattr(pg.flags, "social_publish_enabled", lambda: True)
    monkeypatch.setattr(pg.flags, "own_brand_enabled", lambda: False)


@pytest.fixture
def iso(tmp_path, monkeypatch):
    root = tmp_path / "video_ads"
    root.mkdir()
    monkeypatch.setattr("app.marketing.video_pipeline.output_root", lambda: str(root))
    original = root / "va_1_rev0.mp4"
    original.write_bytes(b"SNAPSHOT-BYTES" * 2048)
    digest = hashlib.sha256(original.read_bytes()).hexdigest()
    size = original.stat().st_size
    snap = root / "_approved" / "tenant1"
    snap.mkdir(parents=True)
    snap_file = snap / f"va_1.r0.{digest}.mp4"
    snap_file.write_bytes(original.read_bytes())
    return {
        "root": root,
        "original": original,
        "snap": snap_file,
        "digest": digest,
        "size": size,
    }


def _finalized(iso, **over):
    rec = {
        "id": "va_1",
        "client_id": "jiya-makeover",
        "approval_id": "ap_1",
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
        "status": "approved",
        "workflow_state": states.APPROVED,
        "video_path": str(iso["original"]),
        "approved_content_sha256": iso["digest"],
        "approved_content_bytes": iso["size"],
        "approval_txn_state": "finalized",
        "approval_txn": "a" * 64,
        "approval_snapshot_path": str(iso["snap"]),
        "approval_snapshot_sha256": iso["digest"],
        "approval_snapshot_bytes": iso["size"],
    }
    rec.update(over)
    return rec


@pytest.fixture
def publish_env(monkeypatch, iso):
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    store: dict = {"rec": _finalized(iso), "provider": 0, "uploaded": b"", "path": ""}

    def _latest():
        return {store["rec"]["id"]: store["rec"]}

    def _update(rid, **fields):
        if store["rec"].get("id") == rid:
            store["rec"].update(fields)

    async def _spy(client, caption, video_path):
        store["provider"] += 1
        store["path"] = video_path
        store["uploaded"] = Path(video_path).read_bytes()
        return {"sent": True, "post_ids": ["p1"]}

    monkeypatch.setattr(pp, "enabled", lambda: True, raising=False)
    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)
    monkeypatch.setattr(vac, "_latest", _latest)
    monkeypatch.setattr(vac, "_update", _update)
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda c: {"id": "jiya-makeover", "postiz_integrations": "c1"},
    )
    monkeypatch.setattr(
        "app.marketing.delivery_ledger.log_event",
        lambda *a, **k: True,
    )
    return store


# --- 1-2: original render mutations must not change uploaded bytes ----------


@pytest.mark.asyncio
async def test_1_original_modified_after_approval_uploads_snapshot(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    iso["original"].write_bytes(b"FAKE-ORIGINAL" * 2048)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is True
    assert publish_env["uploaded"] == iso["snap"].read_bytes()
    assert publish_env["uploaded"].startswith(b"SNAPSHOT-BYTES")
    assert publish_env["provider"] == 1


@pytest.mark.asyncio
async def test_2_original_replaced_between_gate_and_upload(iso, publish_env, monkeypatch):
    from app.marketing import video_ad_cycle as vac

    def _swap(cid):
        iso["original"].write_bytes(b"REPLACED-PATH-BYTES" * 100)
        return {"id": "jiya-makeover", "postiz_integrations": "c1"}

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", _swap)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is True
    assert publish_env["uploaded"].startswith(b"SNAPSHOT-BYTES")
    assert publish_env["path"] == str(iso["snap"])


# --- 3-6: snapshot integrity refusals --------------------------------------


@pytest.mark.asyncio
async def test_3_snapshot_modified_after_finalization_refuses(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    iso["snap"].write_bytes(b"TAMPERED-SNAP" * 2048)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out.get("provider_calls") == 0


@pytest.mark.asyncio
async def test_4_snapshot_replaced_after_gate_before_upload_refuses(iso, publish_env, monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac
    from app.marketing.video_production import publish_snapshot as ps

    real_verify = ps.verify_snapshot_descriptor
    calls = {"n": 0}

    def _verify_then_tamper(**kwargs):
        calls["n"] += 1
        out = real_verify(**kwargs)
        if calls["n"] == 1 and out.get("ok"):
            # After gate/claim verify, before provider: corrupt snapshot.
            iso["snap"].write_bytes(b"LATE-SWAP" * 2048)
        return out

    monkeypatch.setattr(ps, "verify_snapshot_descriptor", _verify_then_tamper)
    # _publish_one imports the symbol — patch module used by vac
    monkeypatch.setattr(
        "app.marketing.video_ad_cycle.verify_snapshot_descriptor",
        _verify_then_tamper,
        raising=False,
    )
    # Re-bind via publish_snapshot import path inside _publish_one
    import app.marketing.video_production.publish_snapshot as psm

    monkeypatch.setattr(psm, "verify_snapshot_descriptor", _verify_then_tamper)

    async def _should_never(*a, **k):
        publish_env["provider"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _should_never, raising=False)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_5_snapshot_missing_refuses(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    iso["snap"].unlink()
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_6_snapshot_outside_media_authority_refuses(iso, publish_env, tmp_path):
    from app.marketing import video_ad_cycle as vac

    outside = tmp_path / "escape.mp4"
    outside.write_bytes(iso["snap"].read_bytes())
    publish_env["rec"]["approval_snapshot_path"] = str(outside)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0


# --- 7-10: state / legacy / tenant refusals --------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "state",
    ["prepared", "decision_recorded", "compensated", "inconsistent", ""],
)
async def test_7_non_finalized_states_refuse(iso, publish_env, state):
    from app.marketing import video_ad_cycle as vac

    publish_env["rec"]["approval_txn_state"] = state
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out["channels"]["gate"]["error"] == "approval_not_finalized"


@pytest.mark.asyncio
async def test_8_legacy_final_approved_matching_hash_refuses(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    for k in (
        "approval_txn_state",
        "approval_txn",
        "approval_snapshot_path",
        "approval_snapshot_sha256",
        "approval_snapshot_bytes",
    ):
        publish_env["rec"].pop(k, None)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out["channels"]["gate"]["error"] == "approval_not_finalized"


@pytest.mark.asyncio
async def test_9_hash_less_legacy_cannot_publish(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    publish_env["rec"].pop("approved_content_sha256", None)
    publish_env["rec"].pop("approved_content_bytes", None)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out["channels"]["gate"]["error"] == "approval_hash_missing"


@pytest.mark.asyncio
async def test_10_unresolved_tenant_preserves_pr179(iso, publish_env, monkeypatch):
    from app.marketing import video_ad_cycle as vac

    monkeypatch.setattr("app.marketing.clients_store.resolve_client", lambda c: None)
    monkeypatch.setattr("app.marketing.clients_store.get_client", lambda c: None)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out["channels"]["tenant"]["error"] == "unresolved_tenant"
    assert publish_env["provider"] == 0


# --- 11-15: failure / idempotency / counters --------------------------------


@pytest.mark.asyncio
async def test_11_provider_failure_leaves_retryable_state(iso, publish_env, monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    async def _fail(*a, **k):
        publish_env["provider"] += 1
        return {"sent": False, "reason": "provider_down"}

    monkeypatch.setattr(pp, "publish_video", _fail, raising=False)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["rec"].get("publish_attempt_state") == "failed"
    assert publish_env["rec"].get("publish_idempotency_key")
    # Retryable: same key, not succeeded — a later call may try again.
    assert publish_env["rec"].get("status") != "published"


@pytest.mark.asyncio
async def test_12_concurrent_duplicate_claims_single_attempt(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    publish_env["rec"]["publish_attempt_state"] = "in_flight"
    identity = canonical_publish_identity(
        tenant="jiya-makeover",
        video_id="va_1",
        approval_txn="a" * 64,
        revision=0,
        snapshot_sha256=iso["digest"],
        snapshot_bytes=iso["size"],
        channel="postiz",
    )
    publish_env["rec"]["publish_idempotency_key"] = publish_idempotency_key(identity)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out["channels"]["idempotency"]["error"] == "publish_in_flight"
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_13_repeated_success_returns_evidence_without_provider(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    first = await vac._publish_one(publish_env["rec"])
    assert first["any_sent"] is True and publish_env["provider"] == 1
    # Simulate durable success on the record (publish_due would set status).
    publish_env["rec"]["status"] = "published"
    publish_env["rec"]["publish_result"] = first["channels"]
    second = await vac._publish_one(publish_env["rec"])
    assert second.get("idempotent") is True
    assert second["any_sent"] is True
    assert publish_env["provider"] == 1  # no second provider call
    assert second.get("provider_calls") == 0


@pytest.mark.asyncio
async def test_14_every_refusal_provider_counter_zero(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    publish_env["rec"].pop("approved_content_sha256", None)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out.get("provider_calls") == 0
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_15_success_exactly_one_provider_call_with_snapshot(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is True
    assert publish_env["provider"] == 1
    assert out.get("provider_calls") == 1
    assert publish_env["path"] == str(iso["snap"])
    assert publish_env["uploaded"] == iso["snap"].read_bytes()
    assert publish_env["rec"].get("publish_idempotency_key", "").startswith("vap:")
    assert publish_env["rec"].get("publish_attempt_state") == "succeeded"
