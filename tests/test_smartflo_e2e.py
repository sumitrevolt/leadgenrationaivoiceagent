"""
End-to-end test: Smartflo test-call → webhook callback simulation.

Chains the full outbound call lifecycle:
  1. Admin places a test call via POST /api/telephony/smartflo/test-call
  2. Smartflo accepts and returns ref_id (mocked)
  3. Smartflo later sends a status webhook to POST /api/webhooks/tata-smartflo
  4. Webhook handler logs CDR, meters the call, updates lead status

No network — both the TataSmartfloClient and downstream services are mocked.
Verifies the complete chain: admin API → provider → webhook → CDR + billing.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest


# ---------------------------------------------------------------------------
# Import guard
# ---------------------------------------------------------------------------
try:
    from app.main import app
    from app.telephony.smartflo_webhooks import get_recent_webhooks

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="app not importable")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clear_deps_and_webhooks():
    """Clean dependency overrides + webhook buffer before each test."""
    from app.telephony.smartflo_webhooks import _RECENT_WEBHOOKS

    _RECENT_WEBHOOKS.clear()
    yield
    app.dependency_overrides.clear()
    _RECENT_WEBHOOKS.clear()


def _override_admin():
    """Override require_admin for unauthenticated test requests."""
    from app.api.auth_deps import require_admin

    app.dependency_overrides[require_admin] = lambda: type(
        "Admin", (), {"email": "test@leadsgenai.in"}
    )()


# ---------------------------------------------------------------------------
# Mock client that records what was sent
# ---------------------------------------------------------------------------
class _RecordingClient:
    """Mock TataSmartfloClient that records place_call args."""

    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.did = "918012345678"

    def available(self) -> bool:
        return True

    async def place_call(self, **kwargs) -> dict:
        self.calls.append(kwargs)
        return {
            "status_code": 200,
            "body": {
                "success": True,
                "message": "Originate successfully queued",
                "ref_id": f"e2e-ref-{len(self.calls):03d}",
            },
        }


# ---------------------------------------------------------------------------
# 1. Happy path: test-call → webhook completed
# ---------------------------------------------------------------------------
class TestHappyPath:
    async def test_call_placed_then_webhook_completed(self):
        """Full lifecycle: admin places call → Smartflo accepts → webhook fires."""
        from starlette.testclient import TestClient

        client = _RecordingClient()

        _override_admin()
        with patch("app.api.telephony_smartflo.TataSmartfloClient", return_value=client):
            with TestClient(app, raise_server_exceptions=False) as tc:
                # Step 1: Admin places a test call
                r = tc.post(
                    "/api/telephony/smartflo/test-call",
                    json={
                        "to": "9876543210",
                        "niche": "salon_spa",
                        "caller_id": "918012345678",
                    },
                )
        assert r.status_code == 200
        body = r.json()
        assert body["placed"] is True
        ref_id = body["ref_id"]
        assert ref_id.startswith("e2e-ref-")

        # Verify place_call was called with correct args
        assert len(client.calls) == 1
        call_args = client.calls[0]
        assert call_args["to"] == "9876543210"
        assert call_args["caller_id"] == "918012345678"
        assert call_args["custom_identifier"]["niche"] == "salon_spa"
        assert call_args["custom_identifier"]["source"] == "admin_test"

        # Step 2: Simulate Smartflo webhook (call completed)
        webhook_payload = {
            "call_id": "CA-e2e-001",
            "ref_id": ref_id,
            "status": "completed",
            "duration": 125,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {
                "source": "admin_test",
                "niche": "salon_spa",
                "client_id": "jiya-makeover",
            },
        }

        with TestClient(app, raise_server_exceptions=False) as tc:
            r2 = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)

        assert r2.status_code == 200
        assert r2.json()["ok"] is True

        # Verify webhook was logged
        recent = get_recent_webhooks(limit=10)
        assert len(recent) >= 1
        logged = recent[-1]
        assert logged["call_id"] == "CA-e2e-001"
        assert logged["ref_id"] == ref_id
        assert logged["status"] == "completed"
        assert logged["duration"] == 125

    async def test_call_placed_then_webhook_failed(self):
        """Lifecycle: call placed → Smartflo reports failure."""
        from starlette.testclient import TestClient

        client = _RecordingClient()

        _override_admin()
        with patch("app.api.telephony_smartflo.TataSmartfloClient", return_value=client):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        ref_id = r.json()["ref_id"]

        # Webhook: call failed
        webhook_payload = {
            "call_id": "CA-e2e-002",
            "ref_id": ref_id,
            "status": "failed",
            "duration": 0,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {"source": "admin_test"},
        }

        with TestClient(app, raise_server_exceptions=False) as tc:
            r2 = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)
        assert r2.status_code == 200

        recent = get_recent_webhooks(limit=10)
        assert len(recent) >= 1
        assert recent[-1]["status"] == "failed"
        assert recent[-1]["duration"] == 0

    async def test_call_placed_then_webhook_no_answer(self):
        """Lifecycle: call placed → no answer."""
        from starlette.testclient import TestClient

        client = _RecordingClient()

        _override_admin()
        with patch("app.api.telephony_smartflo.TataSmartfloClient", return_value=client):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
        ref_id = r.json()["ref_id"]

        webhook_payload = {
            "call_id": "CA-e2e-003",
            "ref_id": ref_id,
            "status": "no-answer",
            "duration": 0,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {"source": "admin_test"},
        }

        with TestClient(app, raise_server_exceptions=False) as tc:
            r2 = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)
        assert r2.status_code == 200

        recent = get_recent_webhooks(limit=10)
        assert recent[-1]["status"] == "no-answer"


# ---------------------------------------------------------------------------
# 2. Webhook → billing metering chain
# ---------------------------------------------------------------------------
class TestBillingChain:
    async def test_completed_webhook_triggers_metering(self):
        """Webhook with status=completed triggers meter_call_completion."""
        from starlette.testclient import TestClient

        meter_called = {}

        async def fake_meter(client_id=None, call_duration_s=0, metadata=None):
            meter_called["client_id"] = client_id
            meter_called["duration"] = call_duration_s
            meter_called["metadata"] = metadata
            return True

        webhook_payload = {
            "call_id": "CA-billing-001",
            "ref_id": "ref-billing-001",
            "status": "completed",
            "duration": 180,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {
                "source": "admin_test",
                "client_id": "jiya-makeover",
            },
        }

        with patch("app.telephony.smartflo_webhooks.meter_call_completion", fake_meter):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)

        assert r.status_code == 200
        assert meter_called.get("client_id") == "jiya-makeover"
        assert meter_called.get("duration") == 180

    async def test_failed_webhook_skips_metering(self):
        """Webhook with status=failed does NOT trigger metering."""
        from starlette.testclient import TestClient

        meter_called = False

        async def fake_meter(**kwargs):
            nonlocal meter_called
            meter_called = True
            return True

        webhook_payload = {
            "call_id": "CA-billing-002",
            "ref_id": "ref-billing-002",
            "status": "failed",
            "duration": 0,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {"source": "admin_test"},
        }

        with patch("app.telephony.smartflo_webhooks.meter_call_completion", fake_meter):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)

        assert r.status_code == 200
        assert meter_called is False


# ---------------------------------------------------------------------------
# 3. Webhook → lead status update chain
# ---------------------------------------------------------------------------
class TestLeadStatusChain:
    async def test_completed_webhook_updates_lead(self):
        """Webhook with lead_id in custom_identifier triggers lead status update."""
        from starlette.testclient import TestClient

        lead_updates = {}

        def fake_update(lead_id=None, disposition=None, call_duration_s=0, provider=None):
            lead_updates["lead_id"] = lead_id
            lead_updates["disposition"] = disposition
            lead_updates["duration"] = call_duration_s
            lead_updates["provider"] = provider

        webhook_payload = {
            "call_id": "CA-lead-001",
            "ref_id": "ref-lead-001",
            "status": "completed",
            "duration": 90,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {
                "source": "admin_test",
                "lead_id": "lead-42",
            },
        }

        with patch("app.telephony.smartflo_webhooks.niche_database", type(
            "MockDB", (), {"update_after_call": staticmethod(fake_update)}
        )()):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)

        assert r.status_code == 200
        assert lead_updates.get("lead_id") == "lead-42"
        assert lead_updates.get("disposition") == "qualified"  # duration > 60s
        assert lead_updates.get("duration") == 90

    async def test_short_call_updates_lead_as_called(self):
        """Short completed call (< 60s) → disposition=called, not qualified."""
        from starlette.testclient import TestClient

        lead_updates = {}

        def fake_update(lead_id=None, disposition=None, call_duration_s=0, provider=None):
            lead_updates["disposition"] = disposition

        webhook_payload = {
            "call_id": "CA-lead-002",
            "ref_id": "ref-lead-002",
            "status": "completed",
            "duration": 30,
            "from": "918012345678",
            "to": "9876543210",
            "direction": "outbound",
            "custom_identifier": {
                "source": "admin_test",
                "lead_id": "lead-43",
            },
        }

        with patch("app.telephony.smartflo_webhooks.niche_database", type(
            "MockDB", (), {"update_after_call": staticmethod(fake_update)}
        )()):
            with TestClient(app, raise_server_exceptions=False) as tc:
                r = tc.post("/api/webhooks/tata-smartflo", json=webhook_payload)

        assert r.status_code == 200
        assert lead_updates.get("disposition") == "called"  # < 60s


# ---------------------------------------------------------------------------
# 4. Webhook resilience
# ---------------------------------------------------------------------------
class TestWebhookResilience:
    async def test_empty_body_returns_200(self):
        """Empty webhook body should not crash — always 200."""
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as tc:
            r = tc.post("/api/webhooks/tata-smartflo", json={})
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_malformed_json_returns_200(self):
        """Malformed body should not crash — always 200."""
        from starlette.testclient import TestClient

        with TestClient(app, raise_server_exceptions=False) as tc:
            r = tc.post(
                "/api/webhooks/tata-smartflo",
                content="not json at all",
                headers={"Content-Type": "application/json"},
            )
        assert r.status_code == 200

    async def test_webhook_buffer_bounded(self):
        """Webhook buffer doesn't grow past MAX_RECENT."""
        from app.telephony.smartflo_webhooks import _MAX_RECENT, _RECENT_WEBHOOKS
        from starlette.testclient import TestClient

        # Send 250 webhooks
        for i in range(250):
            payload = {
                "call_id": f"CA-bound-{i:03d}",
                "status": "completed",
                "duration": i,
                "custom_identifier": {},
            }
            with TestClient(app, raise_server_exceptions=False) as tc:
                tc.post("/api/webhooks/tata-smartflo", json=payload)

        assert len(_RECENT_WEBHOOKS) <= _MAX_RECENT


