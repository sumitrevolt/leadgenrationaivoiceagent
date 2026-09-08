"""SERVABLE == APPROVABLE == PUBLISHABLE — one media-root authority.

Every consumer resolves through `video_media_paths.resolve_video_media_file`,
so an artifact can never be servable-but-unapprovable (or the reverse). These
tests drive the real consumers, not the resolver in isolation.

Writer contract (verified against all 36 production records): a stored
`video_path` is repo-relative and carries its media-root prefix. Bare names are
refused rather than hunted for across roots.
"""

from __future__ import annotations

import os

import pytest

from app.api import customer_dashboard as cd
from app.marketing import video_media_paths as vmp
from app.marketing.video_production import publish_gate as pg


@pytest.fixture
def root(tmp_path, monkeypatch):
    from app.marketing import video_pipeline

    r = tmp_path / "reels"
    r.mkdir()
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(r))
    return r


def _mp4(root, name="ok.mp4", payload=b"bytes" * 100):
    p = root / name
    p.write_bytes(payload)
    return p


# --- parity through the real consumers ----------------------------------


def test_in_root_artifact_is_servable_and_approvable(root):
    p = _mp4(root)
    assert cd._resolve_customer_video_path({"video_path": str(p)}) == p.resolve()
    digest, size = pg.hash_video_file(str(p))
    assert len(digest) == 64 and size > 0


def test_outside_root_artifact_refused_everywhere(root, tmp_path):
    outside = tmp_path / "escape.mp4"
    outside.write_bytes(b"nope")
    assert vmp.resolve_video_media_file(str(outside)) is None
    assert cd._resolve_customer_video_path({"video_path": str(outside)}) is None
    assert pg.hash_video_file(str(outside)) == ("", 0)


def test_cwd_change_has_no_effect(root, tmp_path, monkeypatch):
    p = _mp4(root)
    before = vmp.resolve_video_media_file(str(p))
    monkeypatch.chdir(tmp_path)
    assert vmp.resolve_video_media_file(str(p)) == before
    assert cd._resolve_customer_video_path({"video_path": str(p)}) == before


def test_runtime_output_root_override_is_honoured(tmp_path, monkeypatch):
    from app.marketing import video_pipeline

    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir()
    b.mkdir()
    f = b / "only-in-b.mp4"
    f.write_bytes(b"x")

    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(a))
    assert vmp.resolve_video_media_file(str(f)) is None
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(b))
    assert vmp.resolve_video_media_file(str(f)) == f.resolve()


# --- path-shape contract -------------------------------------------------


def test_bare_relative_name_fails_closed(root, monkeypatch):
    """The canonical writer never emits a bare name — do not hunt for it."""
    _mp4(root, "fixture.mp4")
    monkeypatch.chdir(root)  # even standing in the root, a bare name is refused
    assert vmp.resolve_video_media_file("fixture.mp4") is None


def test_traversal_is_refused(root, tmp_path):
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"x")
    assert vmp.resolve_video_media_file(str(root / ".." / "secret.mp4")) is None


def test_missing_and_directory_and_empty_refused(root):
    assert vmp.resolve_video_media_file(str(root / "nope.mp4")) is None
    d = root / "adir"
    d.mkdir()
    assert vmp.resolve_video_media_file(str(d)) is None
    assert vmp.resolve_video_media_file("") is None
    assert vmp.resolve_video_media_file("   ") is None


@pytest.mark.skipif(os.name == "nt", reason="symlink creation needs privilege on Windows")
def test_symlink_components_refused(root, tmp_path):
    """BOTH an escaping symlink and an in-root symlink are refused."""
    real = _mp4(root, "real.mp4")
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"x")

    escaping = root / "escaping.mp4"
    escaping.symlink_to(outside)
    assert vmp.resolve_video_media_file(str(escaping)) is None

    in_root = root / "in_root.mp4"
    in_root.symlink_to(real)  # retargetable after approval → refused
    assert vmp.resolve_video_media_file(str(in_root)) is None

    sub = root / "sub"
    sub.mkdir()
    linked_dir = root / "linkdir"
    linked_dir.symlink_to(sub, target_is_directory=True)
    via_dir = linked_dir / "f.mp4"
    (sub / "f.mp4").write_bytes(b"x")
    assert vmp.resolve_video_media_file(str(via_dir)) is None
