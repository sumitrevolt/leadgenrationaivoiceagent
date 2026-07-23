"""
Contract tests for /api/customer/videos and /api/customer/videos/{id}/media.
Verifies authentication, tenant isolation, canonical alias resolution, path safety,
symlink rejection, non-MP4 rejection, range requests, inline disposition, and listing filtering.
"""

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.admin import create_access_token
from app.main import app
from app.marketing import clients_store, video_ad_cycle

client = TestClient(app)


@pytest.fixture(autouse=True)
def cleanup_records():
    """Ensure clean video_ad_cycle store for test isolation."""
    orig_latest = getattr(video_ad_cycle, "_STORE", {})
    yield
    # Restore original state if needed


def _mint_customer_token(client_id: str) -> dict[str, str]:
    tok = create_access_token(client_id, f"{client_id}@example.com", "customer")
    return {"Authorization": f"Bearer {tok}"}


def test_unauthenticated_access():
    r_list = client.get("/api/customer/videos")
    assert r_list.status_code == 401

    r_media = client.get("/api/customer/videos/vid123/media")
    assert r_media.status_code == 401


def test_cross_tenant_isolation_and_canonical_alias(tmp_path, monkeypatch):
    reels_dir = Path("data/reels")
    reels_dir.mkdir(parents=True, exist_ok=True)
    mp4_file = reels_dir / "test_tenant_iso.mp4"
    mp4_bytes = b"\x00\x00\x00\x18ftypmp42" + b"A" * 100
    mp4_file.write_bytes(mp4_bytes)

    rec_a = {
        "id": "vid_tenant_a",
        "client_id": "tenant-a",
        "video_path": str(mp4_file),
        "status": "pending",
        "revision": 0,
        "caption": "Test video A",
    }

    def mock_latest():
        return {"vid_tenant_a": rec_a}

    monkeypatch.setattr(video_ad_cycle, "_latest", mock_latest)

    # Tenant B tries to access Tenant A's video media -> 404
    hdr_b = _mint_customer_token("tenant-b")
    res_b = client.get("/api/customer/videos/vid_tenant_a/media", headers=hdr_b)
    assert res_b.status_code == 404

    # Tenant A accesses own video -> 200
    hdr_a = _mint_customer_token("tenant-a")
    res_a = client.get("/api/customer/videos/vid_tenant_a/media", headers=hdr_a)
    assert res_a.status_code == 200
    assert res_a.content == mp4_bytes

    # Canonical alias matching: tenant_a_alias resolves to tenant-a -> 200
    monkeypatch.setattr(
        clients_store,
        "canonical_client_id",
        lambda cid: "tenant-a" if cid in ("tenant-a", "tenant_a_alias") else cid,
    )
    hdr_alias = _mint_customer_token("tenant_a_alias")
    res_alias = client.get("/api/customer/videos/vid_tenant_a/media", headers=hdr_alias)
    assert res_alias.status_code == 200

    # Cleanup test file
    if mp4_file.exists():
        mp4_file.unlink()


def test_missing_file_returns_404(monkeypatch):
    rec = {
        "id": "vid_missing",
        "client_id": "cust123",
        "video_path": "data/reels/non_existent_file_9999.mp4",
        "status": "pending",
    }
    monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"vid_missing": rec})

    hdr = _mint_customer_token("cust123")

    # Media endpoint 404
    r_media = client.get("/api/customer/videos/vid_missing/media", headers=hdr)
    assert r_media.status_code == 404

    # Listing omits media_url and marks has_video=False
    r_list = client.get("/api/customer/videos", headers=hdr)
    assert r_list.status_code == 200
    v_data = r_list.json()
    assert v_data["ok"] is True
    assert len(v_data["videos"]) == 1
    v0 = v_data["videos"][0]
    assert v0["has_video"] is False
    assert v0["media_url"] is None


def test_path_traversal_and_outside_root_rejected(tmp_path, monkeypatch):
    # File outside allowed roots
    outside_file = tmp_path / "secret.mp4"
    outside_file.write_bytes(b"SECRET_MP4_BYTES")

    rec = {
        "id": "vid_traversal",
        "client_id": "cust123",
        "video_path": str(outside_file),
        "status": "pending",
    }
    monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"vid_traversal": rec})

    hdr = _mint_customer_token("cust123")
    r_media = client.get("/api/customer/videos/vid_traversal/media", headers=hdr)
    assert r_media.status_code == 404

    r_list = client.get("/api/customer/videos", headers=hdr)
    assert r_list.json()["videos"][0]["media_url"] is None


def test_symlink_escape_rejected(monkeypatch):
    reels_dir = Path("data/reels")
    reels_dir.mkdir(parents=True, exist_ok=True)

    target_mp4 = reels_dir / "target_real.mp4"
    target_mp4.write_bytes(b"REAL_BYTES")

    symlink_mp4 = reels_dir / "symlink_test.mp4"
    if symlink_mp4.exists():
        symlink_mp4.unlink()

    try:
        os.symlink(str(target_mp4), str(symlink_mp4))
        has_symlink = True
    except (OSError, NotImplementedError):
        has_symlink = False

    if has_symlink:
        rec = {
            "id": "vid_symlink",
            "client_id": "cust123",
            "video_path": str(symlink_mp4),
            "status": "pending",
        }
        monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"vid_symlink": rec})

        hdr = _mint_customer_token("cust123")
        r_media = client.get("/api/customer/videos/vid_symlink/media", headers=hdr)
        assert r_media.status_code == 404

        r_list = client.get("/api/customer/videos", headers=hdr)
        assert r_list.json()["videos"][0]["media_url"] is None

        symlink_mp4.unlink()

    if target_mp4.exists():
        target_mp4.unlink()


