"""Stage 1 — approval binds to the bytes the customer actually previewed.

Before this, approve carried only `expected_revision`: an in-place re-render at
the same revision between preview and approve was invisible. Now the preview
returns the exact digest, the media responses carry a strong ETag over those
same bytes, and approve refuses `approval_content_changed` on any drift.

Every refusal must happen BEFORE any approval-ledger write, video-record
update, snapshot or provider call.
"""

from __future__ import annotations

import hashlib

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.marketing import clients_store
from app.marketing import video_ad_cycle as V

TENANT = "fixture-tenant-p"


@pytest.fixture
def preview_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", "*")
    # HERMETIC PRECONDITION (do not remove): approve() snapshots to the host filesystem
    # and refuses `insufficient_disk_headroom` below VIDEO_SNAPSHOT_MIN_FREE_PCT. These
    # tests are about preview/approve IDENTITY, so the host's free space must not decide
    # the result — unpinned, they go red on any box under the default floor. The floor
    # has dedicated coverage in tests/test_video_snapshot_primitive.py.
    monkeypatch.setenv("VIDEO_SNAPSHOT_MIN_FREE_PCT", "1")

    from app.api.customer_auth import require_customer

    async def _cust():
        return TENANT

    app.dependency_overrides[require_customer] = _cust

    from app.marketing import video_pipeline

    root = tmp_path / "reels"
    root.mkdir()
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(root))
    monkeypatch.setattr(V, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(V, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())
    # Stage 3B-close: approval now requires two POSITIVE server-side facts that
    # require_customer does not establish — the tenant really resolves, and the
    # logout blacklist was actually reachable (its check fails OPEN, which is
    # not acceptable for a mutation). Both are stubbed here so this fixture
    # represents a healthy authenticated session.
    monkeypatch.setattr(
        clients_store, "resolve_client", lambda cid: {"id": str(cid or "").strip()}, raising=False
    )

    class _Redis:
        async def exists(self, _key):
            return 0

    async def _get_redis():
        return _Redis()

    monkeypatch.setattr("app.cache.get_redis_client", _get_redis)

    from app.marketing import auto_content, content_approval

    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))
    # Approval emits a queue row. Without this every consumer of this fixture
    # wrote fixture tenants into the REPO's data/content_queue, where they
    # survived between runs — and auto_content dedupes on date|type, so a
    # leftover row silently suppresses a later enqueue.
    queue_dir = tmp_path / "content_queue"
    queue_dir.mkdir()
    monkeypatch.setattr(auto_content, "_QUEUE_DIR", lambda: str(queue_dir))
    submitted = content_approval.submit(TENANT, {"type": "video_ad", "title": "Preview fixture"})
    approval = submitted["approval"]

    artifact = root / "preview.mp4"
    artifact.write_bytes(b"PREVIEW-A" * 512)
    V._append(
        {
            "id": "vid-preview-1",
            "client_id": TENANT,
            "approval_id": approval["id"],
            "token": approval["token"],
            "status": "pending",
            "revision": 0,
            "video_path": str(artifact),
        }
    )
    with TestClient(app) as c:
        # require_customer is overridden, but the approval path ALSO reads the
        # bearer credential directly to re-check the logout blacklist. Without a
        # header there is no credential to verify, and approval correctly fails
        # closed — so a healthy session must actually present one.
        _fixture_auth = "Bearer fixture-session-token"  # nosecret - test fixture
        c.headers.update({"Authorization": _fixture_auth})
        yield c, artifact
    app.dependency_overrides.clear()


def _sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# --- preview identity ----------------------------------------------------


def test_preview_returns_revision_hash_and_size(preview_client):
    c, artifact = preview_client
    r = c.get("/api/customer/videos/vid-preview-1/preview")
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True
    assert d["revision"] == 0
    assert d["content_sha256"] == _sha(artifact)
    assert d["content_bytes"] == artifact.stat().st_size
    assert d["etag"] == f'"sha256-{_sha(artifact)}"'


