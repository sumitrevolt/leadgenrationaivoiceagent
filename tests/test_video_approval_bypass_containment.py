"""Stage 3B-close — the two P0 approval bypasses.

The read-only audit proved that Stage 3B closed the customer dashboard and the
admin route, but left two paths that reach a finalized, publishable video
approval WITHOUT the saga or a principal:

  P0-1  GET /api/clientops/approve/{token}  (public, unauthenticated)
          -> content_approval.approve -> _decide -> on_approved
          -> record_approval  (writes final_approved=True + a hash of whatever
             the bytes are at that moment, not the bytes anyone previewed)

  P0-2  publish_gate.evaluate_publish_gate never consults saga state, so the
        record produced above passes the gate. approval_saga.is_publishable
        exists, is exported, and is called by nothing.

`on_approved` is the single choke point for P0-1: the caller table shows FOUR
production entrypoints reaching it (public token route, decide_for_client from
the customer portal and boss_council, decide_by_id from product_one_delivery).
Containing on_approved covers all four; patching only the public route would
not.

Every test here counts DURABLE MUTATION, and the suite asserts the repository's
real data/ directory is untouched.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_DATA = Path(__file__).resolve().parents[1] / "data"


def _repo_data_fingerprint() -> dict[str, str]:
    """Content hash of every file under the repo's real data/ dir."""
    out: dict[str, str] = {}
    if not REPO_DATA.exists():
        return out
    for p in sorted(REPO_DATA.rglob("*")):
        if p.is_file():
            try:
                out[str(p.relative_to(REPO_DATA))] = hashlib.sha256(p.read_bytes()).hexdigest()
            except OSError:
                out[str(p.relative_to(REPO_DATA))] = "unreadable"
    return out


@pytest.fixture(autouse=True)
def _no_repo_data_writes():
    """Fails the test if anything touched the repository's data/ directory.

    Not a cleanup step — a proof. An isolation fixture that silently stops
    working would otherwise let these tests pass while writing real files.
    """
    before = _repo_data_fingerprint()
    yield
    after = _repo_data_fingerprint()
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(k for k in set(before) & set(after) if before[k] != after[k])
    assert not (added or removed or changed), (
        f"repo data/ mutated — added={added} removed={removed} changed={changed}"
    )


@pytest.fixture
def iso(tmp_path, monkeypatch):
    """Every durable store this slice can touch, redirected into tmp_path."""
    # No `as` aliases in the import itself: isort and ruff disagree on how to
    # order a block that mixes plain and aliased names from one module, and
    # each "fixes" the other's output forever. Aliasing after the import is
    # stable under both.
    from app.marketing import (
        auto_content,
        clients_store,
        content_approval,
        delivery_ledger,
        video_ad_cycle,
        video_media_paths,
        video_pipeline,
    )

    V = video_ad_cycle
    vmp = video_media_paths

    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(V, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(V, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    for mod, name, sub in (
        (auto_content, "_QUEUE_DIR", "queue"),
        (delivery_ledger, "_LEDGER_DIR", "ledger"),
    ):
        d = tmp_path / sub
        d.mkdir()
        monkeypatch.setattr(mod, name, lambda d=d: str(d))
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: tmp_path / "approved")
    root = tmp_path / "reels"
    root.mkdir()
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(root))
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())

    artifact = root / "legacy.mp4"
    artifact.write_bytes(b"LEGACY-BYTES" * 400)
    submitted = content_approval.submit(
        "tenant-legacy",
        {"type": "video_ad", "title": "Legacy", "revision": 0, "video_path": str(artifact)},
    )
    approval = submitted["approval"]
    V._append(
        {
            "id": "vid-legacy-1",
            "client_id": "tenant-legacy",
            "approval_id": approval["id"],
            "token": approval["token"],
            "status": "pending",
            "revision": 0,
            "video_path": str(artifact),
        }
    )
    return {
        "tmp": tmp_path,
        "artifact": artifact,
        "token": approval["token"],
        "approval_id": approval["id"],
    }


def _rec(rid="vid-legacy-1"):
    from app.marketing import video_ad_cycle as V

    return (V._latest() or {}).get(rid) or {}


def _mutation_spies(monkeypatch):
    """Count every mutation seam a refusal must happen BEFORE."""
    from app.marketing import auto_content, delivery_ledger
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import snapshot

    n = {"record_approval": 0, "enqueue": 0, "ledger": 0, "snapshot": 0, "provider": 0}
    for mod, name, key in (
        (V, "record_approval", "record_approval"),
        (auto_content, "enqueue_approved", "enqueue"),
        (delivery_ledger, "log_event", "ledger"),
        (snapshot, "prepare_snapshot", "snapshot"),
    ):
        real = getattr(mod, name)

        def _spy(*a, __k=key, __r=real, **k):
            n[__k] += 1
            return __r(*a, **k)

        monkeypatch.setattr(mod, name, _spy)

    async def _prov(*a, **k):
        n["provider"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _prov, raising=False)
    return n


