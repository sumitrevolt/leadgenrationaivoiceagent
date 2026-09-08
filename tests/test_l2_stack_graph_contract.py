"""L2 Stack graph contract — expose blank/broken embed regressions.

Root causes covered:
1. X-Frame-Options DENY on /app/control-center/graph (ADR-104) — covered in
   test_l2_stack_graph_frame_headers.py; re-asserted here for HEAD+GET parity.
2. Silent parent blank when iframe fails — parent must keep Old Explorer link
   and listen for cc-graph-ready / cc-graph-error postMessage.
3. Dataset must be real curated architecture (not empty placeholder).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
GRAPH_HTML = REPO / "frontend" / "control_center_graph.html"
CC_HTML = REPO / "frontend" / "control_center.html"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def test_graph_head_and_get_both_frameable(client):
    """HEAD used to 404 while GET worked — breaks probes and confuses triage."""
    g = client.get("/app/control-center/graph")
    h = client.head("/app/control-center/graph")
    assert g.status_code == 200
    assert h.status_code == 200, f"HEAD must not 404, got {h.status_code}"
    assert h.headers.get("x-frame-options") == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in h.headers.get("content-security-policy", "")


def test_graph_html_has_real_structural_dataset():
    body = GRAPH_HTML.read_text(encoding="utf-8")
    # Structural view must declare a non-trivial curated map (not empty stub).
    assert "structural:" in body
    assert "nodes:" in body and "edges:" in body
    # Count node id declarations inside structural view (rough lower bound).
    # Real map ships ~40+ architecture nodes (live smoke saw 46).
    node_ids = re.findall(r"\{id:'([a-z0-9_]+)'", body)
    assert len(node_ids) >= 40, f"expected real architecture nodes, got {len(node_ids)}"
    for required in ("fastapi", "celery", "caddy", "billing", "voice_brain"):
        assert required in node_ids


def test_graph_posts_ready_or_error_to_parent():
    body = GRAPH_HTML.read_text(encoding="utf-8")
    assert "cc-graph-ready" in body
    assert "cc-graph-error" in body
    assert "notifyReady" in body


def test_control_center_preserves_old_explorer_and_truthful_embed_issue():
    body = CC_HTML.read_text(encoding="utf-8")
    assert 'href="/app/explorer"' in body
    assert "tab=plugins" in body
    assert "node=plugin_registry" in body
    assert "Old explorer" in body or "Old Explorer" in body
    assert 'src="/app/control-center/graph"' in body
    assert "cc-graph-ready" in body
    assert "cc-graph-error" in body
    assert "cc-graph-issue" in body
    assert "showL2EmbedIssue" in body


def test_duplicate_control_center_graph_routes_absent():
    """FastAPI first-route-wins — single path registration (GET+HEAD ok)."""
    from app.main import app

    graph_routes = [
        r for r in app.routes if getattr(r, "path", None) == "/app/control-center/graph"
    ]
    assert len(graph_routes) == 1, f"duplicate graph path entries: {graph_routes}"
    methods = set(getattr(graph_routes[0], "methods", []) or [])
    assert "GET" in methods and "HEAD" in methods, methods
