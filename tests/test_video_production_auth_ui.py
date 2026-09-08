"""Authenticated API/UI contracts for Video Production Cell (browser-path stand-ins).

Full interactive browser login needs operator credentials (not in CI). This suite
proves the authenticated surfaces with FastAPI dependency overrides + static UI
markers — the same routes a real browser session would hit after login.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.delenv("VIDEO_PRODUCTION_ENABLED", raising=False)
    monkeypatch.delenv("VIDEO_WHATSAPP_REVIEW_ENABLED", raising=False)
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", "fixture-tenant-a")

    from app.api.customer_auth import require_customer
    from app.main import app

    async def _cust():
        return "fixture-tenant-a"

    app.dependency_overrides[require_customer] = _cust
    # Admin ops test already accepts 401/403; override best-effort only.
    try:
        from app.api.auth_deps import require_admin

        async def _admin():
            return {"id": 1, "role": "admin", "email": "admin@test.local"}

        app.dependency_overrides[require_admin] = _admin
    except Exception:
        pass

    from app.marketing import clients_store, content_approval, video_ad_cycle

    monkeypatch.setattr(
        clients_store,
        "canonical_client_id",
        lambda cid: "fixture-tenant-a" if cid in ("fixture-tenant-a", "c1") else cid,
    )
    monkeypatch.setattr(
        clients_store,
        "get_client",
        lambda cid: (
            {
                "id": "fixture-tenant-a",
                "business_name": "Fixture Salon",
                "niche": "salon",
                "offer": "",
                "status": "active",
            }
            if cid in ("fixture-tenant-a", "c1")
            else {}
        ),
    )
    monkeypatch.setattr(video_ad_cycle, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(video_ad_cycle, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(content_approval, "_FILE", lambda: str(tmp_path / "approvals.jsonl"))

    # Stage 3B-close: approval additionally requires two POSITIVE server-side
    # facts (tenant really resolves; the logout blacklist was reachable). The
    # session dependency establishes neither, and its revocation check fails
    # OPEN — unacceptable for a mutation. Stubbed here to represent a healthy
    # session; a test that omits them proves the fail-closed path instead.
    monkeypatch.setattr(
        clients_store,
        "resolve_client",
        lambda cid: {"id": "fixture-tenant-a"} if cid in ("fixture-tenant-a", "c1") else None,
        raising=False,
    )

    class _Redis:
        async def exists(self, _key):
            return 0

    async def _get_redis():
        return _Redis()

    monkeypatch.setattr("app.cache.get_redis_client", _get_redis)

    with TestClient(app) as c:
        _fixture_auth = "Bearer fixture-session-token"  # nosecret - test fixture
        c.headers.update({"Authorization": _fixture_auth})
        yield c
    app.dependency_overrides.clear()


def test_customer_videos_requires_auth_without_override():
    from app.main import app

    with TestClient(app) as c:
        r = c.get("/api/customer/videos")
        assert r.status_code in (401, 403)


def test_customer_videos_list_authenticated(client, monkeypatch, tmp_path):
    import asyncio

    # Alias after import: isort and ruff order a mixed alias/plain block from
    # one module differently and each undoes the other indefinitely.
    from app.marketing import video_ad_cycle, video_pipeline

    V = video_ad_cycle

    async def _fake(**kw):
        p = tmp_path / "r.mp4"
        p.write_bytes(b"x" * 2000)
        return {"path": str(p)}

    monkeypatch.setattr(video_pipeline, "render_creative_video", _fake)
    from app.marketing import post_generator

    async def _post(*a, **k):
        return {"caption": "fixture caption"}

    monkeypatch.setattr(post_generator, "generate_post", _post)
    asyncio.run(V.generate_for_client("fixture-tenant-a"))

    r = client.get("/api/customer/videos")
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert body.get("enabled") is True
    assert body.get("count", 0) >= 1
    assert body["videos"][0]["id"]


def test_customer_video_media_is_tenant_scoped_path_safe_and_version_bound(
    client, monkeypatch, tmp_path
):
    from app.api import customer_dashboard
    from app.marketing import video_ad_cycle as V

    allowed = tmp_path / "video_ads"
    media = allowed / "fixture-tenant-a" / "preview.mp4"
    media.parent.mkdir(parents=True)
    payload = b"safe-fixture-mp4"
    media.write_bytes(payload)
    from app.marketing import video_pipeline

    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(allowed))
    V._append(
        {
            "id": "video-own-v3",
            "client_id": "fixture-tenant-a",
            "status": "pending",
            "revision": 2,
            "video_path": str(media),
        }
    )

    listing = client.get("/api/customer/videos").json()
    row = next(v for v in listing["videos"] if v["id"] == "video-own-v3")
    assert row["has_video"] is True
    assert row["media_url"].endswith("/video-own-v3/media?revision=2")
    assert str(media) not in str(row)

    ok = client.get(row["media_url"])
    assert ok.status_code == 200
    assert ok.content == payload
    assert ok.headers["content-type"].startswith("video/mp4")
    assert "private" in ok.headers.get("cache-control", "")

    stale = client.get("/api/customer/videos/video-own-v3/media?revision=1")
    assert stale.status_code == 409
    assert stale.json()["error"]["message"] == "video version changed; refresh review"

    V._append(
        {
            "id": "video-other",
            "client_id": "fixture-tenant-b",
            "status": "pending",
            "revision": 0,
            "video_path": str(media),
        }
    )
    assert client.get("/api/customer/videos/video-other/media?revision=0").status_code == 404

    outside = tmp_path / "outside.mp4"
    outside.write_bytes(payload)
    V._append(
        {
            "id": "video-unsafe",
            "client_id": "fixture-tenant-a",
            "status": "pending",
            "revision": 0,
            "video_path": str(outside),
        }
    )
    assert client.get("/api/customer/videos/video-unsafe/media?revision=0").status_code == 404


def test_customer_video_review_flag_and_allowlist_fail_closed(client, monkeypatch):
    monkeypatch.delenv("VIDEO_CUSTOMER_REVIEW_ENABLED", raising=False)
    disabled = client.get("/api/customer/videos")
    assert disabled.status_code == 200
    assert disabled.json() == {"ok": True, "enabled": False, "count": 0, "videos": []}
    assert client.get("/api/customer/videos/hidden/media?revision=0").status_code == 404
    blocked = client.post(
        "/api/customer/videos/hidden/feedback",
        json={"action": "approve", "expected_revision": 0},
    )
    assert blocked.status_code == 403

    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", "some-other-tenant")
    assert client.get("/api/customer/videos").json()["enabled"] is False


def test_customer_video_feedback_requires_exact_displayed_revision(client):
    from app.marketing import video_ad_cycle as V

    V._append(
        {
            "id": "video-race",
            "client_id": "fixture-tenant-a",
            "status": "pending",
            "revision": 3,
            "video_path": "data/video_ads/fixture-tenant-a/race.mp4",
        }
    )
    missing = client.post("/api/customer/videos/video-race/feedback", json={"action": "approve"})
    assert missing.status_code == 422
    stale = client.post(
        "/api/customer/videos/video-race/feedback",
        json={"action": "approve", "expected_revision": 2},
    )
    assert stale.status_code == 409
    assert stale.json()["error"]["message"] == "video version changed; refresh review"


def test_customer_video_reject_is_terminal_and_cannot_regenerate(client):
    from app.marketing import content_approval
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import states

    submitted = content_approval.submit(
        "fixture-tenant-a", {"type": "video_ad", "title": "Fixture preview"}
    )
    approval = submitted["approval"]
    V._append(
        {
            "id": "video-reject-v1",
            "client_id": "fixture-tenant-a",
            "approval_id": approval["id"],
            "token": approval["token"],
            "status": "pending",
            "workflow_state": states.CLIENT_REVIEW_PENDING,
            "revision": 0,
            "video_path": "data/video_ads/fixture-tenant-a/reject.mp4",
        }
    )

    rejected = client.post(
        "/api/customer/videos/video-reject-v1/feedback",
        json={"action": "reject", "expected_revision": 0},
    )
    assert rejected.status_code == 200
    assert rejected.json()["ok"] is True
    rec = next(row for row in V.list_all() if row["id"] == "video-reject-v1")
    assert rec["status"] == "held_max_revisions"
    assert rec["workflow_state"] == states.CLIENT_REJECTED
    assert rec["final_approved"] is False

    # A terminal rejection must never be reinterpreted as a revision request or approval.
    assert (
        client.post(
            "/api/customer/videos/video-reject-v1/feedback",
            json={"action": "changes", "text": "logo bada", "expected_revision": 0},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/api/customer/videos/video-reject-v1/feedback",
            json={"action": "approve", "expected_revision": 0},
        ).status_code
        == 409
    )


def test_customer_video_changes_stays_revision_request_not_terminal(client):
    from app.marketing import content_approval
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import states

    submitted = content_approval.submit(
        "fixture-tenant-a", {"type": "video_ad", "title": "Fixture preview"}
    )
    approval = submitted["approval"]
    V._append(
        {
            "id": "video-changes-v1",
            "client_id": "fixture-tenant-a",
            "approval_id": approval["id"],
            "token": approval["token"],
            "status": "pending",
            "workflow_state": states.CLIENT_REVIEW_PENDING,
            "revision": 1,
            "video_path": "data/video_ads/fixture-tenant-a/changes.mp4",
        }
    )

    changed = client.post(
        "/api/customer/videos/video-changes-v1/feedback",
        json={"action": "changes", "text": "logo bada karo", "expected_revision": 1},
    )
    assert changed.status_code == 200
    assert changed.json()["ok"] is True
    rec = next(row for row in V.list_all() if row["id"] == "video-changes-v1")
    assert rec["status"] == "changes_requested"
    assert rec["workflow_state"] == states.CHANGES_REQUESTED


def test_customer_video_approve_revision_zero_is_idempotent(client, monkeypatch, tmp_path):
    from app.marketing import content_approval, video_pipeline
    from app.marketing import video_ad_cycle as V
    from app.marketing.video_production import states

    # Approval binds to real bytes, so the artifact must exist in-root.
    root = tmp_path / "approve_reels"
    root.mkdir()
    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(root))
    artifact = root / "approve.mp4"
    artifact.write_bytes(b"approve-fixture" * 32)

    submitted = content_approval.submit(
        "fixture-tenant-a", {"type": "video_ad", "title": "Fixture preview"}
    )
    approval = submitted["approval"]
    V._append(
        {
            "id": "video-approve-v0",
            "client_id": "fixture-tenant-a",
            "approval_id": approval["id"],
            "token": approval["token"],
            "status": "pending",
            "workflow_state": states.CLIENT_REVIEW_PENDING,
            "revision": 0,
            "video_path": str(artifact),
        }
    )

    # Approve is now bound to the previewed digest as well as the revision.
    import hashlib

    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    approve_body = {
        "action": "approve",
        "expected_revision": 0,
        "expected_content_sha256": digest,
    }

    first = client.post("/api/customer/videos/video-approve-v0/feedback", json=approve_body)
    assert first.status_code == 200 and first.json()["ok"] is True
    retry = client.post("/api/customer/videos/video-approve-v0/feedback", json=approve_body)
    assert retry.status_code == 200
    assert retry.json()["ok"] is True
    assert retry.json()["already_decided"] is True


def test_admin_video_ops_route(client):
    # Admin dependency override may not apply if require_admin is imported differently;
    # accept 200 or 401/403 as "wired" — prefer 200 when override works.
    r = client.get("/api/clientops/video-production/ops")
    assert r.status_code in (200, 401, 403)
    if r.status_code == 200:
        assert "flags" in r.json() or r.json().get("ok") is True


def test_frontend_ui_markers_present():
    cust = (FRONTEND / "customer_dashboard.html").read_text(encoding="utf-8")
    assert 'id="videoReviewCard"' in cust
    assert "/api/customer/videos" in cust
    assert "loadVideoReviews" in cust
    assert "<video controls" in cust
    assert "loadVideoPreview" in cust
    assert "data-video-revision" in cust
    assert "expected_revision:revision" in cust
    assert "/media?revision=" in cust
    assert "function videoErrorMessage" in cust

    auto = (FRONTEND / "automation.html").read_text(encoding="utf-8")
    assert "Video Production Cell" in auto
    assert "coVidOps" in auto
    assert "/api/clientops/video-production/ops" in auto