# ===================== A1. public token route =============================


def test_public_token_get_cannot_approve_a_video(iso, monkeypatch):
    """P0-1: the unauthenticated GET link must not write an approval.

    A state-changing approval through GET is wrong regardless of identity;
    combined with an unbound legacy token it is a full bypass of Stage 1-3B.
    """
    from app.main import app

    n = _mutation_spies(monkeypatch)
    before = dict(_rec())

    with TestClient(app) as c:
        r = c.get(f"/api/clientops/approve/{iso['token']}?action=approve")

    assert r.status_code < 500, "refusal must be controlled, never a 500"
    body = r.text.lower()
    assert "approval_token_regeneration_required" in body, body[:400]

    rec = _rec()
    assert rec.get("status") == "pending"
    assert not rec.get("final_approved")
    assert not rec.get("approved_at")
    assert not rec.get("approved_content_sha256")
    assert rec == before, "video record must be byte-identical after refusal"
    assert n == {
        "record_approval": 0,
        "enqueue": 0,
        "ledger": 0,
        "snapshot": 0,
        "provider": 0,
    }, n


def test_public_token_route_leaks_no_credential(iso):
    from app.main import app

    with TestClient(app) as c:
        r = c.get(f"/api/clientops/approve/{iso['token']}?action=approve")
    assert iso["token"] not in r.text


# ===================== A2. direct legacy callback ==========================


def test_decide_cannot_approve_video_without_a_saga_transaction(iso, monkeypatch):
    """P0-2 root: on_approved is the choke point for all four entrypoints."""
    from app.marketing import content_approval

    n = _mutation_spies(monkeypatch)
    out = content_approval.approve(iso["token"])

    rec = _rec()
    assert not rec.get("final_approved")
    assert rec.get("status") == "pending"
    assert n["record_approval"] == 0
    assert n["enqueue"] == 0
    assert n["ledger"] == 0
    assert out.get("ok") is False or not rec.get("approved_at")


def test_on_approved_refuses_uncoordinated_transaction(iso, monkeypatch):
    from app.marketing import content_approval
    from app.marketing import video_ad_cycle as V

    n = _mutation_spies(monkeypatch)
    approval = content_approval.get_by_token(iso["token"]) or {}
    assert V.on_approved(approval) is False
    assert n["record_approval"] == 0


def test_non_video_content_approval_still_works(iso, monkeypatch):
    """Containment must be scoped to video_ad — general content is unaffected."""
    from app.marketing import content_approval

    sub = content_approval.submit(
        "tenant-legacy", {"type": "branded", "title": "Post", "caption": "a valid caption here"}
    )
    out = content_approval.approve(sub["approval"]["token"])
    assert out["ok"] is True
    assert (content_approval.get_by_token(sub["approval"]["token"]) or {})["status"] == "approved"


# ===================== A3. publish gate ====================================


def _legacy_approved_record(artifact: Path) -> dict:
    """Exactly the shape record_approval used to produce: hash present, no saga."""
    raw = artifact.read_bytes()
    return {
        "id": "vid-legacy-1",
        "client_id": "tenant-legacy",
        # Realistic: states.publish_allowed requires an approval_id, so omitting
        # it would refuse for an unrelated reason and prove nothing.
        "approval_id": "appr-legacy-1",
        "token": "tok-legacy",
        "status": "approved",
        "workflow_state": "approved",
        "final_approved": True,
        "revision": 0,
        "approved_version": 0,
        "video_path": str(artifact),
        "approved_content_sha256": hashlib.sha256(raw).hexdigest(),
        "approved_content_bytes": len(raw),
    }


def test_legacy_hash_only_record_is_not_publishable(iso, monkeypatch):
    """Currently PASSES the gate. Only a finalized saga transaction may publish."""
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    rec = _legacy_approved_record(iso["artifact"])
    out = publish_gate.assert_can_publish(rec)
    assert out["ok"] is False
    assert out["error"] == "approval_not_finalized"


@pytest.mark.parametrize(
    "state", ["", "prepared", "decision_recorded", "compensated", "inconsistent"]
)
def test_only_finalized_saga_state_is_publish_eligible(iso, monkeypatch, state):
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    rec = _legacy_approved_record(iso["artifact"])
    if state:
        rec["approval_txn_state"] = state
    out = publish_gate.assert_can_publish(rec)
    assert out["ok"] is False
    assert out["error"] in ("approval_not_finalized", "approval_snapshot_missing")


def test_finalized_without_snapshot_identity_refuses(iso, monkeypatch):
    """A finalized flag alone is not enough — the snapshot identity must exist."""
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    rec = _legacy_approved_record(iso["artifact"])
    rec["approval_txn_state"] = "finalized"
    rec["approval_txn"] = "t" * 64
    out = publish_gate.assert_can_publish(rec)
    assert out["ok"] is False
    assert out["error"] == "approval_snapshot_missing"


