"""Hot Queue SLA / idle-reason visibility — GTM operator truth (no outbound)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


def test_inquiry_sla_breach_and_owner_action(tmp_path, monkeypatch):
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    old = (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat()
    row = {
        "channel": "inquiry",
        "from": "9876543210",
        "phone": "9876543210",
        "business_name": "Estique Test",
        "intent": "interested",
        "draft": "Namaste",
        "at": old,
        "hq_source": "website_inquiry",
    }
    f.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})
    q = ra.hot_queue()
    assert len(q) == 1
    assert q[0]["sla_state"] == "breach"
    assert q[0]["owner_action"] == "call_or_wa_draft_then_done"
    assert q[0]["age_minutes"] >= 12
    summary = ra.hot_queue_summary(q, scope="boss")
    assert summary["sla_breach_count"] == 1
    assert summary["inquiry_count"] == 1
    assert summary["idle_reason"] is None
    assert "SLA" in (summary["next_owner_hint"] or "")


def test_empty_queue_idle_reason():
    from app.platform import reply_agent as ra

    s = ra.hot_queue_summary([], scope="boss")
    assert s["idle_reason"] == "queue_empty_no_hot_drafts"
    assert s["count"] == 0
    assert s["next_owner_hint"]


def test_hot_queue_api_includes_summary(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from app.api.auth_deps import require_admin
    from app.main import app
    from app.platform import reply_agent as ra

    f = tmp_path / "reply_drafts.jsonl"
    f.write_text("", encoding="utf-8")
    monkeypatch.setattr(ra, "_DRAFTS_FILE", str(f))
    monkeypatch.setattr(ra, "_full_prospect_map", lambda: {})

    async def _admin():
        return {"role": "admin", "sub": "t"}

    app.dependency_overrides[require_admin] = _admin
    try:
        client = TestClient(app)
        r = client.get("/api/growth/reply/hot-queue?limit=20&scope=boss")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert "summary" in body
        assert body["summary"]["idle_reason"] == "queue_empty_no_hot_drafts"
    finally:
        app.dependency_overrides.pop(require_admin, None)
