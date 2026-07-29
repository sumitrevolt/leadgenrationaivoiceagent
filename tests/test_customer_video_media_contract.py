"""Contract tests for /api/customer/videos/{id}/media HTTP Range + revision gate.

Ported from antigravity/ws3-video-preview-clean (PR #101) and adapted for main's
revision-gated media endpoint — Range is additive; version mismatch stays 409.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.admin import create_access_token
from app.main import app
from app.marketing import clients_store, video_ad_cycle


def _mint_customer_token(client_id: str) -> dict[str, str]:
    tok = create_access_token(client_id, f"{client_id}@example.com", "customer")
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture
def media_client(monkeypatch, tmp_path):
    """Authenticated customer media client with isolated store + review flags ON."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_ENABLED", "1")
    monkeypatch.setenv("VIDEO_CUSTOMER_REVIEW_CLIENTS", "*")

    from app.api import customer_dashboard

    allowed = tmp_path / "video_ads"
    allowed.mkdir(parents=True)
    from app.marketing import video_pipeline

    monkeypatch.setattr(video_pipeline, "output_root", lambda: str(allowed))
    monkeypatch.setattr(video_ad_cycle, "_FILE", str(tmp_path / "video_ads.jsonl"))
    monkeypatch.setattr(video_ad_cycle, "_STATE", str(tmp_path / ".cycle.json"))
    monkeypatch.setattr(clients_store, "canonical_client_id", lambda cid: str(cid or "").strip())

    with TestClient(app) as c:
        yield c, allowed


def _write_mp4(root: Path, name: str, payload: bytes) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def test_unauthenticated_access():
    with TestClient(app) as c:
        assert c.get("/api/customer/videos").status_code in (401, 403)
        assert c.get("/api/customer/videos/vid123/media?revision=0").status_code in (401, 403)


def test_revision_required_and_stale_rejected(media_client):
    client, allowed = media_client
    payload = b"\x00\x00\x00\x18ftypmp42" + b"A" * 40
    mp4 = _write_mp4(allowed, "tenant-a/rev.mp4", payload)
    video_ad_cycle._append(
        {
            "id": "vid_rev",
            "client_id": "tenant-a",
            "video_path": str(mp4),
            "status": "pending",
            "revision": 3,
        }
    )
    hdr = _mint_customer_token("tenant-a")

    missing = client.get("/api/customer/videos/vid_rev/media", headers=hdr)
    assert missing.status_code == 422

    stale = client.get("/api/customer/videos/vid_rev/media?revision=2", headers=hdr)
    assert stale.status_code == 409

    ok = client.get("/api/customer/videos/vid_rev/media?revision=3", headers=hdr)
    assert ok.status_code == 200
    assert ok.content == payload


def test_cross_tenant_isolation(media_client):
    client, allowed = media_client
    payload = b"\x00\x00\x00\x18ftypmp42" + b"B" * 40
    mp4 = _write_mp4(allowed, "tenant-a/iso.mp4", payload)
    video_ad_cycle._append(
        {
            "id": "vid_tenant_a",
            "client_id": "tenant-a",
            "video_path": str(mp4),
            "status": "pending",
            "revision": 0,
        }
    )

    assert (
        client.get(
            "/api/customer/videos/vid_tenant_a/media?revision=0",
            headers=_mint_customer_token("tenant-b"),
        ).status_code
        == 404
    )

    res_a = client.get(
        "/api/customer/videos/vid_tenant_a/media?revision=0",
        headers=_mint_customer_token("tenant-a"),
    )
    assert res_a.status_code == 200
    assert res_a.content == payload


def test_path_outside_root_and_missing_file(media_client, tmp_path):
    client, allowed = media_client
    outside = tmp_path / "secret.mp4"
    outside.write_bytes(b"SECRET_MP4_BYTES")
    video_ad_cycle._append(
        {
            "id": "vid_outside",
            "client_id": "cust123",
            "video_path": str(outside),
            "status": "pending",
            "revision": 0,
        }
    )
    video_ad_cycle._append(
        {
            "id": "vid_missing",
            "client_id": "cust123",
            "video_path": str(allowed / "gone.mp4"),
            "status": "pending",
            "revision": 0,
        }
    )
    hdr = _mint_customer_token("cust123")
    assert (
        client.get("/api/customer/videos/vid_outside/media?revision=0", headers=hdr).status_code
        == 404
    )
    assert (
        client.get("/api/customer/videos/vid_missing/media?revision=0", headers=hdr).status_code
        == 404
    )

    listing = client.get("/api/customer/videos", headers=hdr).json()
    by_id = {v["id"]: v for v in listing["videos"]}
    assert by_id["vid_outside"]["has_video"] is False
    assert by_id["vid_outside"]["media_url"] is None
    assert by_id["vid_missing"]["has_video"] is False
    assert by_id["vid_missing"]["media_url"] is None