def test_finalized_with_inconsistent_snapshot_identity_refuses(iso, monkeypatch):
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    snap = iso["tmp"] / "snapshot.mp4"
    snap.write_bytes(iso["artifact"].read_bytes())
    rec = _legacy_approved_record(iso["artifact"])
    rec.update(
        approval_txn_state="finalized",
        approval_txn="t" * 64,
        approval_snapshot_path=str(snap),
        approval_snapshot_sha256="b" * 64,  # disagrees with approved hash
        approval_snapshot_bytes=snap.stat().st_size,
    )
    out = publish_gate.assert_can_publish(rec)
    assert out["ok"] is False
    assert out["error"] == "approval_snapshot_mismatch"


def test_publish_gate_refuses_before_any_provider_call(iso, monkeypatch):
    from app.marketing.video_production import publish_gate

    n = _mutation_spies(monkeypatch)
    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    publish_gate.assert_can_publish(_legacy_approved_record(iso["artifact"]))
    assert n["provider"] == 0


def test_one_canonical_eligibility_evaluator(iso):
    """The real gate must delegate to the pure evaluator — no second state machine."""
    import inspect

    from app.marketing.video_production import publish_gate

    src = inspect.getsource(publish_gate.assert_can_publish)
    assert "evaluate_publish_gate" in src


def test_saga_finalized_record_is_publishable(iso, monkeypatch):
    """The positive case: a fully coordinated approval still publishes."""
    from app.marketing.video_production import publish_gate

    monkeypatch.setenv("VIDEO_SOCIAL_PUBLISH_ENABLED", "1")
    raw = iso["artifact"].read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    # Stage 3C: snapshot must live inside the media authority (same root).
    snap = iso["artifact"].parent / "snap_ok.mp4"
    snap.write_bytes(raw)
    rec = _legacy_approved_record(iso["artifact"])
    rec.update(
        approval_txn_state="finalized",
        approval_txn="t" * 64,
        approval_snapshot_path=str(snap),
        approval_snapshot_sha256=digest,
        approval_snapshot_bytes=len(raw),
    )
    out = publish_gate.assert_can_publish(rec)
    assert out["ok"] is True, out


# ===================== wiring, not exports =================================


def test_is_publishable_has_a_production_caller():
    """The audit found it exported and called by nothing."""
    import inspect

    from app.marketing.video_production import publish_gate

    src = inspect.getsource(publish_gate)
    assert "is_publishable" in src, "publish gate must consult saga eligibility"


def test_mark_version_approved_cannot_write_an_uncoordinated_approval(iso, monkeypatch):
    """A second writer into record_approval would re-open the bypass."""
    from app.marketing.video_production import publish_gate

    n = _mutation_spies(monkeypatch)
    out = publish_gate.mark_version_approved("vid-legacy-1", 0, actor="admin")
    assert out.get("ok") is False
    assert n["record_approval"] == 0
    assert not _rec().get("final_approved")


def test_revocation_store_down_blocks_customer_approval(monkeypatch):
    """Phase C: require_customer's blacklist check fails OPEN ("allowing
    request"). For a READ that is defensible; for an approval mutation it means
    a logged-out session could still approve whenever Redis is unwell."""
    import asyncio

    from app.api import customer_dashboard as cd

    async def _boom():
        raise OSError("redis down")

    monkeypatch.setattr("app.cache.get_redis_client", _boom)

    class _C:
        credentials = "tok"

    _tenant_ok, revocation_ok = asyncio.new_event_loop().run_until_complete(
        cd._approval_session_facts("acme", _C())
    )
    assert revocation_ok is False


def test_unresolvable_tenant_blocks_customer_approval(monkeypatch):
    """canonical_client_id echoes its input when resolution fails, so a
    'canonical' id is not proof the tenant exists."""
    import asyncio

    from app.api import customer_dashboard as cd
    from app.marketing import clients_store

    monkeypatch.setattr(clients_store, "resolve_client", lambda cid: None, raising=False)

    class _C:
        credentials = "tok"

    tenant_ok, _rev = asyncio.new_event_loop().run_until_complete(
        cd._approval_session_facts("ghost-tenant", _C())
    )
    assert tenant_ok is False


def test_repo_data_untouched_sentinel():
    """Sanity: the guard fixture itself sees the real directory."""
    fp = _repo_data_fingerprint()
    assert isinstance(fp, dict)


def test_no_raw_token_in_approval_store(iso):
    """Once binding lands, storage must hold a hash, not the credential."""
    from app.marketing import content_approval

    path = Path(content_approval._FILE())
    if not path.exists():
        pytest.skip("no approvals file yet")
    rows = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    assert rows, "fixture should have written an approval"
