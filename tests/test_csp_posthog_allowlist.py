"""CSP PostHog allowlist (2026-08-02, ISSUE-02).

Evidence: POSTHOG_API_KEY is set in prod, but SecurityHeadersMiddleware's CSP
blocked the PostHog loader script + events beacon on admin/customer/voice/
automation pages, so product analytics was dead. Fix: allow PostHog infra hosts
in script-src + connect-src only — no generic wildcards, nothing else weakened.
"""

from __future__ import annotations

import pytest

# PostHog infra hosts (script loader + events beacon). Must stay in BOTH
# script-src (loader) and connect-src (capture/beacon) of every app response.
POSTHOG_ALLOWED = ("https://*.i.posthog.com", "https://us-assets.i.posthog.com")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_admin_page_csp_allows_posthog_script_and_connect(client):
    r = client.get("/app/automation")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    # script-src directive must contain both PostHog hosts.
    script_src = _directive(csp, "script-src")
    for host in POSTHOG_ALLOWED:
        assert host in script_src
    # connect-src directive must allow the PostHog beacon host.
    connect_src = _directive(csp, "connect-src")
    assert "https://*.i.posthog.com" in connect_src
    # Other directives unchanged — no PostHog in default/style/font/img.
    for directive in ("default-src", "style-src", "font-src", "img-src"):
        assert not any(h in _directive(csp, directive) for h in POSTHOG_ALLOWED)


def test_customer_page_csp_allows_posthog_too(client):
    r = client.get("/app/customer")
    assert r.status_code == 200
    csp = r.headers.get("content-security-policy", "")
    for host in POSTHOG_ALLOWED:
        assert host in _directive(csp, "script-src")
    assert "https://*.i.posthog.com" in _directive(csp, "connect-src")


def test_posthog_does_not_leak_into_public_widget_csp(client):
    """The public client-widget tier keeps its tight CSP — PostHog is internal-only.

    NOTE: an unknown slug 302-redirects to "/", so check the embed response
    itself (follow_redirects=False) — that is the header the client's iframe
    actually receives.
    """
    r = client.get("/b/some-slug/embed", follow_redirects=False)
    assert r.status_code == 302  # unknown slug -> redirect (route is real)
    csp = r.headers.get("content-security-policy", "")
    assert "frame-ancestors *" in csp
    assert not any(h in _directive(csp, "script-src") for h in POSTHOG_ALLOWED)
    assert not any(h in _directive(csp, "connect-src") for h in POSTHOG_ALLOWED)


def _directive(csp: str, name: str) -> str:
    for part in csp.split(";"):
        part = part.strip()
        if part.startswith(name):
            return part
    return ""