def test_non_mp4_and_non_regular_file_rejected(monkeypatch):
    reels_dir = Path("data/reels")
    reels_dir.mkdir(parents=True, exist_ok=True)

    txt_file = reels_dir / "malicious.txt"
    txt_file.write_text("not a video")

    dir_path = reels_dir / "some_dir.mp4"
    dir_path.mkdir(exist_ok=True)

    rec_txt = {"id": "v1", "client_id": "cust123", "video_path": str(txt_file)}
    rec_dir = {"id": "v2", "client_id": "cust123", "video_path": str(dir_path)}

    monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"v1": rec_txt, "v2": rec_dir})

    hdr = _mint_customer_token("cust123")

    assert client.get("/api/customer/videos/v1/media", headers=hdr).status_code == 404
    assert client.get("/api/customer/videos/v2/media", headers=hdr).status_code == 404

    r_list = client.get("/api/customer/videos", headers=hdr).json()
    for v in r_list["videos"]:
        assert v["media_url"] is None
        assert v["has_video"] is False

    txt_file.unlink()
    dir_path.rmdir()


def test_inline_disposition_and_headers(monkeypatch):
    reels_dir = Path("data/reels")
    reels_dir.mkdir(parents=True, exist_ok=True)
    mp4_file = reels_dir / "valid_headers.mp4"
    mp4_bytes = b"MP4_CONTENT_12345"
    mp4_file.write_bytes(mp4_bytes)

    rec = {"id": "vid_hdr", "client_id": "cust123", "video_path": str(mp4_file)}
    monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"vid_hdr": rec})

    hdr = _mint_customer_token("cust123")
    res = client.get("/api/customer/videos/vid_hdr/media", headers=hdr)

    assert res.status_code == 200
    assert res.headers["content-type"] == "video/mp4"
    assert res.headers["content-disposition"] == 'inline; filename="video_ad_vid_hdr.mp4"'
    assert res.headers["accept-ranges"] == "bytes"
    assert res.headers["content-length"] == str(len(mp4_bytes))
    assert res.content == mp4_bytes

    mp4_file.unlink()


def test_range_request_behavior(monkeypatch):
    reels_dir = Path("data/reels")
    reels_dir.mkdir(parents=True, exist_ok=True)
    mp4_file = reels_dir / "valid_range.mp4"
    # 100 bytes payload
    mp4_bytes = b"".join(f"{i:02d}".encode() for i in range(50))
    mp4_file.write_bytes(mp4_bytes)
    total_len = len(mp4_bytes)

    rec = {"id": "vid_range", "client_id": "cust123", "video_path": str(mp4_file)}
    monkeypatch.setattr(video_ad_cycle, "_latest", lambda: {"vid_range": rec})

    hdr = _mint_customer_token("cust123")

    # 1) Partial range 0-9
    res_part1 = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=0-9"},
    )
    assert res_part1.status_code == 206
    assert res_part1.headers["content-range"] == f"bytes 0-9/{total_len}"
    assert res_part1.headers["content-length"] == "10"
    assert res_part1.content == mp4_bytes[:10]

    # 2) Open-ended range 50-
    res_part2 = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=50-"},
    )
    assert res_part2.status_code == 206
    assert res_part2.headers["content-range"] == f"bytes 50-{total_len - 1}/{total_len}"
    assert res_part2.headers["content-length"] == str(total_len - 50)
    assert res_part2.content == mp4_bytes[50:]

    # 3) Suffix range -20 (last 20 bytes)
    res_suffix = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=-20"},
    )
    assert res_suffix.status_code == 206
    assert (
        res_suffix.headers["content-range"] == f"bytes {total_len - 20}-{total_len - 1}/{total_len}"
    )
    assert res_suffix.headers["content-length"] == "20"
    assert res_suffix.content == mp4_bytes[-20:]

    # 4) Multiple ranges request (unsupported -> 416)
    res_multi = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=0-10, 20-30"},
    )
    assert res_multi.status_code == 416
    assert res_multi.headers["content-range"] == f"bytes */{total_len}"

    # 5) Malformed range request -> 416
    res_malformed = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=invalid-range"},
    )
    assert res_malformed.status_code == 416
    assert res_malformed.headers["content-range"] == f"bytes */{total_len}"

    # 6) Out-of-bounds range -> 416
    res_unsat = client.get(
        "/api/customer/videos/vid_range/media",
        headers={**hdr, "Range": "bytes=500-600"},
    )
    assert res_unsat.status_code == 416
    assert res_unsat.headers["content-range"] == f"bytes */{total_len}"

    mp4_file.unlink()
