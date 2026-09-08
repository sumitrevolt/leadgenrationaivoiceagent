"""Signed bridge projection — one authenticated publisher, not 31 keypairs."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from typing import Any


def _secret() -> bytes:
    """Test/dev secret only. Production must set STAFF_BUS_HMAC_SECRET."""
    raw = (os.environ.get("STAFF_BUS_HMAC_SECRET") or "").strip()
    if raw:
        return raw.encode("utf-8")
    # Deterministic inert local default — never a real prod secret.
    return b"staff-bus-inert-dev-only-not-for-prod"


def sign_envelope(envelope: dict[str, Any]) -> dict[str, Any]:
    """Attach HMAC attribution over canonical envelope fields (no secrets in body)."""
    body = {
        "event_id": envelope.get("event_id"),
        "correlation_id": envelope.get("correlation_id"),
        "idempotency_key": envelope.get("idempotency_key"),
        "tenant_id": envelope.get("tenant_id"),
        "source_agent_id": envelope.get("source_agent_id"),
        "destination": envelope.get("destination"),
        "event_type": envelope.get("event_type"),
        "payload_hash": envelope.get("payload_hash"),
        "timestamp": envelope.get("timestamp"),
    }
    msg = json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(_secret(), msg, hashlib.sha256).hexdigest()
    out = dict(envelope)
    out["bridge"] = {
        "strategy": "signed_bridge_projection",
        "publisher": "staff_bus_bridge",
        "signature": sig,
        "alg": "hmac-sha256",
    }
    return out


def verify_envelope_signature(envelope: dict[str, Any]) -> dict[str, Any]:
    bridge = envelope.get("bridge") if isinstance(envelope.get("bridge"), dict) else {}
    got = str(bridge.get("signature") or "")
    probe = dict(envelope)
    probe.pop("bridge", None)
    expected = sign_envelope(probe).get("bridge", {}).get("signature")
    if not got or not expected or not hmac.compare_digest(got, str(expected)):
        return {"ok": False, "error": "bad_signature", "fail_closed": True}
    return {"ok": True}
