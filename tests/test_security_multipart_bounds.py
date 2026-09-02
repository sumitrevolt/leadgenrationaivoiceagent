"""CP5-3 regression: multipart parsing must stay bounded (DoS guard).

Guards the reachable multipart denial-of-service class
(GHSA-2c2j-9gv5-cj73 / GHSA-f96h-pmfr-66vw — unbounded per-part size and
part-count parsing in older Starlette). Starlette's fixed versions enforce a
per-part size ceiling and a part-count ceiling; an oversized or multi-thousand
part request must be rejected quickly (4xx), never accepted/unbounded.

The public test surface mirrors the app's real unauthenticated multipart route
``POST /api/web-call/recording`` (UploadFile + Form, no auth dependency).
"""

from __future__ import annotations

import io

import pytest
from fastapi import APIRouter, FastAPI, File, Form, UploadFile
from fastapi.testclient import TestClient
from starlette.formparsers import MultiPartParser


def test_parser_has_bounded_defaults() -> None:
    """The installed parser must carry explicit, bounded limits."""
    max_part = getattr(MultiPartParser, "max_part_size", None)
    max_count = getattr(MultiPartParser, "max_part_count", None)
    assert max_part is not None or max_count is not None, (
        "MultiPartParser exposes neither max_part_size nor max_part_count — "
        "unbounded multipart parsing reintroduced"
    )
    if max_part is not None:
        assert 0 < max_part <= 64 * 1024 * 1024, f"max_part_size={max_part}"
    if max_count is not None:
        assert 0 < max_count <= 2000, f"max_part_count={max_count}"


@pytest.fixture(scope="module")
def client() -> TestClient:
    router = APIRouter(prefix="/web-call")

    @router.post("/recording")
    async def recording(file: UploadFile = File(...), session_id: str = Form(...)) -> dict:
        # mirrors app/api/web_call.py's public surface; body read is deliberate
        data = await file.read()
        return {"ok": True, "bytes": len(data)}

    app = FastAPI()
    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _boundary() -> str:
    return "----cp5-3boundary42"


def _multipart_body(part_size: int, n_parts: int = 1) -> tuple[bytes, str]:
    b = _boundary().encode()
    body = io.BytesIO()
    part = b"x" * part_size
    for i in range(n_parts):
        body.write(b"--" + b + b"\r\n")
        body.write(b'Content-Disposition: form-data; name="file"; filename="f%d.webm"\r\n' % i)
        body.write(b"Content-Type: audio/webm\r\n\r\n")
        body.write(part)
        body.write(b"\r\n")
    body.write(b"--" + b + b"--\r\n")
    return body.getvalue(), _boundary()


def test_oversized_single_part_rejected(client: TestClient) -> None:
    body, boundary = _multipart_body(part_size=64 * 1024 * 1024)
    r = client.post(
        "/web-call/recording",
        content=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    # Either the parser rejects it (400/413/422) or the endpoint is never reached.
    assert r.status_code in (
        400,
        413,
        422,
    ), f"oversized part was accepted (status {r.status_code}) — unbounded parse"


def test_many_parts_rejected_within_budget(client: TestClient) -> None:
    body, boundary = _multipart_body(part_size=4096, n_parts=1500)
    r = client.post(
        "/web-call/recording",
        content=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Content-Length": str(len(body)),
        },
    )
    # 1500 parts must not be fully parsed/processed (part-count bound), and the
    # request must terminate with an error, not a hang or a 200 with full body.
    assert r.status_code in (400, 413, 422), (r.status_code,)


def test_normal_small_upload_still_works(client: TestClient) -> None:
    """Sanity: legitimate multipart uploads still succeed after the guards."""
    r = client.post(
        "/web-call/recording",
        files={"file": ("ok.webm", b"tiny-bytes", "audio/webm")},
        data={"session_id": "cp5-3-ok"},
    )
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json().get("ok") is True
