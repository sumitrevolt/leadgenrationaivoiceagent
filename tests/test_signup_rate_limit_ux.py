"""Loop 6 (2026-07-10): signup 429 UX clarity.

Bare `"Thoda ruk ke dobara try karo"` gave FE no retry_after and no reason. The
countdown-friendly RFC 7231 `Retry-After` header + structured detail lets
pricing.html show "X seconds me phir try" instead of a generic error.

RED-first: fails against pre-fix code (detail is a plain string, no header),
passes after (structured detail + Retry-After header).
"""

from __future__ import annotations

import pytest


def _burn_the_bucket(client, tries: int = 12):
    """Post enough signups to trip the inline per-IP bucket (5/min)."""
    responses = []
    for i in range(tries):
        r = client.post(
            "/api/public/signup",
            json={
                "business_name": f"Rate Biz {i}",
                "email": f"rate{i}@example.com",
                "password": "secret123",
                "plan": "starter",
            },
        )
        responses.append(r)
        if r.status_code == 429:
            return r
    return responses[-1]


def test_signup_429_carries_retry_after_header(client, monkeypatch):
    """RFC 7231 §7.1.3 — 429 MUST carry a Retry-After header so FE / browsers
    can show a countdown or auto-retry after the window."""
    # Stub the heavy side-effects so we hit rate-limit before any DB / KB code.
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs

    monkeypatch.setattr(cs, "add_client", lambda **k: {"id": "c", "business_name": ""})
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: None)

    # Clear the module-level bucket so this test is deterministic.
    import app.api.public_site as ps
    ps._RL.clear()

    r = _burn_the_bucket(client)
    assert r.status_code == 429, f"expected 429 after burning bucket, got {r.status_code}"
    assert r.headers.get("Retry-After"), "Retry-After header MUST be set on 429"
    ra = int(r.headers["Retry-After"])
    assert 1 <= ra <= 600, f"Retry-After should be a small positive number of seconds, got {ra}"


def test_signup_429_detail_is_structured_with_reason(client, monkeypatch):
    """Detail MUST be a dict with `error`, `message`, `retry_after`, `scope` so FE
    can branch (`error == "rate_limited"` vs other 4xx) and render a countdown."""
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs
    import app.api.public_site as ps

    monkeypatch.setattr(cs, "add_client", lambda **k: {"id": "c", "business_name": ""})
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: None)
    ps._RL.clear()

    r = _burn_the_bucket(client)
    assert r.status_code == 429
    body = r.json()
    detail = body.get("detail") or {}
    assert isinstance(detail, dict), f"detail must be a dict for structured UX, got {type(detail).__name__}"
    assert detail.get("error") == "rate_limited"
    assert detail.get("scope") == "signup_ip"
    assert detail.get("retry_after"), "retry_after must be present so FE shows a countdown"
    assert isinstance(detail.get("retry_after"), int)
    assert "message" in detail, "human-readable Hinglish string still required for direct display"


def test_signup_429_emits_admin_automation_log(client, monkeypatch):
    """Loop 7: 429 MUST emit a signup_rate_limited AutomationLog row so admin
    Delivery Command Center sees abuse spikes without grepping app logs."""
    import app.api.customer_auth as ca
    import app.marketing.clients_store as cs
    import app.api.public_site as ps
    import app.platform.automation_log_service as als

    monkeypatch.setattr(cs, "add_client", lambda **k: {"id": "c", "business_name": ""})
    monkeypatch.setattr(ca, "login_exists", lambda e: False)
    monkeypatch.setattr(ca, "client_has_login", lambda c: False)
    monkeypatch.setattr(ca, "register_login", lambda *a, **k: None)
    ps._RL.clear()

    captured: list[dict] = []
    monkeypatch.setattr(als, "log_event", lambda **kw: (captured.append(kw), "id")[1])

    r = _burn_the_bucket(client)
    assert r.status_code == 429

    rows = [c for c in captured if c.get("job_type") == "signup_rate_limited"]
    assert len(rows) >= 1, f"expected at least 1 rate_limited row, got {len(rows)}: {captured}"
    row = rows[0]
    assert row.get("status") == "failed"
    assert row.get("triggered_by") == "signup"
    meta = row.get("meta_json") or {}
    assert "ip" in meta
    assert meta.get("scope") == "signup_ip"
