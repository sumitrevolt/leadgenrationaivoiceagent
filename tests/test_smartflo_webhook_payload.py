"""
Tests for Tata Smartflo webhook payload handling.

Why this file exists
--------------------
Smartflo documents its webhook variables with a ``$`` sigil (``$call_id``,
``$call_status``, ``$customer_no_with_prefix`` ...), and can deliver either
``application/json`` or ``application/x-www-form-urlencoded``. The original
handler only looked for bare names (``call_id``, ``status``), so real Smartflo
payloads silently degraded to ``"unknown"``.

Design note
-----------
These tests call the endpoint coroutine **directly** with a hand-built Starlette
``Request`` instead of going through ``TestClient``. Bringing up the full app
(import ~19s + lifespan ~9s per client, with 15+ autouse conftest fixtures and a
120s per-test timeout) makes TestClient-based tests slow and flaky here, and the
behaviour under test is payload parsing, not the ASGI stack.

No network, no database.
"""

from __future__ import annotations

import asyncio
import json
from urllib.parse import urlencode

import pytest

try:
    from starlette.requests import Request

    from app.telephony import smartflo_webhooks as sw

    _IMPORT_OK = True
except ImportError:
    _IMPORT_OK = False

pytestmark = pytest.mark.skipif(not _IMPORT_OK, reason="app not importable")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _build_request(payload: dict, headers: dict | None = None, form: bool = False) -> Request:
    """Build a minimal Starlette Request carrying ``payload``."""
    if form:
        body = urlencode(payload).encode()
        raw_headers = [(b"content-type", b"application/x-www-form-urlencoded")]
    else:
        body = json.dumps(payload).encode()
        raw_headers = [(b"content-type", b"application/json")]

    for key, value in (headers or {}).items():
        raw_headers.append((key.lower().encode(), value.encode()))

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "POST",
        "scheme": "https",
        "path": "/api/webhooks/tata-smartflo",
        "raw_path": b"/api/webhooks/tata-smartflo",
        "query_string": b"",
        "headers": raw_headers,
        "client": ("127.0.0.1", 12345),
        "server": ("leadsgenai.in", 443),
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def _call(payload: dict, headers: dict | None = None, form: bool = False):
    """Invoke the webhook handler and return (status_code, json_body)."""
    request = _build_request(payload, headers=headers, form=form)
    response = asyncio.run(sw.smartflo_webhook(request))
    return response.status_code, json.loads(response.body)


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    """Hermetic: no leaked env, no leaked buffer, no real DB/cache/network.

    IMPORTANT: metering is neutralised by default. The real
    ``meter_call_completion`` reaches for Postgres/Redis, which do not exist
    here - leaving it live makes any "completed" webhook block. Tests that
    assert on metering override it with their own recorder.
    """
    monkeypatch.delenv("SMARTFLO_WEBHOOK_SECRET", raising=False)
    sw._RECENT_WEBHOOKS.clear()

    async def _noop_meter(client_id=None, call_duration_s=0, metadata=None):
        return True

    monkeypatch.setattr(sw, "meter_call_completion", _noop_meter)

    if sw.niche_database is not None:

        def _noop_lead_update(*_a, **_kw):
            return True

        monkeypatch.setattr(sw.niche_database, "update_after_call", _noop_lead_update)

    yield
    sw._RECENT_WEBHOOKS.clear()
    monkeypatch.delenv("SMARTFLO_WEBHOOK_SECRET", raising=False)


