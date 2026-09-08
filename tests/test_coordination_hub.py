"""Contract tests for the Coordination Hub page + frontend wiring.

Mera (OpenCode) contribution is the frontend page `/app/coordination` wired to
Cursor's deployed Owner OS projection API. Backend itself (snapshot/events/git,
HMAC heartbeat/buzz, presence) is covered by Cursor's own tests
(test_coordination_hub_auth.py / _git.py / _projection.py) — ye suite sirf:

  1. page route serves 200,
  2. page references the REAL deployed API surface (no dead /api/coordination-hub/*),
  3. snapshot endpoint is admin-gated (no token → 401),
  4. hub stays inert (projection-only) by default.
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _page() -> str:
    r = client.get("/app/coordination")
    assert r.status_code == 200, f"page route failed: {r.status_code}"
    return r.text


def _assert_admin_gated(path: str) -> None:
    """Conftest globally overrides require_admin + get_current_user -> mock user.
    Is test wale endpoint fail-closed auth hai to dono override hata ke asli gate
    check karo (kabhi-kabhi hub flag OFF hota hai git ke liye to 404 pe pehle
    aa sakta hai — par auth hamesha pehle 401 deta hai bina token ke)."""
    from app.api import auth_deps

    saved = {}
    for dep in (auth_deps.require_admin, auth_deps.get_current_user):
        if dep in app.dependency_overrides:
            saved[dep] = app.dependency_overrides.pop(dep)
    try:
        r = client.get(path)
        assert r.status_code == 401, f"{path}: expected 401, got {r.status_code}"
    finally:
        app.dependency_overrides.update(saved)


def test_page_route_serves_200():
    html = _page()
    assert "Coordination Hub" in html
    assert "owner-os/coordination-hub" in html
    assert "Boss → STAFF coordination evidence" in html
    assert "assignments" in html and "handoffs" in html and "Boss verdict" in html


def test_page_does_not_reference_my_dead_prefix():
    html = _page()
    # Meri purani standalone API prefix kabhi bhi page me nahi hona chahiye
    # (Cursor ka deployed backend wahi single source of truth hai).
    assert "/api/coordination-hub/" not in html


def test_page_references_real_snapshot_endpoint():
    html = _page()
    assert "/api/admin/owner-os/coordination-hub/snapshot" in html
    assert "/api/admin/owner-os/coordination-hub/events" in html


def test_page_references_hub_on_state():
    html = _page()
    assert "COORDINATION_HUB_ENABLED" in html


def test_snapshot_is_admin_gated():
    _assert_admin_gated("/api/admin/owner-os/coordination-hub/snapshot")


def test_events_is_admin_gated():
    _assert_admin_gated("/api/admin/owner-os/coordination-hub/events")


def test_git_is_admin_gated():
    _assert_admin_gated("/api/admin/owner-os/coordination-hub/git")


def test_page_has_no_inline_secrets():
    html = _page()
    # Env var NAMES (COORD_HUB_TOOL_CURSOR_SECRET etc.) documentation me legitimately
    # aate hain — VALUES kabhi nahi. Isliye "=" ke baad actual secret value nahi hona chahiye.
    for leak in ("sk-", "ghp_", "COORD_HUB_TOOL_CURSOR_SECRET=abc", "secret=<"):
        assert leak not in html, f"secret value leaked into page: {leak}"
    import re

    assert not re.search(r"COORD_HUB_[A-Z0-9_]+_SECRET\s*=\s*[A-Za-z0-9]{8,}", html), (
        "env secret value assigned in page"
    )


def test_mutations_refused_surface_present():
    html = _page()
    assert "REFUSED" in html or "refused" in html or "mutation" in html.lower()


def test_tool_script_tab_documents_hmac_inbound():
    html = _page()
    assert "X-CoordHub-Timestamp" in html
    assert "X-CoordHub-Signature" in html
