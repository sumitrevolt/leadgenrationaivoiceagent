"""Unity WebGL Brotli static-serving headers (Phase-1 UAT lock).

Unity build uses decompressionFallback=false → the browser MUST receive
`Content-Encoding: br` on the `.br` artifacts, otherwise the loader receives raw
brotli bytes and the office fails to load with a corrupt/compression error. Plain
StaticFiles omits this header; app.main serves /static/office-unity via a
precompressed-aware handler that also fixes the Content-Type for wasm/js/data.

Skips when the build isn't deployed (frontend/office_unity/Build absent) so CI
without a Unity build stays green.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "frontend" / "office_unity" / "Build"
BASE = "/static/office-unity/Build"

pytestmark = pytest.mark.skipif(not BUILD.is_dir(), reason="Unity build not deployed")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_loader_is_plain_javascript(client):
    r = client.get(f"{BASE}/LeadGenVirtualOffice.loader.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "").lower()
    # The loader itself is NOT brotli-compressed — must not carry Content-Encoding: br.
    assert r.headers.get("content-encoding") != "br"


@pytest.mark.parametrize(
    "fname,ctype_needle",
    [
        ("LeadGenVirtualOffice.data.br", "octet-stream"),
        ("LeadGenVirtualOffice.framework.js.br", "javascript"),
        ("LeadGenVirtualOffice.wasm.br", "wasm"),
    ],
)
def test_br_artifacts_have_brotli_content_encoding(client, fname, ctype_needle):
    r = client.get(f"{BASE}/{fname}")
    assert r.status_code == 200, f"{fname} -> HTTP {r.status_code}"
    assert r.headers.get("content-encoding") == "br", (
        f"{fname} missing 'Content-Encoding: br' — Unity decompressionFallback=false "
        f"requires it or the browser cannot decode the artifact"
    )
    assert ctype_needle in r.headers.get("content-type", "").lower(), (
        f"{fname} wrong Content-Type={r.headers.get('content-type')!r}"
    )


def test_br_sets_vary_accept_encoding(client):
    r = client.get(f"{BASE}/LeadGenVirtualOffice.wasm.br")
    assert "accept-encoding" in r.headers.get("vary", "").lower()


def test_missing_artifact_is_404(client):
    r = client.get(f"{BASE}/DoesNotExist.br")
    assert r.status_code == 404


# NOTE: admin-only enforcement of the office snapshot (/api/platform/office/snapshot,
# Depends(require_admin)) is intentionally NOT asserted here — tests/conftest.py overrides
# require_admin with a mock admin, so this harness cannot observe the real 401/403. Real
# enforcement is fail-closed in app/api/auth_deps.py:require_admin and is covered by the
# dedicated authenticated auth/tenant-isolation suites.
