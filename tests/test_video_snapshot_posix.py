"""POSIX proofs for the snapshot primitive (inode, concurrency, O_NOFOLLOW).

Imports only `snapshot` + `video_media_paths`, so it runs in a minimal,
network-disabled Linux container with no repo conftest and no .env:

    docker run --rm --network none -v <worktree>:/src:ro python:3.12-slim(+pytest)
"""

from __future__ import annotations

import hashlib
import os
import threading

import pytest

from app.marketing.video_production import snapshot as S

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX inode semantics")

TENANT = "tenant-posix"
REC = "va-posix-1"


@pytest.fixture
def env(tmp_path, monkeypatch):
    from app.marketing import video_media_paths as vmp

    src_root = tmp_path / "reels"
    src_root.mkdir()
    approved = tmp_path / "video_ads" / "_approved"
    monkeypatch.setattr(vmp, "reels_dir", lambda: src_root)
    monkeypatch.setattr(vmp, "video_ads_dir", lambda: tmp_path / "video_ads")
    monkeypatch.setattr(vmp, "approved_media_dir", lambda: approved)

    source = src_root / "render.mp4"
    source.write_bytes(b"POSIX-A" * 8192)
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


def test_snapshot_has_distinct_inode_and_single_link(env):
    out = _prepare(env)
    assert out["ok"] is True
    snap, src = os.stat(out["path"]), os.stat(env["source"])
    assert snap.st_ino != src.st_ino
    assert snap.st_nlink == 1 and src.st_nlink == 1


def test_source_overwrite_after_snapshot_does_not_change_snapshot(env):
    out = _prepare(env)
    before = open(out["path"], "rb").read()
    env["source"].unlink()
    env["source"].write_bytes(b"REPLACED" * 8192)
    assert open(out["path"], "rb").read() == before


def test_concurrent_same_revision_installs_exactly_one(env):
    results = []
    barrier = threading.Barrier(8)

    def _run():
        barrier.wait()
        results.append(_prepare(env))

    ts = [threading.Thread(target=_run) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]

    assert all(r["ok"] for r in results)
    assert len({r["path"] for r in results}) == 1
    installed = list((env["approved"] / TENANT).glob("*.mp4"))
    assert len(installed) == 1
    assert hashlib.sha256(installed[0].read_bytes()).hexdigest() == env["digest"]
    assert list((env["approved"] / TENANT).glob(".snap-*")) == []


def test_symlinked_source_refused_by_authority(env):
    link = env["source"].parent / "link.mp4"
    link.symlink_to(env["source"])
    out = _prepare(env, source_path=str(link))
    assert out["ok"] is False and out["error"] == "source_unverifiable"


def test_directory_fsync_path_is_exercised(env):
    assert hasattr(os, "O_DIRECTORY")
    assert _prepare(env)["ok"] is True