# ---------------------------------------------------------------------------
# 1. Real Smartflo format ($-prefixed variables)
# ---------------------------------------------------------------------------
class TestSmartfloDollarFormat:
    def test_dollar_prefixed_payload_is_parsed(self):
        """The whole point of the fix: $vars must resolve, not become 'unknown'."""
        status, body = _call(
            {
                "$call_id": "CA-SF-001",
                "$ref_id": "ref-sf-001",
                "$call_status": "completed",
                "$duration": "95",
                "$billsec": "90",
                "$caller_id_number": "918012345678",
                "$customer_no_with_prefix": "918590126070",
                "$direction": "outbound",
                "$hangup_cause": "NORMAL_CLEARING",
                "$recording_url": "https://rec/1.wav",
                "$start_stamp": "2026-09-07 12:00:00",
                "$end_stamp": "2026-09-07 12:01:35",
            }
        )
        assert status == 200
        assert body["ok"] is True

        logged = sw.get_recent_webhooks(limit=1)[-1]
        assert logged["call_id"] == "CA-SF-001"
        assert logged["ref_id"] == "ref-sf-001"
        assert logged["status"] == "completed"
        assert logged["duration"] == 95  # string coerced to int
        assert logged["billsec"] == 90
        assert logged["from"] == "918012345678"
        assert logged["to"] == "918590126070"
        assert logged["direction"] == "outbound"
        assert logged["hangup_cause"] == "NORMAL_CLEARING"
        assert logged["recording_url"] == "https://rec/1.wav"
        assert logged["start_stamp"] == "2026-09-07 12:00:00"

    def test_call_status_maps_to_status(self):
        """Smartflo sends $call_status, not $status - must still be read."""
        _call({"$call_id": "CA-2", "$call_status": "failed"})
        assert sw.get_recent_webhooks(limit=1)[-1]["status"] == "failed"

    def test_mixed_prefix_payload(self):
        """Sigil is inconsistent in the docs - both forms must work together."""
        _call({"$call_id": "CA-3", "ref_id": "r3", "$call_status": "no-answer"})
        logged = sw.get_recent_webhooks(limit=1)[-1]
        assert logged["call_id"] == "CA-3"
        assert logged["ref_id"] == "r3"
        assert logged["status"] == "no-answer"


# ---------------------------------------------------------------------------
# 2. Backward compatibility (legacy / simplified format used elsewhere)
# ---------------------------------------------------------------------------
class TestLegacyFormat:
    def test_bare_names_still_work(self):
        status, body = _call(
            {
                "call_id": "CA-legacy",
                "ref_id": "ref-legacy",
                "status": "completed",
                "duration": 125,
                "from": "918012345678",
                "to": "9876543210",
                "direction": "outbound",
                "custom_identifier": {"source": "admin_test"},
            }
        )
        assert status == 200
        logged = sw.get_recent_webhooks(limit=1)[-1]
        assert logged["call_id"] == "CA-legacy"
        assert logged["status"] == "completed"
        assert logged["duration"] == 125
        assert logged["custom_identifier"] == {"source": "admin_test"}

    def test_unknown_payload_does_not_500(self):
        """Garbage in -> still 200 (so Smartflo stops retrying), no crash."""
        status, _ = _call({"totally": "unrelated"})
        assert status == 200
        assert sw.get_recent_webhooks(limit=1)[-1]["call_id"] == "unknown"


# ---------------------------------------------------------------------------
# 3. form-urlencoded delivery (Smartflo Content-Type option)
# ---------------------------------------------------------------------------
class TestFormEncoded:
    def test_form_urlencoded_accepted(self):
        status, body = _call(
            {"$call_id": "CA-form", "$call_status": "completed", "$duration": "42"},
            form=True,
        )
        assert status == 200
        logged = sw.get_recent_webhooks(limit=1)[-1]
        assert logged["call_id"] == "CA-form"
        assert logged["status"] == "completed"
        assert logged["duration"] == 42


