"""customer_webhooks.py — programmable event delivery to customer-owned URLs.

Customers (`/app/customer`) register a URL + a set of events; the platform
HMAC-SHA256 signs and POSTs a JSON envelope on every match. This is a paid
SaaS feature (the audit named it as "sellable feature, free + no creds") —
once a customer has a CRM/automation tool, they want THEIR webhook fired
when their lead qualifies, not to poll.

Design rules:
- **Storage by jsonl** (data/customer_webhooks.jsonl + data/customer_webhook_deliveries.jsonl)
  — matches project pattern (llm_metrics, consent_ledger, lead_usage). No
  extra DB table to migrate.
- **Atomic rewrite** on register/remove via a temp file (single-writer; the
  customer's webhook count is tiny — a few per client).
- **HMAC-SHA256** of the raw JSON body with the per-webhook secret, sent as
  `X-LeadGen-Signature: sha256=...` plus `X-LeadGen-Event` + `X-LeadGen-Delivery`.
  Standard Stripe/GitHub pattern — customer-side verifiers are well-known.
- **Retries**: 3 attempts with exponential backoff (5s → 30s → 5min). 2xx =
  success; everything else = retry. Final failure logged in deliveries.jsonl.
- **Bounded deliveries log**: tail-read last 500 lines for the recent-deliveries
  view; full history rotates in place (operators can ship to S3 if they want).
- **Master flag**: `CUSTOMER_WEBHOOKS=1` — OFF default. With it off, register
  still works (drafts) but emit() is a no-op. Customer-side: feature absent
  until enabled at infra level.
- **Allow-listed URL hosts** (`CUSTOMER_WEBHOOK_DENY_PRIVATE=1` default ON):
  reject localhost/private/link-local URLs at register-time so a customer
  cannot make us SSRF into our own infra (revisiting the C4 SSRF lesson —
  same defensive pattern).
- **Per-emit fire-and-forget**: emit() returns immediately after spawning
  the delivery task. Callers (Razorpay webhook, voice qualifier) are never
  blocked by a customer's slow endpoint.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import socket
import time
import uuid
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse

from app.utils.logger import setup_logger

logger = setup_logger(__name__)

_FLAG = "CUSTOMER_WEBHOOKS"
_DENY_PRIVATE_FLAG = "CUSTOMER_WEBHOOK_DENY_PRIVATE"  # default ON
_DATA_DIR = Path(os.environ.get("DATA_DIR", "data"))
_REG_PATH = _DATA_DIR / "customer_webhooks.jsonl"
_DEL_PATH = _DATA_DIR / "customer_webhook_deliveries.jsonl"

# Retry schedule (seconds between attempts). 3 attempts total = 1 initial + 2 retries.
_RETRY_BACKOFF_S = (5.0, 30.0, 300.0)
_HTTP_TIMEOUT_S = 10.0
_DELIVERIES_TAIL = 500

# Strong refs to in-flight background delivery tasks. Without this the event loop
# only weak-refs them, so a delivery task can be garbage-collected mid-flight
# (silent webhook-delivery loss). Discarded automatically on completion.
_INFLIGHT_DELIVERIES: set = set()

# Supported event types — keep this list small + stable so customers' verifiers
# don't break when we add features. New types append; never rename.
SUPPORTED_EVENTS = (
    "lead.created",
    "lead.qualified",
    "call.completed",
    "call.report.ready",
    "payment.received",
    "subscription.activated",
    "subscription.cancelled",
)


# --------------------------------------------------------------------------- #
# Flag helpers
# --------------------------------------------------------------------------- #
def enabled() -> bool:
    return os.environ.get(_FLAG, "0").strip().lower() in ("1", "true", "yes")


def _deny_private() -> bool:
    """Default ON. Set CUSTOMER_WEBHOOK_DENY_PRIVATE=0 only for tests/dev."""
    return os.environ.get(_DENY_PRIVATE_FLAG, "1").strip().lower() in ("1", "true", "yes")


# --------------------------------------------------------------------------- #
# URL validation — same SSRF defense as the /site-audit fix (C4 in code-review)
# --------------------------------------------------------------------------- #
def _is_url_safe(url: str) -> tuple[bool, str]:
    """(ok, reason). False = reject (no register). Defends against customer-
    supplied URL pointing at our own infra (cloud-metadata, internal DBs)."""
    try:
        p = urlparse(url)
    except Exception:
        return False, "url_parse_failed"
    if p.scheme not in {"http", "https"}:
        return False, "scheme_not_http(s)"
    host = (p.hostname or "").strip()
    if not host:
        return False, "no_host"
    if not _deny_private():
        return True, ""
    # Refuse obvious docker-network names
    if host in {
        "localhost",
        "leadgen_app",
        "leadgen_db",
        "leadgen_redis",
        "pgbouncer",
        "qdrant",
        "redis",
        "postgres",
        "tempo",
        "loki",
        "prometheus",
        "grafana",
    }:
        return False, "internal_hostname"
    # Resolve and refuse private/loopback/link-local/reserved IPs.
    try:
        addrs = socket.getaddrinfo(host, None)
    except Exception:
        return False, "dns_resolve_failed"
    for entry in addrs:
        try:
            ip = ipaddress.ip_address(entry[4][0])
        except Exception:
            continue
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            return False, f"private_ip:{ip}"
    return True, ""


# --------------------------------------------------------------------------- #
# Storage
# --------------------------------------------------------------------------- #
def _ensure_dir() -> None:
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass


def _read_registrations() -> list[dict[str, Any]]:
    if not _REG_PATH.exists():
        return []
    try:
        out: list[dict[str, Any]] = []
        for line in _REG_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
        return out
    except Exception:
        return []


def _atomic_rewrite(rows: list[dict[str, Any]]) -> bool:
    """Replace the registration file with `rows`. Atomic via temp-file rename."""
    _ensure_dir()
    tmp = _REG_PATH.with_suffix(".jsonl.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        tmp.replace(_REG_PATH)
        return True
    except Exception as exc:
        logger.error("customer_webhooks registry rewrite failed: %s", exc)
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def _append_delivery(row: dict[str, Any]) -> None:
    _ensure_dir()
    try:
        with _DEL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as exc:
        logger.debug("customer_webhooks delivery write swallowed: %s", exc)


def _read_deliveries(limit: int = _DELIVERIES_TAIL) -> list[dict[str, Any]]:
    if not _DEL_PATH.exists():
        return []
    try:
        lines = _DEL_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out


# --------------------------------------------------------------------------- #
# CRUD
# --------------------------------------------------------------------------- #
def _redact(row: dict[str, Any]) -> dict[str, Any]:
    """Customer-safe shape — secret hidden after creation."""
    r = dict(row)
    sec = r.pop("secret", None)
    r["secret_preview"] = (sec[:6] + "..." + sec[-4:]) if sec and len(sec) > 12 else "***"
    return r


def register(
    client_id: str,
    url: str,
    events: list[str],
    description: str = "",
) -> dict[str, Any]:
    """Create a new webhook. Returns full row INCLUDING secret (only time it's
    visible). Subsequent reads redact the secret."""
    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    url = (url or "").strip()
    if not url:
        return {"ok": False, "error": "url required"}
    safe, reason = _is_url_safe(url)
    if not safe:
        return {"ok": False, "error": f"url rejected: {reason}"}
    evs = [e.strip() for e in (events or []) if e.strip()]
    bad = [e for e in evs if e not in SUPPORTED_EVENTS]
    if bad:
        return {
            "ok": False,
            "error": f"unknown event types: {bad}",
            "supported": list(SUPPORTED_EVENTS),
        }
    if not evs:
        return {
            "ok": False,
            "error": "at least one event required",
            "supported": list(SUPPORTED_EVENTS),
        }

    wh_id = "wh_" + uuid.uuid4().hex[:18]
    secret = "whsec_" + secrets.token_urlsafe(24)
    row = {
        "id": wh_id,
        "client_id": cid,
        "url": url,
        "secret": secret,
        "events": evs,
        "enabled": True,
        "description": description[:120],
        "created_at": int(time.time()),
    }
    rows = _read_registrations()
    rows.append(row)
    if not _atomic_rewrite(rows):
        return {"ok": False, "error": "storage write failed"}
    return {"ok": True, **row}


def list_for(client_id: str) -> list[dict[str, Any]]:
    """All webhooks for a client (secrets redacted)."""
    cid = (client_id or "").strip()
    if not cid:
        return []
    return [_redact(r) for r in _read_registrations() if r.get("client_id") == cid]


def get_one(webhook_id: str, client_id: str) -> dict[str, Any] | None:
    """Return raw row (incl. secret) IF the caller owns it. Else None."""
    cid = (client_id or "").strip()
    for r in _read_registrations():
        if r.get("id") == webhook_id and r.get("client_id") == cid:
            return r
    return None


def remove(webhook_id: str, client_id: str) -> bool:
    """Delete a webhook the caller owns. False if not found / not owned."""
    cid = (client_id or "").strip()
    rows = _read_registrations()
    new_rows = [r for r in rows if not (r.get("id") == webhook_id and r.get("client_id") == cid)]
    if len(new_rows) == len(rows):
        return False
    return _atomic_rewrite(new_rows)


def recent_deliveries(webhook_id: str, client_id: str, limit: int = 50) -> list[dict[str, Any]]:
    """Last N delivery attempts for one webhook the caller owns."""
    cid = (client_id or "").strip()
    if not get_one(webhook_id, cid):
        return []
    out = [
        r
        for r in _read_deliveries(limit=_DELIVERIES_TAIL)
        if r.get("webhook_id") == webhook_id and r.get("client_id") == cid
    ]
    return out[-max(1, int(limit)) :]


# --------------------------------------------------------------------------- #
# Delivery
# --------------------------------------------------------------------------- #
def _sign(body: bytes, secret: str) -> str:
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={mac}"


async def _deliver_one(
    row: dict[str, Any],
    event_type: str,
    payload: dict[str, Any],
    delivery_id: str | None = None,
    *,
    schedule: tuple[float, ...] = _RETRY_BACKOFF_S,
) -> dict[str, Any]:
    """POST to a single webhook with retries. Records EVERY attempt."""
    delivery_id = delivery_id or ("del_" + uuid.uuid4().hex[:18])
    envelope = {
        "id": delivery_id,
        "type": event_type,
        "created_at": int(time.time()),
        "data": payload,
    }
    body_bytes = json.dumps(envelope, ensure_ascii=False).encode("utf-8")
    sig = _sign(body_bytes, row.get("secret", ""))
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "LeadGenAI-Webhook/1.0",
        "X-LeadGen-Event": event_type,
        "X-LeadGen-Delivery": delivery_id,
        "X-LeadGen-Signature": sig,
    }

    import httpx

    last_status = 0
    last_error = ""
    for attempt_idx, _backoff in enumerate(schedule):
        try:
            # Re-check host safety immediately before EACH connect attempt, not just
            # at registration time — closes the DNS-rebinding TOCTOU (customer points
            # a hostname at a public IP to register, then repoints it to
            # 127.0.0.1/169.254.169.254/etc. before delivery or a later retry fires).
            # Same "re-check right before fetch" pattern as the /site-audit SSRF fix
            # (app/marketing/website_auditor.py), not IP-pinning — accepted precedent
            # in this codebase. Production audit 2026-07-01, security batch 2.
            ok, reason = _is_url_safe(row["url"])
            if not ok:
                last_error = f"url_unsafe:{reason}"
                logger.warning(
                    "customer_webhooks: delivery blocked, url now unsafe (%s) for webhook %s",
                    reason,
                    row.get("id"),
                )
                break
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT_S) as client:
                resp = await client.post(row["url"], content=body_bytes, headers=headers)
                last_status = resp.status_code
                if 200 <= resp.status_code < 300:
                    _append_delivery(
                        {
                            "id": delivery_id,
                            "webhook_id": row["id"],
                            "client_id": row["client_id"],
                            "event_type": event_type,
                            "url": row["url"],
                            "attempts": attempt_idx + 1,
                            "last_status": last_status,
                            "delivered": True,
                            "at": int(time.time()),
                        }
                    )
                    return {
                        "delivered": True,
                        "attempts": attempt_idx + 1,
                        "status": last_status,
                        "id": delivery_id,
                    }
                last_error = f"http_{resp.status_code}"
        except Exception as exc:
            last_error = type(exc).__name__
        # Backoff before next attempt (skip after last)
        if attempt_idx < len(schedule) - 1:
            try:
                await asyncio.sleep(schedule[attempt_idx])
            except Exception:
                break
    # All attempts failed
    _append_delivery(
        {
            "id": delivery_id,
            "webhook_id": row["id"],
            "client_id": row["client_id"],
            "event_type": event_type,
            "url": row["url"],
            "attempts": len(schedule),
            "last_status": last_status,
            "last_error": last_error,
            "delivered": False,
            "at": int(time.time()),
        }
    )
    # L.3 dead-letter alert — best-effort; never blocks delivery completion.
    try:
        from app.platform import ops_alerts as _oa

        _oa.maybe_alert_webhook_dead_letter(row["id"], row["client_id"], row["url"])
    except Exception as exc:
        logger.debug("dead-letter alert hook swallowed: %s", exc)
    return {
        "delivered": False,
        "attempts": len(schedule),
        "status": last_status,
        "error": last_error,
        "id": delivery_id,
    }


async def emit(client_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Fire-and-forget event delivery to all matching webhooks of a client.

    Returns {"emitted": n, "skipped": m} immediately — actual delivery runs
    in background. Callers (Razorpay webhook handler, qualifier flow) are
    never blocked.
    """
    # Phase-3 Flow Runner event trigger (additive, self-gated, never-raise).
    # Runs regardless of CUSTOMER_WEBHOOKS — flow triggers must not depend on a
    # customer having registered an HTTP webhook. fire_event self-gates on
    # FLOW_RUNNER + FLOW_AUTO_TRIGGERS, so it is inert until both flags are on.
    try:
        from app.automation import flow_triggers

        flow_triggers.fire_event(event_type, payload or {}, (client_id or "").strip())
    except Exception:
        pass
    if not enabled():
        return {"emitted": 0, "skipped": 0, "disabled": True}
    cid = (client_id or "").strip()
    if not cid or event_type not in SUPPORTED_EVENTS:
        return {"emitted": 0, "skipped": 0, "error": "bad_args" if cid else "no_client_id"}
    rows = _read_registrations()
    targets = [
        r
        for r in rows
        if r.get("client_id") == cid
        and r.get("enabled", True)
        and event_type in (r.get("events") or [])
    ]
    if not targets:
        return {"emitted": 0, "skipped": 0}
    emitted = 0
    for row in targets:
        try:
            _t = asyncio.create_task(_deliver_one(row, event_type, payload))
            _INFLIGHT_DELIVERIES.add(_t)
            _t.add_done_callback(_INFLIGHT_DELIVERIES.discard)
            emitted += 1
        except RuntimeError:
            # No running loop (sync call site) — last-resort sync deliver, no retries
            try:
                asyncio.run(_deliver_one(row, event_type, payload, schedule=(_HTTP_TIMEOUT_S,)))
                emitted += 1
            except Exception:
                pass
    return {"emitted": emitted, "skipped": 0}


