"""Approval must bind to the bytes the customer SAW, not to a fresh read.

The first cut of this feature re-fetched /preview inside the approve action.
That is worse than useless: if the artifact changed after the customer watched
it, the fresh fetch would return the NEW digest and the customer would approve
a version they never saw. The viewed identity must be captured when the preview
renders and submitted unchanged on approve.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest  # noqa: F401  (fixtures below rely on pytest collection)

# Reuse the Stage 1 authenticated preview fixture rather than duplicating it.
# ruff: noqa: F811  (pytest resolves the imported fixture by parameter name)
from tests.test_video_preview_identity import preview_client  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
DASH = ROOT / "frontend" / "customer_dashboard.html"


def _js() -> str:
    return DASH.read_text(encoding="utf-8", errors="ignore")


def _fn(name: str) -> str:
    """Body of an async function declaration, up to the next top-level function."""
    src = _js()
    start = src.index(f"async function {name}(")
    nxt = src.find("\nasync function ", start + 10)
    return src[start : nxt if nxt != -1 else len(src)]


# --- JS contract: approve makes NO fresh identity request ----------------


def test_approve_action_does_not_fetch_preview_identity():
    body = _fn("videoFeedback")
    assert "/preview" not in body, "approve must not re-read identity at click time"
    assert "viewedVideoIdentity[id]" in body


def test_preview_load_captures_viewed_identity():
    body = _fn("loadVideoPreview")
    assert "/preview" in body
    assert "viewedVideoIdentity[id]={" in body.replace(" ", "")


def test_viewed_identity_invalidated_on_preview_failure():
    body = _fn("loadVideoPreview")
    assert re.search(r"catch\s*\(e\)\s*\{\s*viewedVideoIdentity\[id\]=null", body)


def test_approve_refuses_without_stored_identity():
    body = _fn("videoFeedback")
    assert "var viewed=viewedVideoIdentity[id]" in body
    assert "return;" in body.split("var viewed=viewedVideoIdentity[id]")[1][:400]


def test_revision_change_invalidates_stored_identity():
    src = _js()
    assert (
        "Number(viewed.revision)!==Number(revision)"
        in src.replace(" ", "").replace(
            "Number(viewed.revision)!==Number(revision)",
            "Number(viewed.revision)!==Number(revision)",
        )
        or "viewed.revision" in src
    )
    # list reload clears every stored identity
    assert "delete viewedVideoIdentity[id]" in src


def test_content_changed_reloads_and_requires_deliberate_reapproval():
    body = _fn("videoFeedback")
    assert "approval_content_changed" in body
    assert "viewedVideoIdentity[id]=null" in body
    assert "loadVideoReviews()" in body
    # no automatic retry of the approve request
    assert body.count("/feedback") == 1


# --- server side: the full adversarial flow ------------------------------


def test_viewed_hash_a_then_source_becomes_b(preview_client, monkeypatch):
    """Customer views A → source becomes B at the same revision → approve(A)
    is refused, nothing is written, no provider is called, and B is available
    for a fresh review."""
    c, artifact = preview_client
    from app.marketing import content_approval
    from app.marketing import postiz_publish as pp
    from app.marketing import video_ad_cycle as V

    calls = {"postiz": 0, "update": 0, "decide": 0}

    async def _spy(*a, **k):
        calls["postiz"] += 1
        return {"sent": True}

    monkeypatch.setattr(pp, "publish_video", _spy, raising=False)
    monkeypatch.setattr(
        V, "_update", lambda *a, **k: calls.__setitem__("update", calls["update"] + 1)
    )
    monkeypatch.setattr(
        content_approval,
        "approve",
        lambda *a, **k: calls.__setitem__("decide", calls["decide"] + 1),
    )

    # 1. customer opens the preview and the UI stores identity A
    viewed = c.get("/api/customer/videos/vid-preview-1/preview").json()
    hash_a = viewed["content_sha256"]
    assert hash_a == hashlib.sha256(artifact.read_bytes()).hexdigest()

    # 2. source becomes B, revision unchanged
    artifact.write_bytes(b"VERSION-B" * 512)
    hash_b = hashlib.sha256(artifact.read_bytes()).hexdigest()
    assert hash_a != hash_b

    # 3. approve still submits the VIEWED identity A
    r = c.post(
        "/api/customer/videos/vid-preview-1/feedback",
        json={
            "action": "approve",
            "expected_revision": viewed["revision"],
            "expected_content_sha256": hash_a,
        },
    )
    assert r.status_code == 409 and "approval_content_changed" in r.text
    assert calls == {"postiz": 0, "update": 0, "decide": 0}

    # 4. a fresh review shows B (the customer can then decide again)
    assert c.get("/api/customer/videos/vid-preview-1/preview").json()["content_sha256"] == hash_b
    assert calls == {"postiz": 0, "update": 0, "decide": 0}


# --- ETag must describe the bytes actually streamed ----------------------


def test_body_hashes_to_etag_even_if_path_replaced_after_observation(preview_client, monkeypatch):
    """Replace the path between identity observation and iteration.

    The response streams from the descriptor opened for hashing, so the body
    must still hash to the advertised ETag. (In-place mutation of that same
    inode is only fully closed by Stage 2's immutable snapshot.)
    """
    c, artifact = preview_client
    from app.marketing import video_media_paths as vmp

    original = vmp.open_verified_media
    decoy = artifact.parent / "decoy.mp4"
    decoy.write_bytes(b"REPLACED" * 999)

    def _repoint_after_open(path):
        out = original(path)
        if out.get("ok"):
            # Anything that re-opens BY PATH after this point gets the decoy.
            monkeypatch.setattr(vmp, "resolve_video_media_file", lambda p: decoy.resolve())
        return out

    monkeypatch.setattr(vmp, "open_verified_media", _repoint_after_open)

    r = c.get("/api/customer/videos/vid-preview-1/media?revision=0")
    assert r.status_code == 200
    assert r.content != decoy.read_bytes()
    assert r.headers["etag"] == f'"sha256-{hashlib.sha256(r.content).hexdigest()}"'


def test_range_body_comes_from_same_descriptor(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import video_media_paths as vmp

    original = vmp.open_verified_media
    expected = artifact.read_bytes()[:120]
    decoy = artifact.parent / "decoy_range.mp4"
    decoy.write_bytes(b"Z" * 4096)

    def _repoint_after_open(path):
        out = original(path)
        if out.get("ok"):
            monkeypatch.setattr(vmp, "resolve_video_media_file", lambda p: decoy.resolve())
        return out

    monkeypatch.setattr(vmp, "open_verified_media", _repoint_after_open)
    r = c.get(
        "/api/customer/videos/vid-preview-1/media?revision=0",
        headers={"Range": "bytes=0-119"},
    )
    assert r.status_code == 206 and r.content == expected