# ---------------------------------------------------------------------------
# 4. Optional shared-secret auth gate (Smartflo sends no auth of its own)
# ---------------------------------------------------------------------------
class TestSecretGate:
    def test_no_secret_configured_means_open(self):
        """Default (unset) keeps the endpoint open - backward compatible."""
        status, _ = _call({"$call_id": "CA-open", "$call_status": "completed"})
        assert status == 200

    def test_missing_header_rejected_when_secret_set(self, monkeypatch):
        monkeypatch.setenv("SMARTFLO_WEBHOOK_SECRET", "s3cret")
        status, body = _call({"$call_id": "CA-x", "$call_status": "completed"})
        assert status == 401
        assert body["ok"] is False

    def test_wrong_header_rejected(self, monkeypatch):
        monkeypatch.setenv("SMARTFLO_WEBHOOK_SECRET", "s3cret")
        status, _ = _call(
            {"$call_id": "CA-x", "$call_status": "completed"},
            headers={"X-Smartflo-Secret": "wrong"},
        )
        assert status == 401

    def test_correct_header_accepted(self, monkeypatch):
        monkeypatch.setenv("SMARTFLO_WEBHOOK_SECRET", "s3cret")
        status, _ = _call(
            {"$call_id": "CA-ok", "$call_status": "completed"},
            headers={"X-Smartflo-Secret": "s3cret"},
        )
        assert status == 200
        assert sw.get_recent_webhooks(limit=1)[-1]["call_id"] == "CA-ok"


# ---------------------------------------------------------------------------
# 5. Billing uses billsec when present, duration otherwise
# ---------------------------------------------------------------------------
class TestMetering:
    def test_billsec_preferred_over_duration(self, monkeypatch):
        captured = {}

        async def fake_meter(client_id=None, call_duration_s=0, metadata=None):
            captured["duration"] = call_duration_s
            captured["metadata"] = metadata
            return True

        monkeypatch.setattr(sw, "meter_call_completion", fake_meter)
        _call(
            {
                "$call_id": "CA-bill",
                "$call_status": "completed",
                "$duration": "180",
                "$billsec": "150",
                "custom_identifier": '{"client_id": "jiya-makeover"}',
            }
        )
        assert captured["duration"] == 150  # billsec wins
        assert captured["metadata"]["provider"] == "tata_smartflo"

    def test_custom_identifier_json_string_coerced(self, monkeypatch):
        captured = {}

        async def fake_meter(client_id=None, call_duration_s=0, metadata=None):
            captured["client_id"] = client_id
            return True

        monkeypatch.setattr(sw, "meter_call_completion", fake_meter)
        _call(
            {
                "$call_id": "CA-str",
                "$call_status": "completed",
                "custom_identifier": '{"client_id": "jiya-makeover"}',
            }
        )
        assert captured["client_id"] == "jiya-makeover"

    def test_falls_back_to_duration_when_no_billsec(self, monkeypatch):
        captured = {}

        async def fake_meter(client_id=None, call_duration_s=0, metadata=None):
            captured["duration"] = call_duration_s
            return True

        monkeypatch.setattr(sw, "meter_call_completion", fake_meter)
        _call(
            {
                "call_id": "CA-bill2",
                "status": "completed",
                "duration": 180,
                "custom_identifier": {"client_id": "jiya-makeover"},
            }
        )
        assert captured["duration"] == 180

    def test_failed_call_not_metered(self, monkeypatch):
        called = {"v": False}

        async def fake_meter(**kw):
            called["v"] = True
            return True

        monkeypatch.setattr(sw, "meter_call_completion", fake_meter)
        _call({"$call_id": "CA-f", "$call_status": "failed"})
        assert called["v"] is False

    def test_call_connected_boolean_treated_as_connected(self, monkeypatch):
        """Some triggers only send $call_connected, no usable status string."""
        called = {"v": False}

        async def fake_meter(**kw):
            called["v"] = True
            return True

        monkeypatch.setattr(sw, "meter_call_completion", fake_meter)
        _call({"$call_id": "CA-cc", "$call_connected": "true"})
        assert called["v"] is True


# ---------------------------------------------------------------------------
# 6. Buffer bounds
# ---------------------------------------------------------------------------
class TestBufferBounds:
    def test_recent_webhooks_bounded(self):
        for i in range(sw._MAX_RECENT + 25):
            _call({"$call_id": f"CA-{i}", "$call_status": "completed"})
        assert len(sw._RECENT_WEBHOOKS) <= sw._MAX_RECENT
