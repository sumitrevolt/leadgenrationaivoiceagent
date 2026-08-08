"""CP5-3 regression: static-file path handling must not leak files.

Guards the reachable UNC-path SSRF surface (GHSA-wqp7-x3pw-xc5r, fixed in
starlette 1.1.0) plus classic directory traversal. The tests mirror the app's
real mount pattern (``StaticFiles(directory=...)`` over the frontend dirs) so a
future Starlette downgrade / mount change that re-opens the hole fails here.

All assertions allow any non-2xx outcome: the invariant is "no file leaks",
not a specific status code (Starlette versions differ in 400 vs 404 vs 403).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.routing import Mount
from starlette.staticfiles import StaticFiles
from starlette.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
DESIGN_SYSTEM = REPO / "frontend" / "design-system"
WEBSITE = REPO / "frontend" / "website"


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = Starlette(
        routes=[
            Mount("/design-system", StaticFiles(directory=str(DESIGN_SYSTEM))),
            Mount("/site", StaticFiles(directory=str(WEBSITE), html=True)),
        ]
    )
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def test_legit_asset_still_serves(client: TestClient) -> None:
    """Sanity: the mount serves a real asset (guards against a broken test)."""
    if DESIGN_SYSTEM.joinpath("vendor").is_dir():
        probe = "/design-system/vendor/README.md"
        r = client.get(probe)
        assert r.status_code == 200, (probe, r.status_code)


def test_encoded_traversal_does_not_leak(client: TestClient) -> None:
    for path in (
        "/design-system/%2e%2e/%2e%2e/app/main.py",
        "/design-system/%2e%2e/app/main.py",
        "/design-system/..%2f..%2f.env",
        "/site/%2e%2e/%2e%2e/app/main.py",
        "/site/%2e%2e/.env",
    ):
        r = client.get(path)
        assert r.status_code >= 400, (path, r.status_code)
        body = r.content
        assert b"SQLALCHEMY" not in body and b"SECRET_KEY" not in body, path


def test_windows_style_paths_rejected(client: TestClient) -> None:
    """Backslash / UNC-style input (GHSA-wqp7-x3pw-xc5r class) must not leak."""
    for path in (
        r"/design-system/..\..\app\main.py",
        r"/design-system/\\server\share\secrets.txt",
        r"/site/..\..\app\main.py",
    ):
        r = client.get(path)
        assert r.status_code >= 400, (path, r.status_code)
        body = r.content
        assert b"SQLALCHEMY" not in body and b"SECRET_KEY" not in body, path


def test_double_encoded_traversal_does_not_leak(client: TestClient) -> None:
    for path in (
        "/design-system/%252e%252e/%252e%252e/app/main.py",
        "/site/%252e%252e/%252e%252e/app/main.py",
    ):
        r = client.get(path)
        assert r.status_code >= 400, (path, r.status_code)
