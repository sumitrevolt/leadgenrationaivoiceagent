"""Customer AI Marketing Studio API tests — routes mounted, auth-gated, never-empty.

free_ai.chat is stubbed by conftest (canned reply), so generators exercise the
LLM-or-template path without real network. Every tool must return 200 + a
non-trivial result for an authed customer, and 401/403 without a token.
"""

from fastapi.testclient import TestClient

from app.api.admin import create_access_token
from app.main import app

_TOK = create_access_token("studio-test-client", "studio@test.com", "customer")
_H = {"Authorization": f"Bearer {_TOK}", "Content-Type": "application/json"}

_POST_TOOLS = [
    ("/api/customer/studio/post", {"occasion": "Diwali", "offer": "20% off"}),
    ("/api/customer/studio/calendar", {"days": 7}),
    ("/api/customer/studio/whatsapp", {"occasion": "Weekend sale"}),
    ("/api/customer/studio/review-reply", {"review_text": "Bahut accha service, fast!", "rating": 5}),
    ("/api/customer/studio/gbp-text", {"services": ["Repair", "Installation"]}),
    ("/api/customer/studio/ads", {"offer": "Free demo"}),
    ("/api/customer/studio/hashtags", {"count": 15}),
    # batch 2 — MVP-12
    ("/api/customer/studio/festival-post", {"days": 45}),
    ("/api/customer/studio/poster", {"offer": "20% off", "phone": "+919999999999"}),
    ("/api/customer/studio/review-request", {}),
    ("/api/customer/studio/followup-sequence", {"lead_type": "new_inquiry"}),
    ("/api/customer/studio/speed-followup", {}),
    ("/api/customer/studio/reel-script", {"topic": "offer", "n": 2}),
    ("/api/customer/studio/win-back", {"offer": "10% wapas"}),
    ("/api/customer/studio/quote-draft", {"avg_deal_value": 20000}),
]


def test_studio_routes_mounted():
    paths = {getattr(r, "path", "") for r in app.routes}
    for p in [
        "/api/customer/studio/tools",
        "/api/customer/studio/post",
        "/api/customer/studio/calendar",
        "/api/customer/studio/whatsapp",
        "/api/customer/studio/review-reply",
        "/api/customer/studio/gbp-text",
        "/api/customer/studio/ads",
        "/api/customer/studio/hashtags",
        "/api/customer/studio/gbp-tips",
    ]:
        assert p in paths, f"missing route {p}"


def test_studio_requires_auth():
    c = TestClient(app)
    assert c.get("/api/customer/studio/tools").status_code in (401, 403)
    assert c.post("/api/customer/studio/post", json={}).status_code in (401, 403)
    assert c.get("/api/customer/studio/gbp-tips").status_code in (401, 403)


def test_studio_tools_list():
    c = TestClient(app)
    r = c.get("/api/customer/studio/tools", headers=_H)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and d["count"] == 17
    assert {t["key"] for t in d["tools"]} >= {
        "post", "ads", "review-reply", "hashtags", "festival-post", "poster",
        "review-request", "followup-sequence", "speed-followup", "reel-script",
        "win-back", "quote-draft", "next-best-action",
    }
    assert "niche" in d["context"]


def test_studio_next_best_action():
    c = TestClient(app)
    r = c.get("/api/customer/studio/next-best-action", headers=_H)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and isinstance(d["actions"], list) and len(d["actions"]) >= 1
    assert "action" in d["actions"][0]


def test_studio_poster_returns_svg():
    c = TestClient(app)
    r = c.post("/api/customer/studio/poster", headers=_H, json={"offer": "Sale"})
    assert r.status_code == 200
    svg = r.json().get("result", {}).get("svg", "")
    assert svg.strip().startswith("<svg") or "<svg" in svg


def test_studio_gbp_tips_no_llm():
    c = TestClient(app)
    r = c.get("/api/customer/studio/gbp-tips", headers=_H)
    assert r.status_code == 200
    d = r.json()
    assert d["ok"] is True and isinstance(d["tips"], list) and len(d["tips"]) > 0


def test_studio_post_tools_never_empty():
    c = TestClient(app)
    for path, body in _POST_TOOLS:
        r = c.post(path, headers=_H, json=body)
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        d = r.json()
        assert d.get("ok") is True, f"{path} not ok"
        # each tool returns either a 'result' dict or a list (calendar) — non-empty
        payload = d.get("result") or d.get("items")
        assert payload, f"{path} returned empty payload"


def test_studio_review_reply_requires_text():
    c = TestClient(app)
    # missing required review_text -> 422 validation
    r = c.post("/api/customer/studio/review-reply", headers=_H, json={"rating": 5})
    assert r.status_code == 422


def test_studio_client_scoped_context():
    """business_name/niche come from the client record, NOT the request body."""
    c = TestClient(app)
    r = c.post("/api/customer/studio/post", headers=_H, json={"occasion": "x"})
    assert r.status_code == 200
    ctx = r.json().get("context", {})
    assert "niche" in ctx and "business_name" in ctx
