"""L2 Stack graph iframe fix (2026-07-15, Priority 2 of the ADR-104 follow-up session).

Root cause: SecurityHeadersMiddleware sets `X-Frame-Options: DENY` (correct default
for every admin page) on every response including /app/control-center/graph, the
page control_center.html itself embeds via <iframe src="/app/control-center/graph">.
A browser silently refuses to render an iframe whose own response says
"do not frame me" -- no console error, no network failure, just a blank canvas
with the browser's generic broken-frame icon. That is exactly what was observed
live on production this session.

Fix: a new `_SAME_ORIGIN_EMBEDDABLE_PREFIXES` tier in SecurityHeadersMiddleware
(alongside the pre-existing fully-public `_EMBEDDABLE_PREFIXES` for the client
lead-widget/reviews-widget) that sets `X-Frame-Options: SAMEORIGIN` and
`frame-ancestors 'self'` -- narrower than the public-embeddable tier (which uses
`frame-ancestors *`), since this route must only ever be framed by our own
authenticated admin UI, never an external site.
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_graph_route_is_same_origin_frameable(client):
    r = client.get("/app/control-center/graph")
    assert r.status_code == 200
    assert r.headers.get("x-frame-options") == "SAMEORIGIN"
    csp = r.headers.get("content-security-policy", "")
    assert "frame-ancestors 'self'" in csp
    # Must NOT be wide-open like the public client-widget tier.
    assert "frame-ancestors *" not in csp


def test_graph_route_is_real_html_not_a_stub(client):
    r = client.get("/app/control-center/graph")
    assert r.status_code == 200
    assert "text/html" in r.headers.get("content-type", "")
    body = r.text
    # The three view tabs + Sigma/Graphology/ELK vendored script tags must be present.
    assert "Structural" in body and "Automation" in body and "Products" in body
    assert "sigma.min.js" in body
    assert "graphology.umd.min.js" in body
    assert "elk.bundled.js" in body
    # Error/loading UI must exist (never a silent blank canvas).
    assert 'id="error-banner"' in body
    assert 'id="loading"' in body


def test_other_admin_pages_still_deny_framing(client):
    """The fix must be scoped to this one route -- every other admin page keeps
    the blanket DENY default (regression guard against over-widening)."""
    r = client.get("/app/control-center")
    assert r.status_code == 200
    assert r.headers.get("x-frame-options") == "DENY"
    csp = r.headers.get("content-security-policy", "")
    assert "frame-ancestors" not in csp


def test_public_client_widget_tier_is_unaffected():
    """The pre-existing fully-public embeddable tier (client websites framing
    the lead/reviews widget) must keep frame-ancestors '*', not the new
    same-origin-only 'self' -- the two tiers must stay distinct."""
    from app.middleware import SecurityHeadersMiddleware as M

    assert M._is_embeddable("/api/engage/reviews-widget/abc") is True
    assert M._is_embeddable("/b/some-slug/embed") is True
    assert M._is_same_origin_embeddable("/api/engage/reviews-widget/abc") is False


def test_same_origin_embeddable_helper_scoped_to_graph_path():
    from app.middleware import SecurityHeadersMiddleware as M

    assert M._is_same_origin_embeddable("/app/control-center/graph") is True
    assert M._is_same_origin_embeddable("/app/control-center") is False
    assert M._is_same_origin_embeddable("/app/office") is False
    assert M._is_embeddable("/app/control-center/graph") is False
