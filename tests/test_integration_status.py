"""Integration expiry/health honesty — classifier + admin/customer API tests.

Scenarios 1-12: pure classifier (healthy / expiring_soon / expired / revoked /
unauthorized / transient_failure / unreachable / never_configured / unknown +
precedence). 13-20: API auth, tenant isolation, redaction, failure isolation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app.platform import integration_status as ist

NOW = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Pure classifier
# ---------------------------------------------------------------------------
def test_1_recent_success_is_healthy():
    r = ist.classify({"configured": True, "last_success": NOW - timedelta(hours=1)}, now=NOW)
    assert r["status"] == "healthy" and not r["reconnect_required"]


def test_2_expiry_within_threshold_is_expiring_soon():
    r = ist.classify(
        {"configured": True, "expires_at": NOW + timedelta(days=3)}, now=NOW, threshold_days=7
    )
    assert r["status"] == "expiring_soon" and r["reconnect_required"]


def test_3_expiry_in_past_is_expired():
    r = ist.classify({"configured": True, "expires_at": NOW - timedelta(days=1)}, now=NOW)
    assert r["status"] == "expired" and r["reconnect_required"]


def test_4_explicit_revocation_is_revoked():
    r = ist.classify({"configured": True, "revoked": True}, now=NOW)
    assert r["status"] == "revoked" and r["reconnect_required"]


def test_5_auth_failure_is_unauthorized():
    r = ist.classify({"configured": True, "auth_failure": True}, now=NOW)
    assert r["status"] == "unauthorized" and r["reconnect_required"]


def test_6_retryable_failure_is_transient():
    r = ist.classify({"configured": True, "transient_failure": True}, now=NOW)
    assert r["status"] == "transient_failure" and r["retry_eligible"]


def test_7_timeout_is_unreachable():
    r = ist.classify({"configured": True, "unreachable": True}, now=NOW)
    assert r["status"] == "unreachable" and r["retry_eligible"]


def test_8_no_config_is_never_configured():
    r = ist.classify({"configured": False}, now=NOW)
    assert r["status"] == "never_configured"


def test_9_configured_without_evidence_is_unknown():
    # env-presence style: configured but no expiry and no success -> unknown, NOT healthy
    r = ist.classify({"configured": True}, now=NOW)
    assert r["status"] == "unknown"


def test_10_expired_overrides_recent_success():
    r = ist.classify(
        {"configured": True, "expires_at": NOW - timedelta(minutes=1), "last_success": NOW}, now=NOW
    )
    assert r["status"] == "expired"


def test_11_revoked_overrides_success_and_valid_token():
    r = ist.classify(
        {
            "configured": True,
            "revoked": True,
            "expires_at": NOW + timedelta(days=30),
            "last_success": NOW,
        },
        now=NOW,
    )
    assert r["status"] == "revoked"


def test_12_valid_future_token_is_healthy():
    r = ist.classify({"configured": True, "expires_at": NOW + timedelta(days=30)}, now=NOW)
    assert r["status"] == "healthy"


# ---------------------------------------------------------------------------
# API — admin + customer
# ---------------------------------------------------------------------------
def _mint(client_id: str, role: str = "customer") -> str:
    from jose import jwt

    from app.config import settings

    payload = {
        "sub": client_id,
        "role": role,
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


_DIRECTORY = {
    "cliA": [{"platform": "facebook", "expires_at": "2099-01-01T00:00:00+00:00", "deleted": False}],
    "cliB": [{"platform": "linkedin", "expires_at": "2000-01-01T00:00:00+00:00", "deleted": False}],
}


@pytest.fixture(autouse=True)
def _fake_vault(monkeypatch):
    def fake_list_accounts(cid):
        return list(_DIRECTORY.get(cid, []))

    monkeypatch.setattr("app.social_engine.vault.list_accounts", fake_list_accounts)
    monkeypatch.setattr(
        "app.platform.integration_status._bounded_client_ids", lambda limit=200: list(_DIRECTORY)
    )


def test_13_customer_unauthenticated_denied(client):
    r = client.get("/api/customer/integrations/health")
    assert r.status_code in (401, 403)


def test_14_customer_sees_only_own_tenant(client):
    ra = client.get(
        "/api/customer/integrations/health", headers={"Authorization": f"Bearer {_mint('cliA')}"}
    )
    assert ra.status_code == 200
    a = ra.json()["integrations"]
    assert len(a) == 1 and a[0]["integration"] == "Facebook" and a[0]["status"] == "healthy"

    rb = client.get(
        "/api/customer/integrations/health", headers={"Authorization": f"Bearer {_mint('cliB')}"}
    )
    b = rb.json()["integrations"]
    assert len(b) == 1 and b[0]["integration"] == "LinkedIn"
    assert b[0]["status"] == "expired" and b[0]["action_required"] is True
    # customer B never sees cliA's data
    assert "Facebook" not in json.dumps(b)


def test_15_customer_response_is_redacted(client):
    r = client.get(
        "/api/customer/integrations/health", headers={"Authorization": f"Bearer {_mint('cliA')}"}
    )
    blob = json.dumps(r.json())
    for forbidden in (
        "client_id",
        "cliA",
        "tok",
        "access_token",
        "expires_at",
        "reference_id",
        "correlation",
    ):
        assert forbidden not in blob, f"customer response leaked {forbidden!r}"


def test_16_admin_returns_sanitized_diagnostics(client):
    # require_admin is overridden to a mock admin in conftest -> 200
    r = client.get("/api/admin/integrations/health", params={"client_id": "cliB"})
    assert r.status_code == 200
    items = r.json()["integrations"]
    assert items and items[0]["status"] == "expired"
    it = items[0]
    assert it["client_id"] == "cliB" and it["reference_id"].startswith("int_")
    assert it["reconnect_required"] is True and it["failure_category"] == "expired"
    blob = json.dumps(r.json())
    for forbidden in ("tok", "access_token", "refresh_token", "secret", "Authorization", "Bearer"):
        assert forbidden not in blob, f"admin response leaked {forbidden!r}"


def test_17_one_provider_failure_does_not_break_response(client, monkeypatch):
    def boom(cid):
        raise RuntimeError("vault store unavailable")

    monkeypatch.setattr("app.social_engine.vault.list_accounts", boom)
    r = client.get(
        "/api/customer/integrations/health", headers={"Authorization": f"Bearer {_mint('cliA')}"}
    )
    assert r.status_code == 200  # degrades to empty, never 500
    assert r.json()["integrations"] == []


def test_18_no_secret_key_names_in_admin_serialization(client):
    r = client.get("/api/admin/integrations/health", params={"client_id": "cliA"})
    keys = set()
    for it in r.json()["integrations"]:
        keys |= set(it.keys())
    assert keys.isdisjoint(
        {"token", "tok", "access_token", "refresh_token", "api_key", "secret", "signature"}
    )