async def fire_test(webhook_id: str, client_id: str) -> dict[str, Any]:
    """Operator-visible test: one immediate POST, no retries, returns result."""
    row = get_one(webhook_id, client_id)
    if not row:
        return {"ok": False, "error": "not_found"}
    return await _deliver_one(
        row,
        "webhook.test",
        {"hello": "from leadsgenai.in", "ts": int(time.time())},
        schedule=(_HTTP_TIMEOUT_S,),  # one attempt, no retries
    )


def set_enabled(webhook_id: str, client_id: str, enabled: bool) -> dict[str, Any]:
    """L.1: pause/resume a webhook without losing subscriptions or delivery
    history. emit() already respects the `enabled` flag — this is the toggle.
    """
    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    rows = _read_registrations()
    found = False
    for r in rows:
        if r.get("id") == webhook_id and r.get("client_id") == cid:
            r["enabled"] = bool(enabled)
            r["enabled_toggled_at"] = int(time.time())
            found = True
    if not found:
        return {"ok": False, "error": "not_found"}
    if not _atomic_rewrite(rows):
        return {"ok": False, "error": "storage write failed"}
    return {"ok": True, "id": webhook_id, "enabled": bool(enabled)}


def consecutive_failure_count(webhook_id: str) -> int:
    """L.3: count of consecutive failed deliveries for one webhook ending at
    the most-recent attempt. Resets to 0 on the first successful delivery
    walking back from newest. Used by the dead-letter alert hook."""
    rows = [
        r for r in _read_deliveries(limit=_DELIVERIES_TAIL) if r.get("webhook_id") == webhook_id
    ]
    n = 0
    for r in reversed(rows):
        if r.get("delivered"):
            break
        n += 1
    return n