# ---------------------------------------------------------------------------
# 5. Multiple calls lifecycle
# ---------------------------------------------------------------------------
class TestMultipleCalls:
    async def test_two_calls_independently_tracked(self):
        """Two test-calls → two webhooks, each tracked independently."""
        from starlette.testclient import TestClient

        client = _RecordingClient()

        _override_admin()
        with patch("app.api.telephony_smartflo.TataSmartfloClient", return_value=client):
            with TestClient(app, raise_server_exceptions=False) as tc:
                # Call 1
                r1 = tc.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543210"},
                )
                # Call 2
                r2 = tc.post(
                    "/api/telephony/smartflo/test-call",
                    json={"to": "9876543211"},
                )

        ref1 = r1.json()["ref_id"]
        ref2 = r2.json()["ref_id"]
        assert ref1 != ref2

        # Webhook for call 1
        with TestClient(app, raise_server_exceptions=False) as tc:
            tc.post("/api/webhooks/tata-smartflo", json={
                "call_id": "CA-multi-001", "ref_id": ref1,
                "status": "completed", "duration": 120,
                "custom_identifier": {},
            })
            # Webhook for call 2
            tc.post("/api/webhooks/tata-smartflo", json={
                "call_id": "CA-multi-002", "ref_id": ref2,
                "status": "no-answer", "duration": 0,
                "custom_identifier": {},
            })

        recent = get_recent_webhooks(limit=10)
        assert len(recent) >= 2
        # Both tracked with correct refs
        refs_seen = {w["ref_id"] for w in recent[-2:]}
        assert ref1 in refs_seen
        assert ref2 in refs_seen
