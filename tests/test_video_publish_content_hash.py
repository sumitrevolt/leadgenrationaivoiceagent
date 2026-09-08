"""Gen-1 approval must bind to the exact VIDEO BYTES, not just a revision number.

`publish_gate.assert_can_publish` verified flags, allowlist, workflow state,
`approved_version == revision` and `final_approved` — every one of them a field
on a mutable JSONL record. Nothing re-read the artifact. So a video approved by
the customer could be re-rendered in place at the same path and same revision,
and the stale approval still authorised the publish.

These tests pin the byte-level binding. Creative OS is deliberately untouched:
it already has its own live-hash verification (`creative_os/approval.py`), and
conflating the two generations is not the goal here.
"""

from __future__ import annotations

import pytest

from app.marketing.video_production import publish_gate as pg
from app.marketing.video_production import states


@pytest.fixture(autouse=True)
def _gates_open(monkeypatch):
    """Neutralise the unrelated gates so only hash behaviour is under test."""
    monkeypatch.setattr(pg.flags, "production_enabled", lambda: False)
    monkeypatch.setattr(pg.flags, "social_publish_enabled", lambda: True)
    monkeypatch.setattr(pg.flags, "own_brand_enabled", lambda: False)


@pytest.fixture
def video(tmp_path, monkeypatch):
    """A real file inside an allowed media root."""
    root = tmp_path / "video_ads"
    root.mkdir()
    # Override through the PUBLIC renderer accessor, not a private constant.
    monkeypatch.setattr("app.marketing.video_pipeline.output_root", lambda: str(root))
    p = root / "va_1_rev0.mp4"
    p.write_bytes(b"BYTES-A" * 4096)
    return p


def _rec(video, **over):
    from pathlib import Path

    rec = {
        "id": "va_1",
        "client_id": "jiya-makeover",
        "approval_id": "ap_1",  # states.publish_allowed requires it
        "revision": 0,
        "approved_version": 0,
        "final_approved": True,
        "status": "approved",
        "workflow_state": states.APPROVED,
        "video_path": str(video),
    }
    rec.update(over)
    # Stage 3C: gate observes the SNAPSHOT path, not the mutable render.
    # Default helper materialises a real sibling snapshot with identical bytes.
    approved = str(rec.get("approved_content_sha256") or "")
    if approved and "approval_txn_state" not in over:
        snap = Path(str(rec.get("approval_snapshot_path") or (str(video) + ".snap")))
        if not snap.exists():
            snap.write_bytes(Path(video).read_bytes())
        rec.setdefault("approval_txn_state", "finalized")
        rec.setdefault("approval_txn", "t" * 64)
        rec.setdefault("approval_snapshot_path", str(snap))
        rec.setdefault("approval_snapshot_sha256", approved)
        rec.setdefault(
            "approval_snapshot_bytes", rec.get("approved_content_bytes") or snap.stat().st_size
        )
    return rec


# --- 1. Stage 3C: original render may change; SNAPSHOT is the identity -------


def test_overwritten_original_still_publishable_via_snapshot(video):
    """Original render mutated after approval must NOT poison the snapshot gate."""
    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    assert pg.assert_can_publish(rec)["ok"] is True

    video.write_bytes(b"BYTES-B" * 4096)  # mutable render swapped
    out = pg.assert_can_publish(rec)
    assert out["ok"] is True, out
    assert out["content_sha256"] == digest


def test_overwritten_snapshot_refused(video):
    from pathlib import Path

    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    snap = Path(rec["approval_snapshot_path"])
    snap.write_bytes(b"BYTES-B" * 4096)
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False
    assert out["error"] == "content_hash_mismatch"


# --- 2-4. every unverifiable case fails CLOSED ---------------------------


def test_legacy_record_without_hash_refused(video):
    """Pre-change approvals carry no hash. They must require re-approval."""
    out = pg.assert_can_publish(_rec(video))
    assert out["ok"] is False and out["error"] == "approval_hash_missing"


def test_missing_file_refused(video):
    from pathlib import Path

    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    Path(rec["approval_snapshot_path"]).unlink()
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False and out["error"] == "content_unverifiable"


def test_directory_as_video_path_refused(video, tmp_path):
    """Snapshot path that is a directory is unverifiable."""
    d = video.parent / "not_a_file"
    d.mkdir()
    rec = _rec(
        video,
        approval_snapshot_path=str(d),
        approved_content_sha256="0" * 64,
        approved_content_bytes=1,
        approval_txn_state="finalized",
        approval_txn="t" * 64,
        approval_snapshot_sha256="0" * 64,
        approval_snapshot_bytes=1,
    )
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False and out["error"] in (
        "content_unverifiable",
        "approval_not_finalized",
        "approval_snapshot_missing",
    )