def rotate_secret(webhook_id: str, client_id: str) -> dict[str, Any]:
    """K.3: replace a webhook's signing secret in-place. Subscriptions and the
    webhook ID stay; only the secret changes. Returns the NEW plaintext secret
    once (same pattern as create) — customer must update their verifier.

    Use case: leaked secret recovery. Avoids the delete-then-recreate dance
    that loses delivery history and forces a new webhook ID.
    """
    cid = (client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "client_id required"}
    rows = _read_registrations()
    new_secret = "whsec_" + secrets.token_urlsafe(24)
    found = False
    for r in rows:
        if r.get("id") == webhook_id and r.get("client_id") == cid:
            r["secret"] = new_secret
            r["secret_rotated_at"] = int(time.time())
            found = True
    if not found:
        return {"ok": False, "error": "not_found"}
    if not _atomic_rewrite(rows):
        return {"ok": False, "error": "storage write failed"}
    return {"ok": True, "secret": new_secret, "id": webhook_id}


async def retry_delivery(webhook_id: str, client_id: str, delivery_id: str) -> dict[str, Any]:
    """K.2: replay a prior delivery attempt. Looks the original event_type +
    payload up from data/customer_webhook_deliveries.jsonl. Useful when the
    customer's endpoint was briefly down and the original 3 retries exhausted.
    """
    row = get_one(webhook_id, client_id)
    if not row:
        return {"ok": False, "error": "webhook_not_found"}
    # Find the original delivery record. Payload isn't persisted (privacy +
    # storage size); we replay with the event_type and a marker payload so
    # the customer's verifier sees a legitimate signed retry. If their
    # event-handler is idempotent on X-LeadGen-Delivery (as the verifier
    # docs urge), they de-dupe correctly.
    original = None
    for r in _read_deliveries(limit=_DELIVERIES_TAIL):
        if r.get("id") == delivery_id and r.get("webhook_id") == webhook_id:
            original = r
            break
    if not original:
        return {"ok": False, "error": "delivery_not_found"}
    if original.get("delivered"):
        return {"ok": False, "error": "delivery_already_succeeded"}
    return await _deliver_one(
        row,
        str(original.get("event_type") or "webhook.test"),
        {"retry_of": delivery_id, "ts": int(time.time())},
        delivery_id="del_retry_" + uuid.uuid4().hex[:14],
        schedule=(_HTTP_TIMEOUT_S,),  # single-shot — operator can re-retry
    )


def fire_emit(client_id: str, event_type: str, payload: dict[str, Any]) -> None:
    """Fire-and-forget customer webhook from billing/sync paths. Never raises."""
    try:
        import asyncio as _asyncio

        cid = (client_id or "").strip()
        if not cid or event_type not in SUPPORTED_EVENTS:
            return
        try:
            _loop = _asyncio.get_running_loop()
            _loop.create_task(emit(cid, event_type, payload))
        except RuntimeError:
            try:
                _asyncio.run(emit(cid, event_type, payload))
            except Exception:
                pass
    except Exception:
        pass


__all__ = [
    "enabled",
    "SUPPORTED_EVENTS",
    "fire_emit",
    "register",
    "list_for",
    "remove",
    "recent_deliveries",
    "emit",
    "fire_test",
    "rotate_secret",
    "retry_delivery",
    "set_enabled",
    "consecutive_failure_count",
]
