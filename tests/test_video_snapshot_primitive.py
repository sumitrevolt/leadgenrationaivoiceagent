"""Stage 2 — immutable snapshot primitive.

Filesystem only: no approval ledger, video record, queue, provider or UI is
touched. A hardlink would share the source inode, so the snapshot must be a NEW
inode; every failure path must leave nothing installed and no temp behind.
"""

from __future__ import annotations

import hashlib
import os
import threading

import pytest

from app.marketing.video_production import snapshot as S

TENANT = "jiya-makeover"
REC = "va-snap-1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import video_media_paths as vmp
    from app.marketing import video_pipeline

    src_root = tmp_path / "reels"
    src_root.mkdir()
    approved = tmp_path / "video_ads" / "_approved"
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(src_root))
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: approved)

    source = src_root / "render.mp4"
    source.write_bytes(b"SNAPSHOT-A" * 4096)
    return {
        "source": source,
        "approved": approved,
        "digest": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def _prepare(env, **over):
    kw = {
        "tenant_id": TENANT,
        "record_id": REC,
        "revision": 0,
        "expected_sha256": env["digest"],
        "source_path": str(env["source"]),
    }
    kw.update(over)
    return S.prepare_snapshot(**kw)


def _temps(env):
    d = env["approved"] / TENANT
    return list(d.glob(".snap-*")) if d.exists() else []


# 1. correct digest/size and a NEW inode
def test_snapshot_is_new_inode_with_correct_identity(env):
    out = _prepare(env)
    assert out["ok"] is True and out["reused"] is False
    snap = os.stat(out["path"])
    src = os.stat(env["source"])
    assert snap.st_ino != src.st_ino  # copy, never a hardlink
    assert snap.st_nlink == 1
    assert out["sha256"] == env["digest"]
    assert out["bytes"] == src.st_size
    assert hashlib.sha256(open(out["path"], "rb").read()).hexdigest() == env["digest"]
    assert _temps(env) == []


# 2. hash mismatch installs nothing
def test_hash_mismatch_leaves_no_artifact(env):
    out = _prepare(env, expected_sha256="b" * 64)
    assert out["ok"] is False and out["error"] == "content_hash_mismatch"
    assert not (env["approved"] / TENANT).exists() or not list(
        (env["approved"] / TENANT).glob("*.mp4")
    )
    assert _temps(env) == []


# 3. concurrent source mutation refuses
def test_source_changed_during_copy_refuses(env, monkeypatch):
    real_fstat = os.fstat
    calls = {"n": 0}

    def _drifting_fstat(fd):
        st = real_fstat(fd)
        calls["n"] += 1
        if calls["n"] >= 2:  # the post-copy stat looks different
            return os.stat_result(tuple(st)[:7] + (st.st_atime, st.st_mtime + 5, st.st_ctime))
        return st

    monkeypatch.setattr(os, "fstat", _drifting_fstat)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "source_changed_during_copy"
    assert _temps(env) == []


# 4. interruption at each stage cleans the temp
@pytest.mark.parametrize("boom_at", ["fsync", "replace"])
def test_interruption_cleans_temp(env, monkeypatch, boom_at):
    if boom_at == "fsync":
        monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk gone")))
    else:
        monkeypatch.setattr(
            os, "replace", lambda a, b: (_ for _ in ()).throw(OSError("rename failed"))
        )
    out = _prepare(env)
    assert out["ok"] is False
    assert _temps(env) == []
    assert not list((env["approved"] / TENANT).glob("*.mp4"))


# 5. size and disk-headroom budgets refuse
def test_oversized_source_refused(env, monkeypatch):
    monkeypatch.setattr(S, "_MAX_SNAPSHOT_BYTES", 16)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "source_size_out_of_bounds"
    assert _temps(env) == []


def test_insufficient_disk_headroom_refused(env, monkeypatch):
    monkeypatch.setattr(S, "_free_bytes", lambda p: S._DISK_HEADROOM_BYTES)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "insufficient_disk_headroom"
    assert _temps(env) == []


def test_empty_source_refused(env):
    env["source"].write_bytes(b"")
    out = _prepare(env, expected_sha256=hashlib.sha256(b"").hexdigest())
    assert out["ok"] is False and out["error"] == "source_size_out_of_bounds"


# 6. identical snapshot reused without rewrite
def test_identical_snapshot_is_reused(env):
    first = _prepare(env)
    before = os.stat(first["path"])
    second = _prepare(env)
    assert second["ok"] is True and second["reused"] is True
    after = os.stat(second["path"])
    assert (before.st_ino, before.st_mtime_ns) == (after.st_ino, after.st_mtime_ns)


# 7. corrupt existing destination refused, never overwritten
def test_existing_corrupt_snapshot_refused(env):
    first = _prepare(env)
    corrupted = b"TAMPERED"
    with open(first["path"], "wb") as fh:
        fh.write(corrupted)
    out = _prepare(env)
    assert out["ok"] is False and out["error"] == "existing_snapshot_corrupt"
    assert open(first["path"], "rb").read() == corrupted  # untouched


# 8. concurrent same-revision calls do not corrupt
def test_concurrent_same_revision_is_safe(env):
    results = []

    def _run():
        results.append(_prepare(env))

    threads = [threading.Thread(target=_run) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert all(r["ok"] for r in results)
    paths = {r["path"] for r in results}
    assert len(paths) == 1
    only = paths.pop()
    assert hashlib.sha256(open(only, "rb").read()).hexdigest() == env["digest"]
    assert _temps(env) == []
    assert len(list((env["approved"] / TENANT).glob("*.mp4"))) == 1


# 9. distinct revisions cannot overwrite each other
def test_distinct_revisions_do_not_collide(env):
    r0 = _prepare(env, revision=0)
    env["source"].write_bytes(b"SNAPSHOT-B" * 4096)
    d1 = hashlib.sha256(env["source"].read_bytes()).hexdigest()
    r1 = _prepare(env, revision=1, expected_sha256=d1)
    assert r0["path"] != r1["path"]
    assert os.path.exists(r0["path"]) and os.path.exists(r1["path"])
    assert hashlib.sha256(open(r0["path"], "rb").read()).hexdigest() != d1


# 10. traversal identifiers are neutralised
@pytest.mark.parametrize(
    "tenant,record",
    [("../../etc", "va-1"), ("t", "../../../evil"), ("a/b", "c\\d"), ("", "")],
)
def test_traversal_identifiers_refused(env, tenant, record):
    out = _prepare(env, tenant_id=tenant, record_id=record)
    assert out["ok"] is True
    installed = os.path.realpath(out["path"])
    root = os.path.realpath(env["approved"])
    assert installed.startswith(root + os.sep)  # never escapes the approved root
    assert ".." not in os.path.relpath(installed, root)


def test_invalid_expected_hash_refused(env):
    assert _prepare(env, expected_sha256="nothex")["error"] == "expected_sha256_invalid"
    assert _prepare(env, expected_sha256="")["error"] == "expected_sha256_invalid"


def test_source_outside_media_root_refused(env, tmp_path):
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x" * 100)
    out = _prepare(env, source_path=str(outside))
    assert out["ok"] is False and out["error"] == "source_unverifiable"


# 11-12. no hardlink, no ledger/record/queue/provider mutation
def test_never_uses_os_link(env, monkeypatch):
    calls = {"link": 0}
    monkeypatch.setattr(os, "link", lambda *a, **k: calls.__setitem__("link", calls["link"] + 1))
    assert _prepare(env)["ok"] is True
    assert calls["link"] == 0


def test_no_business_state_or_provider_mutation(env, monkeypatch):
    from app.marketing import content_approval
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V

    counts = {"update": 0, "append": 0, "decide": 0, "postiz": 0}

    async def _spy_postiz(*a, **k):
        counts["postiz"] += 1
        return {"sent": True}

    monkeypatch.setattr(V, "_update", lambda *a, **k: counts.__setitem__("update", 1))
    monkeypatch.setattr(V, "_append", lambda *a, **k: counts.__setitem__("append", 1))
    monkeypatch.setattr(
        content_approval, "approve", lambda *a, **k: counts.__setitem__("decide", 1)
    )
    monkeypatch.setattr(pp, "publish_video", _spy_postiz, raising=False)

    assert _prepare(env)["ok"] is True
    assert counts == {"update": 0, "append": 0, "decide": 0, "postiz": 0}


def test_module_does_not_delete_finalized_snapshots():
    src = (S.__file__ or "").replace("\\", "/")
    body = open(src, encoding="utf-8").read()
    assert "read_bytes(" not in body
    assert "os.link(" not in body
    # the only unlink is the temp-artifact cleanup
    assert body.count("os.unlink(") == 1 and "os.unlink(tmp_path)" in body
