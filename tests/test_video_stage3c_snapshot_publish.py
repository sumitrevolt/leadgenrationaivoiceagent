"""Stage 3C adversarial proofs — provider streams a verified snapshot descriptor.

Red-first: every refusal path leaves provider counters at zero; the success
path permits exactly one fake-provider call reading the already-open fd.
Local reservation is durable; external exactly-once is NOT claimed (Postiz
has no documented provider idempotency key).
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import pytest

from app.marketing.video_production import publish_gate as pg
from app.marketing.video_production import publish_snapshot as ps
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

    store: dict = {
        "rec": _finalized(iso),
        "provider": 0,
        "uploaded": b"",
        "path_reopen": 0,
        "used_fileobj": False,
    }

    def _latest():
        return {store["rec"]["id"]: store["rec"]}

    def _update(rid, **fields):
        if store["rec"].get("id") == rid:
            store["rec"].update(fields)
        return True

    async def _spy(client, caption, video_path="", *, video_file=None, filename="video.mp4", **kw):
        store["provider"] += 1
        if video_file is None:
            # Path reopen is a Stage 3C contract failure.
            store["path_reopen"] += 1
            store["uploaded"] = Path(video_path).read_bytes() if video_path else b""
        else:
            store["used_fileobj"] = True
            video_file.seek(0)
            store["uploaded"] = video_file.read()
            video_file.seek(0)
        return {
            "sent": True,
            "outcome": "published",
            "post_ids": ["p1"],
            "provider_idempotency": False,
        }

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
    assert publish_env["uploaded"].startswith(b"SNAPSHOT-BYTES")
    assert publish_env["used_fileobj"] is True
    assert publish_env["path_reopen"] == 0
    assert publish_env["provider"] == 1
    assert out.get("external_exactly_once") is False


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
    assert publish_env["path_reopen"] == 0


# --- 3-6: snapshot integrity / descriptor TOCTOU --------------------------


@pytest.mark.asyncio
async def test_3_snapshot_modified_after_finalization_refuses(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    iso["snap"].write_bytes(b"TAMPERED-SNAP" * 2048)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out.get("provider_calls") == 0


@pytest.mark.asyncio
async def test_4_path_replaced_after_descriptor_open_still_uploads_verified_bytes(
    iso, publish_env, monkeypatch
):
    """Adversarial #4 (locked): path replace AFTER verified open must not matter.

    Provider receives bytes from the already-open descriptor. A second path
    open for that snapshot is a test failure.

    Note: in-place overwrite of an already-open Windows file shares the inode
    with the fd — that is NOT path replacement. This test renames the path to
    a new inode when the OS allows it; otherwise it still proves no reopen.
    """
    from app.marketing import video_ad_cycle as vac

    real_open = ps.open_verified_snapshot
    expected = iso["snap"].read_bytes()

    def _open_then_replace_path(**kwargs):
        out = real_open(**kwargs)
        if out.get("ok"):
            # Capture fd bytes before any filesystem swap.
            pos = out["fh"].tell()
            out["fh"].seek(0)
            publish_env["fd_bytes"] = out["fh"].read()
            out["fh"].seek(pos)
            try:
                stale = iso["snap"].with_name(iso["snap"].name + ".stale")
                os.replace(str(iso["snap"]), str(stale))
                iso["snap"].write_bytes(b"LATE-SWAP-SHOULD-NOT-UPLOAD" * 128)
                publish_env["path_replaced"] = True
            except OSError:
                # Windows often refuses rename/unlink of an open file. A sibling
                # decoy stands in for what a naive path-reopen would bind to.
                publish_env["path_replaced"] = False
                (iso["snap"].parent / "decoy_reopen.mp4").write_bytes(
                    b"LATE-SWAP-SHOULD-NOT-UPLOAD" * 128
                )
        return out

    monkeypatch.setattr(ps, "open_verified_snapshot", _open_then_replace_path)

    snap_resolved = str(iso["snap"].resolve())
    real_os_open = os.open

    def _guarded_os_open(path, flags, *a, **k):
        p = os.path.normcase(os.path.abspath(str(path)))
        target = os.path.normcase(os.path.abspath(snap_resolved))
        if p == target:
            publish_env.setdefault("os_open_snap", 0)
            publish_env["os_open_snap"] += 1
            if publish_env["os_open_snap"] > 1:
                raise AssertionError("second path open of snapshot is a Stage 3C failure")
        return real_os_open(path, flags, *a, **k)

    monkeypatch.setattr(os, "open", _guarded_os_open)

    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is True, out
    assert publish_env["fd_bytes"] == expected
    assert publish_env["uploaded"] == expected
    assert publish_env["used_fileobj"] is True
    assert publish_env["path_reopen"] == 0
    assert publish_env["provider"] == 1
    assert publish_env.get("os_open_snap", 0) == 1


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


# --- 11-15: failure / local reservation / counters -------------------------


@pytest.mark.asyncio
async def test_11_known_provider_failure_is_publish_failed(iso, publish_env, monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    async def _fail(*a, **k):
        publish_env["provider"] += 1
        return {
            "sent": False,
            "outcome": "failed",
            "reason": "400: provider_down",
            "provider_idempotency": False,
        }

    monkeypatch.setattr(pp, "publish_video", _fail, raising=False)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISH_FAILED
    assert out.get("external_exactly_once") is False


@pytest.mark.asyncio
async def test_11b_crash_after_provider_start_is_outcome_unknown(iso, publish_env, monkeypatch):
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    async def _boom(*a, **k):
        publish_env["provider"] += 1
        raise RuntimeError("connection dropped after accept")

    monkeypatch.setattr(pp, "publish_video", _boom, raising=False)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISH_OUTCOME_UNKNOWN
    # Blind retry must refuse.
    again = await vac._publish_one(publish_env["rec"])
    assert again["channels"]["idempotency"]["error"] == "publish_outcome_unknown"
    assert publish_env["provider"] == 1


@pytest.mark.asyncio
async def test_11c_ambiguous_adapter_outcome_is_unknown_not_retryable(
    iso, publish_env, monkeypatch
):
    """P0-1: Postiz timeout-shaped sent=False must become unknown, not failed."""
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac
    from app.marketing.video_production import cell

    async def _timeout(*a, **k):
        publish_env["provider"] += 1
        return {
            "sent": False,
            "outcome": "unknown",
            "reason": "ReadTimeout",
            "provider_idempotency": False,
        }

    monkeypatch.setattr(pp, "publish_video", _timeout, raising=False)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out.get("publish_attempt_state") == ps.PUBLISH_OUTCOME_UNKNOWN
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISH_OUTCOME_UNKNOWN

    # _publish_one blind retry blocked.
    again = await vac._publish_one(publish_env["rec"])
    assert again["channels"]["idempotency"]["error"] == "publish_outcome_unknown"
    assert publish_env["provider"] == 1

    # schedule_approved while still status=approved must not blind-retry.
    scheduled = await cell.schedule_approved("va_1")
    assert scheduled.get("error") == "publish_outcome_unknown"
    assert publish_env["provider"] == 1
    assert publish_env["rec"].get("status") == "publish_outcome_unknown"

    # publish_due must not pick unknown rows as ordinary approved retries.
    due = await vac.publish_due()
    assert due.get("published", 0) == 0
    assert due.get("failed", 0) == 0
    assert publish_env["provider"] == 1
    assert publish_env["rec"].get("status") == "publish_outcome_unknown"


@pytest.mark.asyncio
async def test_12_concurrent_duplicate_shares_one_reservation(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

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
    publish_env["rec"]["publish_attempt_state"] = ps.PROVIDER_INFLIGHT
    # Fresh timestamp → active hold (not stale recovery).
    publish_env["rec"]["publish_attempt_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out["channels"]["idempotency"]["error"] == "publish_reservation_held"
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_12b_reservation_write_failure_fail_closed(iso, publish_env, monkeypatch):
    """P0-2: if durable reserve does not stick, provider must not be called."""
    from app.marketing import video_ad_cycle as vac

    def _fail_update(rid, **fields):
        return False

    monkeypatch.setattr(vac, "_update", _fail_update)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out["channels"]["idempotency"]["error"] == "publish_reservation_failed"
    assert publish_env["provider"] == 0
    assert out.get("provider_calls") == 0


@pytest.mark.asyncio
async def test_12c_inflight_write_failure_zero_provider_calls(iso, publish_env, monkeypatch):
    """P0-B: provider_inflight must be durable before provider invocation."""
    from app.marketing import video_ad_cycle as vac

    real_cas = vac._cas_publish_state

    def _fail_inflight(rid, idem_key, *, from_states, to_state, **kw):
        if to_state == ps.PROVIDER_INFLIGHT:
            return {"ok": False, "error": "publish_cas_write_failed"}
        return real_cas(rid, idem_key, from_states=from_states, to_state=to_state, **kw)

    monkeypatch.setattr(vac, "_cas_publish_state", _fail_inflight)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert publish_env["provider"] == 0
    assert out.get("provider_calls") == 0
    assert out["channels"]["idempotency"]["error"] == "publish_cas_write_failed"


@pytest.mark.asyncio
async def test_12d_stale_inflight_becomes_unknown_not_retryable(iso, publish_env, monkeypatch):
    """P1 hard-kill: aged provider_inflight → publish_outcome_unknown."""
    from app.marketing import video_ad_cycle as vac

    identity = canonical_publish_identity(
        tenant="jiya-makeover",
        video_id="va_1",
        approval_txn="a" * 64,
        revision=0,
        snapshot_sha256=iso["digest"],
        snapshot_bytes=iso["size"],
        channel="postiz",
    )
    key = publish_idempotency_key(identity)
    publish_env["rec"]["publish_idempotency_key"] = key
    publish_env["rec"]["publish_attempt_state"] = ps.PROVIDER_INFLIGHT
    publish_env["rec"]["publish_attempt_at"] = "2000-01-01T00:00:00"
    monkeypatch.setenv("VIDEO_AD_PUBLISH_STALE_SECONDS", "60")

    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out["channels"]["idempotency"]["error"] == "publish_outcome_unknown"
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISH_OUTCOME_UNKNOWN
    assert publish_env["provider"] == 0

    again = await vac._publish_one(publish_env["rec"])
    assert again["channels"]["idempotency"]["error"] == "publish_outcome_unknown"
    assert publish_env["provider"] == 0


def test_12e_subprocess_kill_seam_recovers_stale_inflight(tmp_path, monkeypatch):
    """Real subprocess termination seam: child dies while inflight; parent recovers."""
    import json
    import subprocess
    import sys

    from app.marketing import video_ad_cycle as vac

    store = tmp_path / "video_ads.jsonl"
    lock = str(store) + ".lock"
    monkeypatch.setattr(vac, "_FILE", str(store))
    monkeypatch.setenv("VIDEO_AD_PUBLISH_STALE_SECONDS", "0")

    rid = "va_kill"
    key = "vap:" + ("ab" * 32)
    # Seed a fresh reserved row the child will advance to inflight.
    seed = {
        "id": rid,
        "publish_idempotency_key": key,
        "publish_attempt_state": ps.PUBLISH_RESERVED,
        "publish_attempt_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    store.write_text(json.dumps(seed) + "\n", encoding="utf-8")

    child = r"""
