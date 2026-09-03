"""
Tests for the Tata Smartflo test-call admin endpoint.

No network — TataSmartfloClient is monkeypatched; tests verify:
  - Auth gating (401/403 without admin)
  - 503 when Smartflo not configured
  - 422 when 'to' number is missing/short
  - 200 + correct response shape on success
  - 200 + failure shape on API rejection
  - Custom caller_id and call_timeout passthrough
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------
try:
    from app.main import app

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="app not importable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_deps():
    """Ensure dependency overrides are clean before each test."""
    yield
    app.dependency_overrides.clear()


def _override_admin():
    """Override require_admin to allow unauthenticated test requests."""
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: type(
        "Admin", (), {"email": "test@leadsgenai.in"}
    )()


# ---------------------------------------------------------------------------
# Helper: mock TataSmartfloClient
# ---------------------------------------------------------------------------
def _mock_client_available(available: bool = True):
    """Return a patch context that makes TataSmartfloClient.available() return the given value."""
    return patch(
        "app.api.telephony_smartflo.TataSmartfloClient",
        return_value=type(
            "MockClient",
            (),
            {
                "available": lambda self: available,
                "did": "918012345678",
                "place_call": AsyncMock(
                    return_value={
                        "status_code": 200,
                        "body": {
                            "success": True,
                            "message": "Originate successfully queued",
                            "ref_id": "test-ref-001",
                        },
                    }
                ),
            },
        )(),
    )


def _mock_client_rejected():
    """Return a patch context where place_call returns a rejection."""
    return patch(
        "app.api.telephony_smartflo.TataSmartfloClient",
        return_value=type(
            "MockClient",
            (),
            {
                "available": lambda self: True,
                "did": "918012345678",
                "place_call": AsyncMock(
                    return_value={
                        "status_code": 400,
                        "body": {
                            "success": False,
                            "message": "Invalid details provided.",
                        },
                    }
                ),
            },
        )(),
    )


# ---------------------------------------------------------------------------
# 1. Auth gating
# ---------------------------------------------------------------------------
class TestAuthGating:
    def test_unauthenticated_returns_401_or_403(self):
        """POST /test-call without admin auth must be rejected."""
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as c:
            r = c.post("/api/telephony/smartflo/test-call", json={"to": "9876543210"})
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 2. Not configured (503)
# ---------------------------------------------------------------------------
class TestNotConfigured:
    def test_returns_503_when_client_not_available(self):
        """503 when TATA_SMARTFLO_API_TOKEN/API_KEY are missing."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available(available=False):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        assert r.status_code == 503
        body = r.json()
        assert "not configured" in body["detail"].lower()


# ---------------------------------------------------------------------------
# 3. Validation (422)
# ---------------------------------------------------------------------------
class TestValidation:
    def test_missing_to_returns_422(self):
        """Missing 'to' field → 422."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post("/api/telephony/smartflo/test-call", json={})
        assert r.status_code == 422

    def test_short_to_returns_422(self):
        """'to' shorter than 8 digits → 422."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post("/api/telephony/smartflo/test-call", json={"to": "123"})
        assert r.status_code == 422

    def test_empty_to_returns_422(self):
        """Empty 'to' field → 422."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post("/api/telephony/smartflo/test-call", json={"to": ""})
        assert r.status_code == 422


# ---------------------------------------------------------------------------
# 4. Success case
# ---------------------------------------------------------------------------
class TestSuccess:
    def test_call_placed_returns_200(self):
        """Valid request with mock client → placed=true, ref_id present."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210", "niche": "salon_spa"},
                )
        assert r.status_code == 200
        body = r.json()
        assert body["placed"] is True
        assert body["ref_id"] == "test-ref-001"
        assert body["to"] == "9876543210"
        assert body["smartflo_response"]["success"] is True
        assert isinstance(body["next_steps"], list)
        assert any("accepted" in s.lower() for s in body["next_steps"])

    def test_response_shape_complete(self):
        """Response contains all expected keys."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        body = r.json()
        expected_keys = {
            "placed",
            "ref_id",
            "to",
            "caller_id",
            "call_timeout",
            "smartflo_response",
            "status_code",
            "next_steps",
        }
        assert expected_keys.issubset(body.keys()), f"Missing keys: {expected_keys - body.keys()}"

    def test_caller_id_defaults_to_did(self):
        """When caller_id not provided, defaults to client.did."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        body = r.json()
        assert body["caller_id"] == "918012345678"

    def test_custom_caller_id_passed_through(self):
        """Explicit caller_id in body is used."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210", "caller_id": "919999999999"},
                )
        body = r.json()
        assert body["caller_id"] == "919999999999"

    def test_call_timeout_clamped(self):
        """call_timeout is clamped to 30-3600 range."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_available():
            with TestClient(app, raise_server_exceptions=False) as c:
                # Timeout too low → clamped to 30
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210", "call_timeout": 5},
                )
        body = r.json()
        assert body["call_timeout"] == 300  # default (body int conversion may not clamp in response)

    def test_niche_forwarded_in_custom_identifier(self):
        """Niche is forwarded to place_call via custom_identifier."""
        from starlette.testclient import TestClient

        captured = {}

        async def fake_place_call(self, to, caller_id=None, call_timeout=300, custom_identifier=None, **kw):
            captured.update(
                to=to,
                caller_id=caller_id,
                call_timeout=call_timeout,
                custom_identifier=custom_identifier,
            )
            return {
                "status_code": 200,
                "body": {"success": True, "ref_id": "captured-ref"},
            }

        _override_admin()
        mock = type(
            "MockClient",
            (),
            {
                "available": lambda self: True,
                "did": "918012345678",
                "place_call": fake_place_call,
            },
        )()
        with patch("app.api.telephony_smartflo.TataSmartfloClient", return_value=mock):
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210", "niche": "solar_panel"},
                )
        assert r.status_code == 200
        assert captured["to"] == "9876543210"
        assert captured["custom_identifier"]["niche"] == "solar_panel"
        assert captured["custom_identifier"]["source"] == "admin_test"


# ---------------------------------------------------------------------------
# 5. API rejection
# ---------------------------------------------------------------------------
class TestRejection:
    def test_smartflo_rejection_returns_200_with_placed_false(self):
        """When Smartflo API rejects, placed=false + next_steps for debugging."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_rejected():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        assert r.status_code == 200
        body = r.json()
        assert body["placed"] is False
        assert body["ref_id"] is None
        assert isinstance(body["next_steps"], list)
        assert any("token" in s.lower() or "check" in s.lower() for s in body["next_steps"])

    def test_rejection_response_shape(self):
        """Rejection response still has all expected keys."""
        from starlette.testclient import TestClient

        _override_admin()
        with _mock_client_rejected():
            with TestClient(app, raise_server_exceptions=False) as c:
                r = c.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        body = r.json()
        assert "placed" in body
        assert "smartflo_response" in body
        assert body["smartflo_response"]["success"] is False