def test_path_outside_media_root_refused(video, tmp_path):
    outside = tmp_path / "escape.mp4"
    outside.write_bytes(b"BYTES-A" * 4096)
    rec = _rec(
        video,
        approval_snapshot_path=str(outside),
        approved_content_sha256="0" * 64,
        approved_content_bytes=1,
        approval_txn_state="finalized",
        approval_txn="t" * 64,
        approval_snapshot_sha256="0" * 64,
        approval_snapshot_bytes=1,
    )
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False and out["error"] == "content_unverifiable"


# --- 5-6. legitimate behaviour preserved ---------------------------------


def test_unchanged_bytes_still_publishable(video):
    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    out = pg.assert_can_publish(rec)
    assert out["ok"] is True and out["version"] == 0


def test_revision_mismatch_still_refused_even_with_matching_hash(video):
    digest, size = pg.hash_video_file(str(video))
    rec = _rec(
        video,
        revision=2,
        approved_version=1,
        approved_content_sha256=digest,
        approved_content_bytes=size,
    )
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False and out["error"] == "version_mismatch"


def test_size_drift_alone_is_refused(video):
    digest, _ = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=999999)
    out = pg.assert_can_publish(rec)
    assert out["ok"] is False and out["error"] == "content_hash_mismatch"


# --- 7. refusal happens before any provider call -------------------------


@pytest.mark.asyncio
async def test_refusal_precedes_provider_invocation(video, monkeypatch):
    from pathlib import Path

    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    calls = {"postiz": 0, "telegram": 0}

    async def _spy_postiz(*a, **k):
        calls["postiz"] += 1
        return {"sent": True}

    async def _spy_tg(*a, **k):
        calls["telegram"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "enabled", lambda: True, raising=False)
    monkeypatch.setattr(pp, "publish_video", _spy_postiz, raising=False)
    monkeypatch.setattr(vac, "_tg_send_video", _spy_tg, raising=False)
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        lambda c: {"id": "jiya-makeover", "niche": "salon"},
    )
    monkeypatch.setattr(vac, "_update", lambda *a, **k: None)
    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", lambda *a, **k: True)

    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    Path(rec["approval_snapshot_path"]).write_bytes(b"TAMPERED" * 4096)

    out = await vac._publish_one(rec)
    assert out["any_sent"] is False
    assert out["channels"]["gate"]["error"] == "content_hash_mismatch"
    assert calls == {"postiz": 0, "telegram": 0}
    assert out.get("provider_calls") == 0


# --- 8. reapproval stores the NEW hash; publish never backfills ----------


@pytest.fixture
def writer(video, monkeypatch):
    """Capture what the ONE canonical writer persists."""
    import app.marketing.video_ad_cycle as vac

    written: dict = {}
    monkeypatch.setattr(vac, "_latest", lambda: {"va_1": _rec(video)})
    monkeypatch.setattr(vac, "_update", lambda rec_id, **f: written.update({"id": rec_id, **f}))
    return written


def test_canonical_writer_persists_hash_and_identity(video, writer):
    import app.marketing.video_ad_cycle as vac

    out = vac.record_approval("va_1", 0, actor="customer:jiya-makeover")
    digest, size = pg.hash_video_file(str(video))
    assert out["ok"] is True
    assert writer["approved_content_sha256"] == digest
    assert writer["approved_content_bytes"] == size
    assert writer["approved_version"] == 0
    assert writer["approved_by"] == "customer:jiya-makeover"
    assert writer["approved_at"] and writer["status"] == "approved"


def test_wrapper_is_retired_and_writes_nothing(video, writer):
    """INVERTED (Stage 3B-close).

    These three tests used to assert that ``mark_version_approved`` correctly
    performed an approval with a free-form ``actor`` string and no transaction.
    That is the same uncoordinated-writer shape as the legacy token callback, so
    the wrapper is retired rather than fixed. Its original safety intent (never
    hash caller-selected bytes) is now satisfied absolutely: it writes nothing
    at all, for any argument combination.
    """
    for kwargs in (
        {"actor": "admin"},
        {"actor": "admin", "video_path": str(video)},
        {"actor": "admin", "video_path": str(video.parent / "." / video.name)},
    ):
        out = pg.mark_version_approved("va_1", 0, **kwargs)
        assert out["ok"] is False
        assert out["error"] == "uncoordinated_approval_writer_retired"
    assert writer == {}, "retired wrapper must never reach the canonical writer"


def test_wrapper_path_mismatch_refuses(video, writer, tmp_path, monkeypatch):
    """Case 3 — different path → refused, zero update, zero provider calls."""
    from app.marketing import postiz_publish as pp

    calls = {"postiz": 0}

    async def _spy(*a, **k):
        calls["postiz"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)

    decoy = video.parent / "decoy.mp4"  # in-root, but NOT the record's file
    decoy.write_bytes(b"DECOY" * 100)
    pg.mark_version_approved("va_1", 0, video_path=str(decoy), actor="admin")
    assert writer == {}  # no approval mutation at all
    assert calls == {"postiz": 0}


