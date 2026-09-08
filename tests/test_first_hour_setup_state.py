"""Loop 9 (2026-07-10): brand-new customer first-hour empty-state anti-churn.

`/api/customer/auth/me` now returns `first_hour_setup: {active, minutes_elapsed,
minutes_remaining, message}` so the dashboard FE can render "🚀 AI setup ho rahi
hai — X min me pehla content" instead of showing empty zeros to a customer who
signed up 5 minutes ago and is waiting on the auto_onboard job.

RED-first: field wasn't in the response before this loop.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def test_me_first_hour_setup_active_for_fresh_customer(monkeypatch):
    """Signed up 5 min ago + no content → active=True with a helpful message."""
    # Zero content queued.
    import app.marketing.auto_content as ac
    from app.api.customer_auth import _first_hour_setup_state

    monkeypatch.setattr(ac, "list_queue", lambda cid, limit=1: [])

    rec = {"id": "c_new", "created_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=5))}
    state = _first_hour_setup_state(rec)
    assert state["active"] is True
    assert state["minutes_elapsed"] == 5
    assert 20 <= state["minutes_remaining"] <= 30
    assert "setup" in state["message"].lower()


def test_me_first_hour_setup_inactive_after_60_minutes(monkeypatch):
    """Signed up 65 min ago → active=False (window closed regardless of content)."""
    import app.marketing.auto_content as ac
    from app.api.customer_auth import _first_hour_setup_state

    monkeypatch.setattr(ac, "list_queue", lambda cid, limit=1: [])

    rec = {"id": "c_old", "created_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=65))}
    state = _first_hour_setup_state(rec)
    assert state["active"] is False


def test_me_first_hour_setup_inactive_when_content_ready(monkeypatch):
    """Fresh customer BUT auto_onboard already produced content → no banner
    (customer sees real content, not the setup message)."""
    import app.marketing.auto_content as ac
    from app.api.customer_auth import _first_hour_setup_state

    monkeypatch.setattr(ac, "list_queue", lambda cid, limit=1: [{"id": "post1"}])

    rec = {"id": "c_ready", "created_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=10))}
    state = _first_hour_setup_state(rec)
    assert state["active"] is False, (
        "content already exists — customer doesn't need the setup banner"
    )


def test_me_first_hour_setup_defensive_on_missing_created_at(monkeypatch):
    """Legacy client without created_at → safe inactive default, no exception."""
    from app.api.customer_auth import _first_hour_setup_state

    state = _first_hour_setup_state({"id": "c_legacy"})
    assert state["active"] is False
    assert state["minutes_elapsed"] == 0


def test_me_first_hour_setup_defensive_on_none(monkeypatch):
    """None client rec (unknown cid) → safe inactive default."""
    from app.api.customer_auth import _first_hour_setup_state

    state = _first_hour_setup_state(None)
    assert state["active"] is False


def test_me_endpoint_includes_first_hour_setup_field(client, monkeypatch):
    """The /me response contract MUST include first_hour_setup so FE can branch."""
    import app.api.customer_auth as ca
    from app.api.customer_auth import require_customer

    # Override auth to a known cid.
    from app.main import app

    app.dependency_overrides[require_customer] = lambda: "c_me"

    import app.marketing.clients_store as cs

    monkeypatch.setattr(
        cs,
        "get_client",
        lambda cid: {
            "id": cid,
            "business_name": "Me Biz",
            "product": "marketing",
            "created_at": _iso(datetime.now(timezone.utc) - timedelta(minutes=3)),
        },
    )
    import app.marketing.auto_content as ac

    monkeypatch.setattr(ac, "list_queue", lambda cid, limit=1: [])

    try:
        r = client.get("/api/customer/auth/me")
        assert r.status_code == 200
        d = r.json()
        assert "first_hour_setup" in d, f"missing first_hour_setup: keys={list(d.keys())}"
        fhs = d["first_hour_setup"]
        assert fhs.get("active") is True
        assert fhs.get("minutes_elapsed") == 3
        assert fhs.get("message")
    finally:
        app.dependency_overrides.pop(require_customer, None)
