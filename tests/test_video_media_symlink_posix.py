"""POSIX symlink-component proof for the media-root authority.

Production runs Linux; Windows dev boxes skip symlink creation because it needs
a privilege. This module imports ONLY `video_media_paths` (no FastAPI, no app
bootstrap) so it can run in a minimal, network-disabled Linux container:

    docker run --rm --network none -v <worktree>:/w:ro -w /w python:3.12-slim \
        sh -c "pip install -q pytest && python -m pytest tests/test_video_media_symlink_posix.py -q"

Both the ESCAPING symlink and the IN-ROOT symlink must refuse: an in-root
symlink is retargetable after approval, which would defeat the content binding.
"""

from __future__ import annotations

import os

import pytest

from app.marketing import video_media_paths as vmp

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX symlink semantics")


@pytest.fixture
def root(tmp_path, monkeypatch):
    r = tmp_path / "reels"
    r.mkdir()
    # Patch the authority's own root accessors so this module never imports the
    # renderer (PIL / edge-tts) — keeps the Linux container minimal and offline.
    monkeypatch.setattr(vmp, "reels_dir", lambda: r)
    monkeypatch.setattr(vmp, "video_ads_dir", lambda: r)
    return r


def _mp4(path, payload=b"bytes" * 100):
    path.write_bytes(payload)
    return path


def test_plain_in_root_file_is_accepted(root):
    """Control: without any symlink the same shape resolves fine."""
    p = _mp4(root / "plain.mp4")
    assert vmp.resolve_video_media_file(str(p)) == p.resolve()


def test_escaping_symlink_refused(root, tmp_path):
    outside = _mp4(tmp_path / "outside.mp4")
    link = root / "escaping.mp4"
    link.symlink_to(outside)
    assert link.is_symlink()
    assert vmp.resolve_video_media_file(str(link)) is None


def test_in_root_symlink_refused(root):
    """Refused even though it currently points inside the root."""
    real = _mp4(root / "real.mp4")
    link = root / "in_root.mp4"
    link.symlink_to(real)
    assert link.is_symlink()
    assert link.resolve() == real.resolve()  # target is legitimate *right now*
    assert vmp.resolve_video_media_file(str(link)) is None


def test_symlinked_parent_directory_refused(root):
    sub = root / "sub"
    sub.mkdir()
    _mp4(sub / "f.mp4")
    linked_dir = root / "linkdir"
    linked_dir.symlink_to(sub, target_is_directory=True)
    assert vmp.resolve_video_media_file(str(linked_dir / "f.mp4")) is None


def test_symlink_retarget_after_first_accept_is_still_refused(root, tmp_path):
    """The retarget scenario the policy exists for."""
    real = _mp4(root / "approved.mp4", b"A" * 512)
    link = root / "served.mp4"
    link.symlink_to(real)
    assert vmp.resolve_video_media_file(str(link)) is None

    evil = _mp4(tmp_path / "evil.mp4", b"B" * 512)
    link.unlink()
    link.symlink_to(evil)
    assert vmp.resolve_video_media_file(str(link)) is None