def test_preview_never_exposes_filesystem_path(preview_client):
    c, artifact = preview_client
    body = c.get("/api/customer/videos/vid-preview-1/preview").text
    assert str(artifact) not in body and "video_path" not in body


# --- ETag parity across 200 and 206 --------------------------------------


def test_full_and_range_responses_share_strong_etag(preview_client):
    c, artifact = preview_client
    expected = f'"sha256-{_sha(artifact)}"'

    full = c.get("/api/customer/videos/vid-preview-1/media?revision=0")
    assert full.status_code == 200
    assert full.headers["etag"] == expected
    assert not full.headers["etag"].startswith("W/")

    part = c.get(
        "/api/customer/videos/vid-preview-1/media?revision=0",
        headers={"Range": "bytes=0-99"},
    )
    assert part.status_code == 206
    assert part.headers["etag"] == expected
    assert part.headers["content-range"].endswith(f"/{artifact.stat().st_size}")
    assert len(part.content) == 100


def test_range_semantics_preserved(preview_client):
    c, artifact = preview_client
    size = artifact.stat().st_size
    suffix = c.get(
        "/api/customer/videos/vid-preview-1/media?revision=0",
        headers={"Range": "bytes=-50"},
    )
    assert suffix.status_code == 206 and len(suffix.content) == 50
    bad = c.get(
        "/api/customer/videos/vid-preview-1/media?revision=0",
        headers={"Range": f"bytes={size + 10}-"},
    )
    assert bad.status_code == 416


# --- approve is bound to the previewed identity --------------------------


def _approve(c, **over):
    body = {"action": "approve", "expected_revision": 0}
    body.update(over)
    return c.post("/api/customer/videos/vid-preview-1/feedback", json=body)


def test_approve_requires_expected_hash(preview_client):
    c, _ = preview_client
    assert _approve(c).status_code == 400


@pytest.mark.parametrize("bad", ["", "   ", "nothex", "a" * 63, "A" * 64 + "b"])
def test_malformed_expected_hash_fails_closed(preview_client, bad):
    c, _ = preview_client
    assert _approve(c, expected_content_sha256=bad).status_code in (400, 422)


def test_overwritten_same_revision_refuses_content_changed(preview_client):
    c, artifact = preview_client
    previewed = c.get("/api/customer/videos/vid-preview-1/preview").json()["content_sha256"]
    artifact.write_bytes(b"PREVIEW-B" * 512)  # same revision, new bytes
    r = _approve(c, expected_content_sha256=previewed)
    assert r.status_code == 409
    assert "approval_content_changed" in r.text


def test_wrong_revision_refused(preview_client):
    c, artifact = preview_client
    r = _approve(c, expected_revision=7, expected_content_sha256=_sha(artifact))
    assert r.status_code == 409


def test_wrong_tenant_refused(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.api.customer_auth import require_customer

    async def _other():
        return "some-other-tenant"

    app.dependency_overrides[require_customer] = _other
    assert c.get("/api/customer/videos/vid-preview-1/preview").status_code == 404
    assert _approve(c, expected_content_sha256=_sha(artifact)).status_code == 404


def test_mismatch_writes_nothing_and_calls_no_provider(preview_client, monkeypatch):
    c, artifact = preview_client
    from app.marketing import content_approval
    from app.marketing import postiz_publish as pp

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

    previewed = c.get("/api/customer/videos/vid-preview-1/preview").json()["content_sha256"]
    artifact.write_bytes(b"TAMPERED" * 512)
    assert _approve(c, expected_content_sha256=previewed).status_code == 409
    assert calls == {"postiz": 0, "update": 0, "decide": 0}


def test_matching_hash_approves(preview_client):
    c, artifact = preview_client
    pv = c.get("/api/customer/videos/vid-preview-1/preview").json()
    r = _approve(c, expected_revision=pv["revision"], expected_content_sha256=pv["content_sha256"])
    assert r.status_code == 200 and r.json()["ok"] is True