def test_non_mp4_rejected(media_client):
    client, allowed = media_client
    txt = allowed / "malicious.txt"
    txt.write_text("not a video")
    video_ad_cycle._append(
        {
            "id": "v1",
            "client_id": "cust123",
            "video_path": str(txt),
            "status": "pending",
            "revision": 0,
        }
    )
    hdr = _mint_customer_token("cust123")
    assert client.get("/api/customer/videos/v1/media?revision=0", headers=hdr).status_code == 404


def test_inline_disposition_and_headers(media_client):
    client, allowed = media_client
    mp4_bytes = b"MP4_CONTENT_12345"
    mp4 = _write_mp4(allowed, "cust123/headers.mp4", mp4_bytes)
    video_ad_cycle._append(
        {
            "id": "vid_hdr",
            "client_id": "cust123",
            "video_path": str(mp4),
            "status": "pending",
            "revision": 1,
        }
    )
    hdr = _mint_customer_token("cust123")
    res = client.get("/api/customer/videos/vid_hdr/media?revision=1", headers=hdr)

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("video/mp4")
    assert res.headers["content-disposition"] == 'inline; filename="video_ad_vid_hdr.mp4"'
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["content-length"] == str(len(mp4_bytes))
    assert "private" in res.headers.get("cache-control", "")
    assert res.content == mp4_bytes


def test_range_request_behavior(media_client):
    client, allowed = media_client
    # 100 bytes payload (pairs of digits 00..49)
    mp4_bytes = b"".join(f"{i:02d}".encode() for i in range(50))
    total_len = len(mp4_bytes)
    mp4 = _write_mp4(allowed, "cust123/range.mp4", mp4_bytes)
    video_ad_cycle._append(
        {
            "id": "vid_range",
            "client_id": "cust123",
            "video_path": str(mp4),
            "status": "pending",
            "revision": 0,
        }
    )
    hdr = _mint_customer_token("cust123")
    url = "/api/customer/videos/vid_range/media?revision=0"

    res_part1 = client.get(url, headers={**hdr, "Range": "bytes=0-9"})
    assert res_part1.status_code == 206
    assert res_part1.headers["content-range"] == f"bytes 0-9/{total_len}"
    assert res_part1.headers["content-length"] == "10"
    assert res_part1.content == mp4_bytes[:10]

    res_part2 = client.get(url, headers={**hdr, "Range": "bytes=50-"})
    assert res_part2.status_code == 206
    assert res_part2.headers["content-range"] == f"bytes 50-{total_len - 1}/{total_len}"
    assert res_part2.headers["content-length"] == str(total_len - 50)
    assert res_part2.content == mp4_bytes[50:]

    res_suffix = client.get(url, headers={**hdr, "Range": "bytes=-20"})
    assert res_suffix.status_code == 206
    assert (
        res_suffix.headers["content-range"] == f"bytes {total_len - 20}-{total_len - 1}/{total_len}"
    )
    assert res_suffix.headers["content-length"] == "20"
    assert res_suffix.content == mp4_bytes[-20:]

    res_multi = client.get(url, headers={**hdr, "Range": "bytes=0-10, 20-30"})
    assert res_multi.status_code == 416
    assert res_multi.headers["content-range"] == f"bytes */{total_len}"

    res_malformed = client.get(url, headers={**hdr, "Range": "bytes=invalid-range"})
    assert res_malformed.status_code == 416
    assert res_malformed.headers["content-range"] == f"bytes */{total_len}"

    res_unsat = client.get(url, headers={**hdr, "Range": "bytes=500-600"})
    assert res_unsat.status_code == 416
    assert res_unsat.headers["content-range"] == f"bytes */{total_len}"


def test_range_still_enforces_revision_gate(media_client):
    client, allowed = media_client
    mp4 = _write_mp4(allowed, "cust123/race.mp4", b"0123456789abcdef")
    video_ad_cycle._append(
        {
            "id": "vid_race",
            "client_id": "cust123",
            "video_path": str(mp4),
            "status": "pending",
            "revision": 5,
        }
    )
    hdr = _mint_customer_token("cust123")
    stale = client.get(
        "/api/customer/videos/vid_race/media?revision=4",
        headers={**hdr, "Range": "bytes=0-3"},
    )
    assert stale.status_code == 409