import json, os, sys, time
from filelock import FileLock
path = sys.argv[1]
rid = sys.argv[2]
key = sys.argv[3]
# Mark inflight under lock, then sleep until killed.
with FileLock(path + ".lock", timeout=15):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "id": rid,
            "publish_idempotency_key": key,
            "publish_attempt_state": "provider_inflight",
            "publish_attempt_at": "2000-01-01T00:00:00",
        }) + "\n")
    time.sleep(120)
"""
    proc = subprocess.Popen(
        [sys.executable, "-c", child, str(store), rid, key],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait until durable inflight is visible.
        deadline = time.time() + 10
        while time.time() < deadline:
            cur = vac._latest().get(rid) or {}
            if cur.get("publish_attempt_state") == ps.PROVIDER_INFLIGHT:
                break
            time.sleep(0.05)
        else:
            proc.kill()
            raise AssertionError("child never wrote provider_inflight")
        proc.kill()
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    # Parent recover path: stale inflight must become unknown, never retry.
    out = vac._acquire_publish_reservation(rid, key, {"tenant": "t", "video_id": rid})
    assert out.get("ok") is False
    assert out.get("error") == "publish_outcome_unknown"
    durable = vac._latest().get(rid) or {}
    assert durable.get("publish_attempt_state") == ps.PUBLISH_OUTCOME_UNKNOWN


@pytest.mark.asyncio
async def test_13_repeated_success_returns_local_evidence_without_provider(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    first = await vac._publish_one(publish_env["rec"])
    assert first["any_sent"] is True and publish_env["provider"] == 1
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISHED
    second = await vac._publish_one(publish_env["rec"])
    assert second.get("idempotent_local") is True
    assert second["any_sent"] is True
    assert publish_env["provider"] == 1
    assert second.get("provider_calls") == 0
    assert second.get("external_exactly_once") is False


@pytest.mark.asyncio
async def test_14_every_refusal_provider_counter_zero(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    publish_env["rec"].pop("approved_content_sha256", None)
    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is False
    assert out.get("provider_calls") == 0
    assert publish_env["provider"] == 0


@pytest.mark.asyncio
async def test_15_success_one_provider_call_from_verified_descriptor(iso, publish_env):
    from app.marketing import video_ad_cycle as vac

    out = await vac._publish_one(publish_env["rec"])
    assert out["any_sent"] is True
    assert publish_env["provider"] == 1
    assert out.get("provider_calls") == 1
    assert publish_env["used_fileobj"] is True
    assert publish_env["path_reopen"] == 0
    assert publish_env["uploaded"] == iso["snap"].read_bytes()
    assert publish_env["rec"].get("publish_idempotency_key", "").startswith("vap:")
    assert publish_env["rec"].get("publish_attempt_state") == ps.PUBLISHED
    assert out.get("external_exactly_once") is False
    assert ps.PROVIDER_ACCEPTS_IDEMPOTENCY_KEY is False