def test_writer_refuses_empty_actor(video, writer):
    import app.marketing.video_ad_cycle as vac

    out = vac.record_approval("va_1", 0, actor="   ")
    assert out["ok"] is False and out["error"] == "approver_identity_required"
    assert writer == {}  # nothing persisted


def test_writer_leaves_record_unchanged_when_unhashable(video, writer, monkeypatch):
    import app.marketing.video_ad_cycle as vac

    video.unlink()
    out = vac.record_approval("va_1", 0, actor="admin")
    assert out["ok"] is False and out["error"] == "content_unverifiable"
    assert writer == {}  # atomic: no partial approval written


def test_reapproval_replaces_hash_not_backfills(video, writer):
    import app.marketing.video_ad_cycle as vac

    vac.record_approval("va_1", 0, actor="customer:jiya-makeover")
    first = writer["approved_content_sha256"]
    video.write_bytes(b"BYTES-B" * 4096)
    vac.record_approval("va_1", 1, actor="admin")
    assert writer["approved_content_sha256"] != first
    assert writer["approved_version"] == 1 and writer["approved_by"] == "admin"


def test_publish_gate_never_writes_a_hash(video, monkeypatch):
    """The gate must be READ-ONLY — backfilling would approve changed bytes."""
    calls = []
    monkeypatch.setattr(
        "app.marketing.video_ad_cycle._update",
        lambda rec_id, **f: calls.append(f),
    )
    pg.assert_can_publish(_rec(video))  # legacy record, no hash
    assert calls == []


def test_hash_is_streaming_not_whole_file_read(video, monkeypatch):
    """A 1080p video must not be slurped into memory."""
    import app.marketing.video_production.publish_gate as mod

    monkeypatch.setattr(
        mod.Path,
        "read_bytes",
        lambda self: pytest.fail("read_bytes() used — must stream in chunks"),
        raising=False,
    )
    digest, size = pg.hash_video_file(str(video))
    assert len(digest) == 64 and size == len(b"BYTES-A" * 4096)


# --- TOCTOU: Stage 3C CLOSED — provider consumes snapshot only ------------


@pytest.mark.asyncio
async def test_toctou_gap_closed_provider_receives_snapshot_bytes(video, monkeypatch):
    """Stage 3C: mutating the original between gate and upload must not matter.

    Provider is handed the snapshot path; uploaded bytes must equal the
    approved snapshot, not the swapped original.
    """
    from pathlib import Path

    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as vac

    uploaded: dict[str, bytes] = {}

    async def _capture(
        client, caption, video_path="", *, video_file=None, filename="video.mp4", **kw
    ):
        if video_file is not None:
            video_file.seek(0)
            uploaded["bytes"] = video_file.read()
            uploaded["path"] = "fileobj"
            video_file.seek(0)
        else:
            uploaded["path"] = video_path
            uploaded["bytes"] = open(video_path, "rb").read()
        return {"sent": True, "post_ids": ["p1"]}

    def _mutate_original_after_gate(cid):
        video.write_bytes(b"SWAPPED" * 4096)
        return {"id": "jiya-makeover", "postiz_integrations": "c1"}

    monkeypatch.setattr(pp, "enabled", lambda: True, raising=False)
    monkeypatch.setattr(pp, "publish_video", _capture, raising=False)
    monkeypatch.setattr(
        "app.marketing.clients_store.resolve_client",
        _mutate_original_after_gate,
    )
    store = {"rec": None}

    def _latest():
        return {store["rec"]["id"]: store["rec"]} if store["rec"] else {}

    def _update(rid, **fields):
        if store["rec"] is None:
            return False
        if store["rec"].get("id") == rid:
            store["rec"].update(fields)
        return True

    monkeypatch.setattr(vac, "_latest", _latest)
    monkeypatch.setattr(vac, "_update", _update)
    monkeypatch.setattr("app.marketing.delivery_ledger.log_event", lambda *a, **k: True)

    digest, size = pg.hash_video_file(str(video))
    rec = _rec(video, approved_content_sha256=digest, approved_content_bytes=size)
    store["rec"] = rec
    snap_bytes = Path(rec["approval_snapshot_path"]).read_bytes()

    assert pg.assert_can_publish(rec)["ok"] is True
    out = await vac._publish_one(rec)

    assert out.get("any_sent") is True
    assert uploaded.get("bytes") == snap_bytes
    assert uploaded.get("bytes", b"").startswith(b"BYTES-A")
    assert not uploaded.get("bytes", b"").startswith(b"SWAPPED")
    assert uploaded["path"] == "fileobj"
    assert out.get("provider_calls") == 1
    assert out.get("external_exactly_once") is False
