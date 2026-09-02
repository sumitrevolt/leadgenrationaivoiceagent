"""Studio Media tools — security + functionality (upload/serve/IDOR + image tools)."""

import io

from fastapi.testclient import TestClient

from app.api.admin import create_access_token
from app.main import app
from tests._api_helpers import iter_mounted_routes

_TOK = create_access_token("media-test-c", "m@test.com", "customer")
_H = {"Authorization": f"Bearer {_TOK}"}


def _png(size=(64, 64)) -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "#abcdef").save(buf, "PNG")
    return buf.getvalue()


def test_media_routes_mounted():
    paths = {r.path for r in iter_mounted_routes(app)}
    for p in [
        "/api/customer/studio/upload",
        "/api/customer/studio/media/{media_id}",
        "/api/customer/studio/img-gif",
        "/api/customer/studio/img-sticker",
        "/api/customer/studio/img-resize",
        "/api/customer/studio/img-bgremove",
    ]:
        assert p in paths, f"missing {p}"


def test_media_requires_auth():
    c = TestClient(app)
    assert c.post(
        "/api/customer/studio/upload", files={"file": ("a.png", _png(), "image/png")}
    ).status_code in (401, 403)
    assert c.post("/api/customer/studio/img-gif", json={}).status_code in (401, 403)
    assert c.get("/api/customer/studio/media/" + "a" * 32).status_code in (401, 403)


def test_gif_generate_and_serve():
    c = TestClient(app)
    r = c.post("/api/customer/studio/img-gif", headers=_H, json={"text": "SALE", "style": "pop"})
    assert r.status_code == 200
    media = r.json().get("media")
    assert media and media[0]["media_id"]
    mid = media[0]["media_id"]
    s = c.get(f"/api/customer/studio/media/{mid}", headers=_H)
    assert (
        s.status_code == 200 and s.headers["content-type"] == "image/gif" and len(s.content) > 100
    )


def test_sticker_pack_six():
    c = TestClient(app)
    r = c.post("/api/customer/studio/img-sticker", headers=_H, json={})
    assert r.status_code == 200
    assert len(r.json().get("media", [])) == 6


def test_serve_idor_blocked():
    """A different client must NOT be able to fetch another client's media."""
    c = TestClient(app)
    mid = c.post("/api/customer/studio/img-gif", headers=_H, json={"text": "X"}).json()["media"][0][
        "media_id"
    ]
    attacker = {"Authorization": f"Bearer {create_access_token('attacker', 'a@x.com', 'customer')}"}
    assert c.get(f"/api/customer/studio/media/{mid}", headers=attacker).status_code == 404


def test_serve_rejects_traversal_and_bad_id():
    c = TestClient(app)
    assert c.get("/api/customer/studio/media/..%2f..%2fetc%2fpasswd", headers=_H).status_code == 404
    assert c.get("/api/customer/studio/media/notahexid", headers=_H).status_code == 404


def test_upload_rejects_non_image_magic_bytes():
    """A text/script file with .png name is rejected (magic-byte sniff, not extension)."""
    c = TestClient(app)
    bad = b"<script>alert(1)</script>" * 5
    r = c.post(
        "/api/customer/studio/upload", headers=_H, files={"file": ("evil.png", bad, "image/png")}
    )
    assert r.status_code == 415


def test_upload_rejects_oversize():
    c = TestClient(app)
    big = b"\x89PNG\r\n\x1a\n" + b"0" * (9 * 1024 * 1024)
    r = c.post(
        "/api/customer/studio/upload", headers=_H, files={"file": ("big.png", big, "image/png")}
    )
    assert r.status_code == 413


def test_upload_then_resize():
    c = TestClient(app)
    up = c.post(
        "/api/customer/studio/upload", headers=_H, files={"file": ("a.png", _png(), "image/png")}
    )
    assert up.status_code == 200
    uid = up.json()["upload_id"]
    rz = c.post(
        "/api/customer/studio/img-resize",
        headers=_H,
        json={"upload_id": uid, "sizes": ["square", "story"]},
    )
    assert rz.status_code == 200
    assert len(rz.json().get("media", [])) == 2


def test_resize_rejects_foreign_upload_id():
    """upload_id only resolves inside the authed client's own dir."""
    c = TestClient(app)
    r = c.post("/api/customer/studio/img-resize", headers=_H, json={"upload_id": "f" * 32})
    assert r.status_code == 404


def test_video_reel_submit_or_graceful():
    """Reel submit returns a job_id (ffmpeg present) OR graceful ok:false — never 500."""
    c = TestClient(app)
    r = c.post("/api/customer/studio/video-reel", headers=_H, json={"offer": "Sale"})
    assert r.status_code == 200
    d = r.json()
    assert (d.get("ok") and d.get("job_id")) or (d.get("ok") is False and d.get("note"))


def test_video_status_bad_id():
    c = TestClient(app)
    assert c.get("/api/customer/studio/video-status/notahex", headers=_H).status_code == 404
    assert c.get("/api/customer/studio/video-status/" + "a" * 32, headers=_H).status_code == 404
    assert c.get("/api/customer/studio/video-status/" + "a" * 32).status_code in (401, 403)


def test_bgremove_graceful_without_rembg():
    c = TestClient(app)
    up = c.post(
        "/api/customer/studio/upload", headers=_H, files={"file": ("a.png", _png(), "image/png")}
    )
    uid = up.json()["upload_id"]
    r = c.post("/api/customer/studio/img-bgremove", headers=_H, json={"upload_id": uid})
    # either ok (rembg present) or graceful ok:false with a note — never 500
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True or (d.get("ok") is False and d.get("note"))
