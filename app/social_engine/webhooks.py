"""social_engine.webhooks — Phase 4/12 provider webhook signature verifiers.

Provider webhook (Meta / LinkedIn / GBP push / X) signatures MUST be verified
before we accept any status update — otherwise a forged POST could flip a
customer's ledger to "published" or "failed" without evidence.

  verify_meta_signature(payload_bytes, signature_header, app_secret) -> bool
  verify_linkedin_signature(payload_bytes, signature_header, secret) -> bool
  verify_generic_hmac_sha256(payload_bytes, signature_header, secret) -> bool

All functions:
  - constant-time compare (hmac.compare_digest)
  - never raise
  - Fail-CLOSED: unknown/empty header → False
  - Case-insensitive on the `sha256=` prefix

Reference:
  Meta: `X-Hub-Signature-256: sha256=<hex>`
  LinkedIn: `X-Li-Signature: sha256=<hex>` (member webhooks;
    Community-Management is different — verify at activation)
"""

from __future__ import annotations

import hashlib
import hmac
from typing import Any

from app.utils.logger import setup_logger

logger = setup_logger(__name__)


def _extract_sha256_hex(header: str) -> str:
    """Accepts 'sha256=abc123' / 'SHA256=abc123' / bare 'abc123'. Returns
    lowercase hex or '' if malformed."""
    if not header:
        return ""
    s = header.strip()
    if "=" in s:
        prefix, _, hexpart = s.partition("=")
        if prefix.strip().lower() != "sha256":
            return ""
        s = hexpart.strip()
    s = s.lower()
    # Must look like 64-char hex.
    if len(s) != 64 or any(c not in "0123456789abcdef" for c in s):
        return ""
    return s


def verify_generic_hmac_sha256(
    payload: bytes,
    signature_header: str,
    secret: str,
) -> bool:
    """Generic HMAC-SHA256 verifier. Returns False on any anomaly (empty
    inputs, malformed header, mismatch). Constant-time compare."""
    try:
        if not secret or payload is None:
            return False
        got_hex = _extract_sha256_hex(signature_header)
        if not got_hex:
            return False
        expected = hmac.new(
            key=secret.encode("utf-8") if isinstance(secret, str) else secret,
            msg=payload if isinstance(payload, bytes) else str(payload).encode("utf-8"),
            digestmod=hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, got_hex)
    except Exception as e:
        logger.debug(f"[webhooks] hmac verify failed: {e}")
        return False


def verify_meta_signature(payload: bytes, signature_header: str, app_secret: str) -> bool:
    """Meta / Facebook Graph webhook — `X-Hub-Signature-256` header.
    See https://developers.facebook.com/docs/graph-api/webhooks/getting-started"""
    return verify_generic_hmac_sha256(payload, signature_header, app_secret)


def verify_linkedin_signature(payload: bytes, signature_header: str, client_secret: str) -> bool:
    """LinkedIn webhook — `X-Li-Signature: sha256=<hex>` (verify at activation
    — LinkedIn ran a v2 migration recently). Same math as Meta."""
    return verify_generic_hmac_sha256(payload, signature_header, client_secret)


def dispatch_status_update(
    provider_post_id: str,
    new_status: str,
    detail: str = "",
    client_id: str = "",
) -> dict[str, Any]:
    """Reflect a verified webhook status update into the ledger + store. Called
    only AFTER the signature verifier returned True. Never raises. Idempotent
    per (provider_post_id, new_status)."""
    try:
        # Best-effort: find the matching job by post_id and mark it.
        from . import store as _store

        rows = _store._latest()
        target = None
        for jid, r in rows.items():
            if str(r.get("post_id") or "") == provider_post_id:
                target = (jid, r)
                break
        if target:
            jid, r = target
            if str(r.get("status") or "") != new_status:
                _store.mark(jid, new_status, last_error=detail[:200])
        # Emit a ledger event so admin cockpit picks up the async status flip.
        try:
            from app.marketing import delivery_ledger

            ev = {
                "published": "post_published",
                "failed": "post_failed",
                "dead": "post_failed",
                "cancelled": "post_cancelled",
            }.get(new_status)
            if ev:
                delivery_ledger.log_event(
                    client_id or (target[1].get("client_id") if target else ""),
                    ev,
                    detail=(detail or provider_post_id)[:200],
                    key=f"webhook_status:{provider_post_id}:{new_status}",
                )
        except Exception:
            pass
        return {
            "ok": True,
            "post_id": provider_post_id,
            "status": new_status,
            "matched_job": bool(target),
        }
    except Exception as e:
        logger.warning(f"[webhooks] dispatch failed: {e}")
        return {"ok": False, "error": str(e)[:150]}
