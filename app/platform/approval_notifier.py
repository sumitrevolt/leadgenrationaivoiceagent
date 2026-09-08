"""Idempotent, consent-gated pending-approval email notifications + audit.

Design (Phase-1 customer-delivery, 2026-07-12):
- Env-gated by APPROVAL_EMAIL_NOTIFY (default OFF) so nothing sends by accident.
- Client allowlist is mandatory (`APPROVAL_EMAIL_CLIENT_ALLOWLIST`); empty means
  zero recipients even when the main flag is accidentally enabled.
- A sweep selects at most one pending approval per client, so a backlog cannot
  produce an email blast to one customer.
- Every attempt writes/updates an ``ApprovalNotification`` audit row keyed by a
  UNIQUE idempotency key = ``f"{channel}:{client_id}:{approval_id}:{version}"``.
  The unique key prevents duplicate sends across task retries, worker restarts
  and repeated scheduler runs (DB-backed — survives a Redis flush).
- ``version`` is a hash of the approval's mutable state, so a CHANGED approval
  produces a new key and is allowed to notify again.
- A row is only marked ``sent`` when the email provider returns success; a failed
  send stays retryable. Consent (promotional suppression) + a per-client email
  setting are honoured before sending.
- Recipient / consent / send are module-level seams so tests can inject them.
- Never raises (matches repo convention).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from app.models.approval_notification import ApprovalNotification
from app.models.base import get_async_session

try:
    from app.utils.logger import setup_logger

    logger = setup_logger(__name__)
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger(__name__)

CHANNEL = "email"
_SUBJECT = "Action needed: approve your content"


def notify_enabled() -> bool:
    if os.getenv("APPROVAL_EMAIL_NOTIFY_HARD_OFF", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    return os.getenv("APPROVAL_EMAIL_NOTIFY", "0").strip().lower() in ("1", "true", "yes", "on")


def approval_client_allowlist() -> set[str]:
    """Explicit customer ids eligible for approval email. Empty = fail closed.

    Sources (union):
      1. ``APPROVAL_EMAIL_CLIENT_ALLOWLIST`` env CSV
      2. ``data/approval_email_client_allowlist.txt`` (one id per line) — so ops
         can arm a paying client without container recreate (ADR-097 pin-safe).
    """
    ids: set[str] = set()
    raw = os.getenv("APPROVAL_EMAIL_CLIENT_ALLOWLIST", "")
    for item in raw.split(","):
        client_id = item.strip()[:64]
        if client_id:
            ids.add(client_id)
    try:
        path = os.path.join("data", "approval_email_client_allowlist.txt")
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.split("#", 1)[0].strip()[:64]
                    if line:
                        ids.add(line)
    except Exception:
        pass
    return ids


async def _notification_scope(feature_service=None) -> tuple[bool, set[str]]:
    """Return ``(enabled, exact_client_ids)`` with fail-closed precedence.

    Legacy env flag + env allowlist remain compatible. Without that env flag,
    the audited runtime feature flag may arm only ``enabled_tenants``. Broad
    ``enabled_all`` still needs the legacy explicit allowlist; percentage mode
    is refused because an email recipient set must be deterministic/auditable.
    """
    if os.getenv("APPROVAL_EMAIL_NOTIFY_HARD_OFF", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False, set()
    env_allowlist = approval_client_allowlist()
    if notify_enabled():
        return True, env_allowlist
    try:
        if feature_service is None:
            from app.infrastructure.feature_flags import feature_flags

            feature_service = feature_flags
        flag = await feature_service.get_flag("approval_email_notify")
        if flag is None:
            return False, set()
        state = str(getattr(flag.state, "value", flag.state) or "").strip().lower()
        if state == "enabled_all":
            enabled = bool(env_allowlist) and bool(
                await feature_service.is_enabled("approval_email_notify")
            )
            return enabled, (env_allowlist if enabled else set())
        if state != "enabled_tenants":
            return False, set()
        candidates = {
            cid
            for raw in (getattr(flag, "enabled_tenants", None) or [])
            if (cid := str(raw or "").strip()[:64])
        }
        allowed: set[str] = set()
        for client_id in candidates:
            if await feature_service.is_enabled("approval_email_notify", tenant_id=client_id):
                allowed.add(client_id)
        return bool(allowed), allowed
    except Exception:
        return False, set()


def _client_backlog(client_id: str) -> dict:
    """`{count, oldest_days}` of this client's OPEN approvals. Never raises.

    Falls back to a bare count of 0 on any read failure, which degrades the mail
    to its old singular wording rather than blocking a send.
    """
    out = {"count": 0, "oldest_days": 0}
    try:
        from datetime import datetime as _dt
        from datetime import timezone as _tz

        from app.marketing import content_approval

        rows = content_approval.pending(str(client_id or "")) or []
        out["count"] = len(rows)
        now = _dt.now(_tz.utc)
        oldest = 0
        for r in rows:
            raw = str(r.get("created_at") or "").strip()
            if not raw:
                continue
            try:
                d = _dt.fromisoformat(raw.replace("Z", "+00:00"))
                if d.tzinfo is None:
                    d = d.replace(tzinfo=_tz.utc)
                oldest = max(oldest, int((now - d).total_seconds() // 86400))
            except Exception:
                continue
        out["oldest_days"] = oldest
    except Exception as e:
        logger.debug(f"[approval_notifier] backlog read skip: {e}")
    return out


def _backlog_phrase(backlog: dict) -> str:
    n = int(backlog.get("count") or 0)
    days = int(backlog.get("oldest_days") or 0)
    if n <= 1:
        return "You have content awaiting your approval."
    if days >= 2:
        return (
            f"You have {n} items awaiting your approval — the oldest has been waiting {days} days."
        )
    return f"You have {n} items awaiting your approval."


def _backlog_text(backlog: dict, link: str) -> str:
    return f"{_backlog_phrase(backlog)} Review and approve here: {link}"


def _backlog_html(backlog: dict, link: str) -> str:
    return f'<p>{_backlog_phrase(backlog)}</p><p><a href="{link}">Review &amp; approve</a></p>'


def deep_link(approval_id: str = "") -> str:
    """Authenticated in-app deep link to the approvals card (customer must log in)."""
    base = (os.getenv("SITE_BASE_URL") or "https://leadsgenai.in").rstrip("/")
    return f"{base}/app/customer/marketing#approvalCard"


def _approval_version(approval: dict) -> str:
    basis = json.dumps(
        {"status": approval.get("status"), "content": approval.get("content")},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


def idem_key(client_id: str, approval_id: str, version: str) -> str:
    return f"{CHANNEL}:{client_id}:{approval_id}:{version}"


# --- injectable seams -------------------------------------------------------
def _normalized_valid_email(email: str | None) -> str | None:
    normalized = str(email or "").strip().lower()
    if normalized.count("@") != 1:
        return None
    local, domain = normalized.rsplit("@", 1)
    blocked_domains = {"localhost", "example.com", "example.org", "example.net"}
    if (
        not local
        or "." not in domain
        or domain in blocked_domains
        or domain.endswith((".local", ".invalid", ".test"))
    ):
        return None
    return normalized


def _resolve_recipient(client_id: str) -> str | None:
    """Best-effort first-party customer email; exact-client and never raises."""
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        for candidate in (c.get("email"), c.get("contact_email")):
            if email := _normalized_valid_email(candidate):
                return email
    except Exception:
        pass
    try:
        from app.api.customer_auth import client_login_email

        return _normalized_valid_email(client_login_email(client_id))
    except Exception:
        return None


def _email_allowed(client_id: str, email: str) -> tuple[bool, str]:
    """(allowed, failure_category). Honours promotional suppression + a per-client
    email-notify setting. failure_category is '' when allowed."""
    normalized = _normalized_valid_email(email)
    if not normalized:
        return False, "invalid_email"
    try:
        from app.platform import email_unsub

        if email_unsub.is_suppressed(normalized):
            return False, "no_consent"
    except Exception:
        pass
    try:
        from app.marketing import clients_store

        c = clients_store.get_client(client_id) or {}
        if c.get("email_notifications") is False or c.get("approval_email_opt_out") is True:
            return False, "email_disabled"
    except Exception:
        pass
    return True, ""


async def _do_send(
    to_email: str, subject: str, html: str, text: str
) -> tuple[bool, str | None, str]:
    """Returns (ok, provider_message_id, failure_category). Never raises."""
    try:
        from app.integrations.email_sender import email_sender

        if email_sender is None:
            return False, None, "sender_unavailable"
        ok = await email_sender.send_email([to_email], subject, text, html_body=html)
        if ok:
            return True, None, ""  # sender returns bool, not a provider id
        return False, None, "provider_error"
    except Exception as e:  # pragma: no cover - defensive
        logger.warning(f"approval email send error: {type(e).__name__}")
        return False, None, "provider_exception"


# --- audit helpers ----------------------------------------------------------
def _audit(row: ApprovalNotification, note: str = "") -> dict:
    return {
        "id": row.id,
        "client_id": row.client_id,
        "approval_id": row.approval_id,
        "approval_version": row.approval_version,
        "channel": row.channel,
        "idempotency_key": row.idempotency_key,
        "status": row.status,
        "failure_category": row.failure_category,
        "provider_message_id": row.provider_message_id,
        "attempts": row.attempts,
        "attempted_at": row.attempted_at.isoformat() if row.attempted_at else None,
        "note": note,
    }


def _finalize(row: ApprovalNotification, status: str, cat: str | None) -> dict:
    row.status = status
    row.failure_category = cat
    row.completed_at = datetime.utcnow()
    return _audit(row)


async def notify_approval(
    approval: dict,
    *,
    session=None,
    send_fn=None,
    resolve_recipient=None,
    email_allowed=None,
) -> dict:
    """Idempotently notify ONE pending approval. Never raises; returns an audit dict.

    Dedupe: a row with the same idempotency key already 'sent' short-circuits with
    no send. 'failed'/'attempted' rows are retried. A changed approval version has a
    different key and is treated as a new notification.
    """
    resolve_recipient = resolve_recipient or _resolve_recipient
    email_allowed = email_allowed or _email_allowed
    send_fn = send_fn or _do_send

    client_id = str(approval.get("client_id") or "")
    approval_id = str(approval.get("id") or "")
    if not approval_id:
        return {"status": "skipped", "failure_category": "no_approval_id"}
    version = _approval_version(approval)
    key = idem_key(client_id, approval_id, version)

    async def _run(sess) -> dict:
        existing = (
            await sess.execute(
                select(ApprovalNotification).where(ApprovalNotification.idempotency_key == key)
            )
        ).scalar_one_or_none()
        if existing and existing.status == "sent":
            return _audit(existing, note="duplicate_suppressed")

        row = existing or ApprovalNotification(
            id=uuid4().hex,
            client_id=client_id,
            approval_id=approval_id,
            approval_version=version,
            channel=CHANNEL,
            idempotency_key=key,
            status="attempted",
            attempts=0,
        )
        row.attempts = (row.attempts or 0) + 1
        row.attempted_at = datetime.utcnow()
        row.status = "attempted"
        row.completed_at = None
        if existing is None:
            sess.add(row)
        try:
            await sess.flush()  # reserve the unique key (dedupe vs concurrent runs)
        except Exception:
            # Unique-key race: another attempt won. Re-read and honour its result.
            await sess.rollback()
            other = (
                await sess.execute(
                    select(ApprovalNotification).where(ApprovalNotification.idempotency_key == key)
                )
            ).scalar_one_or_none()
            if other is not None:
                return _audit(other, note="dedupe_race")
            raise

        email = resolve_recipient(client_id)
        if not email:
            return _finalize(row, "skipped", "no_email")
        allowed, cat = email_allowed(client_id, email)
        if not allowed:
            return _finalize(row, "skipped", cat or "no_consent")

        link = deep_link(approval_id)
        # Queue-aware wording. The idempotency key is per (approval, version,
        # channel), so an item is announced EXACTLY ONCE and never followed up;
        # a customer who ignores that single mail is never told about it again
        # and the queue grows in silence. Prod 2026-08-09: 36 mails sent to the
        # one paying customer over four weeks, all delivered, 20 items still
        # pending — the mails were arriving, they just each said "you have
        # content" and never "you have 20 waiting, oldest 17 days".
        # This does not add sends or change cadence; it makes the sends that
        # already happen carry the state of the queue.
        backlog = _client_backlog(client_id)
        text = _backlog_text(backlog, link)
        html = _backlog_html(backlog, link)
        ok, pmid, fcat = await send_fn(email, _SUBJECT, html, text)
        if ok:
            row.provider_message_id = pmid
            return _finalize(row, "sent", None)
        return _finalize(row, "failed", fcat or "provider_error")

    try:
        if session is not None:
            result = await _run(session)
        else:
            async with get_async_session() as sess:
                result = await _run(sess)
    except Exception as e:
        logger.warning(f"notify_approval error: {type(e).__name__}")
        return {
            "status": "failed",
            "failure_category": "internal_error",
            "approval_id": approval_id,
        }

    # Per-customer ledger mirror (best-effort, idempotent).
    try:
        from app.marketing import delivery_ledger

        delivery_ledger.log_event(
            client_id,
            "approval_reminded",
            detail=f"email:{result.get('status')}",
            meta={
                "approval_id": approval_id,
                "channel": CHANNEL,
                "result": result.get("status"),
                "failure_category": result.get("failure_category"),
            },
            key=f"approval_email:{key}",
        )
    except Exception:
        pass
    return result


async def notify_pending_approvals(
    *,
    limit: int = 200,
    session=None,
    per_item_timeout: float = 20.0,
    notification_scope: tuple[bool, set[str]] | None = None,
    **kw,
) -> dict:
    """Scoped sweep over pending approvals. Inert unless env/runtime gate is on.

    - Explicit client allowlist is mandatory; empty means no recipients.
    - At most one reminder per client per sweep (newest pending item wins).
    - Bounded client batch (``limit``) and bounded per-item timeout.
    - One client's failure/timeout NEVER stops the sweep (each item is isolated).
    - Tenant isolation: each approval carries its own client_id and the recipient is
      resolved from THAT client, so no cross-tenant delivery is possible.
    """
    enabled, allowlist = notification_scope or await _notification_scope()
    counts = {
        "enabled": enabled,
        "seen": 0,
        "attempted": 0,
        "sent": 0,
        "skipped": 0,
        "failed": 0,
        "not_allowlisted": 0,
        "duplicate_client_suppressed": 0,
        # Idempotency pe short-circuit hue items. `sent` se ALAG rakhna zaroori
        # hai: `notify_approval` dedupe pe purani row ka audit lautata hai jiska
        # `status` "sent" hota hai — use `sent` ginna matlab "customer ko email
        # gaya" ka jhootha haan (2026-07-14 postmortem).
        "deduplicated": 0,
        "last_failure_category": None,
    }
    if not counts["enabled"]:
        return counts
    try:
        from app.marketing import content_approval

        pending = content_approval.pending("") or []
    except Exception:
        pending = []

    selected: list[dict] = []
    seen_clients: set[str] = set()
    max_clients = max(0, int(limit))
    for approval in pending:
        client_id = str(approval.get("client_id") or "").strip()
        if client_id not in allowlist:
            counts["not_allowlisted"] += 1
            continue
        if client_id in seen_clients:
            counts["duplicate_client_suppressed"] += 1
            continue
        seen_clients.add(client_id)
        if len(selected) < max_clients:
            selected.append(approval)

    for approval in selected:
        try:
            r = await asyncio.wait_for(
                notify_approval(approval, session=session, **kw), timeout=per_item_timeout
            )
        except asyncio.TimeoutError:
            r = {"status": "failed", "failure_category": "timeout"}
        except Exception:
            r = {"status": "failed", "failure_category": "internal_error"}
        counts["seen"] += 1
        # Dedupe short-circuit: koi provider call NAHI hua. `notify_approval`
        # is case me purani row ka audit lautata hai (status="sent"), isliye
        # status pe bharosa mat karo — `note` hi sach batata hai.
        if str(r.get("note") or "") in ("duplicate_suppressed", "dedupe_race"):
            counts["deduplicated"] += 1
            continue
        counts["attempted"] += 1
        st = r.get("status", "skipped")
        counts[st] = counts.get(st, 0) + 1
        if st in ("failed", "skipped") and r.get("failure_category"):
            counts["last_failure_category"] = r.get("failure_category")
    return counts


# --- operational health -----------------------------------------------------
_HEALTH: dict = {
    "last_run": None,
    "runs": 0,
    "seen": 0,
    "attempted": 0,
    "sent": 0,
    "skipped": 0,
    "failed": 0,
    "last_failure_category": None,
    "locked_out": 0,
}


def get_health() -> dict:
    """Admin-visible sweep health. Contains only aggregate counts + a sanitized
    failure category — never email addresses, secrets or message bodies."""
    h = dict(_HEALTH)
    h["enabled"] = bool(h.get("enabled", notify_enabled()))
    return h


def _record_run(result: dict) -> None:
    _HEALTH["enabled"] = bool(result.get("enabled"))
    _HEALTH["runs"] += 1
    _HEALTH["last_run"] = datetime.utcnow().isoformat()
    _HEALTH["seen"] = result.get("seen", 0)
    _HEALTH["attempted"] = result.get("attempted", result.get("seen", 0))
    _HEALTH["sent"] = result.get("sent", 0)
    _HEALTH["skipped"] = result.get("skipped", 0)
    _HEALTH["failed"] = result.get("failed", 0)
    _HEALTH["last_failure_category"] = result.get("last_failure_category")


# --- single-flight lock (distributed via Redis, process-local fallback) -----
_LOCAL_LOCK = {"held": False}


class SweepLock:
    """Non-blocking single-flight lock. Prefers Redis ``SET NX EX`` so overlapping
    invocations across the celery worker AND the in-process scheduler are suppressed;
    falls back to a process-local flag when Redis is unavailable. ``acquire()`` returns
    False immediately if the lock is already held."""

    def __init__(self, key: str = "approval_notify:sweep_lock", ttl: int = 300):
        self.key = key
        self.ttl = ttl
        self._token: str | None = None
        self._local = False

    async def acquire(self) -> bool:
        token = uuid4().hex
        try:
            from app.cache import get_redis_client

            r = await get_redis_client()
            if r is not None:
                ok = await r.set(self.key, token, nx=True, ex=self.ttl)
                if ok:
                    self._token = token
                    return True
                return False
        except Exception:
            pass
        if _LOCAL_LOCK["held"]:
            return False
        _LOCAL_LOCK["held"] = True
        self._local = True
        return True

    async def release(self) -> None:
        try:
            if self._token is not None:
                from app.cache import get_redis_client

                r = await get_redis_client()
                if r is not None:
                    try:
                        cur = await r.get(self.key)
                        cur_s = cur.decode() if isinstance(cur, bytes | bytearray) else cur
                        if cur_s == self._token:
                            await r.delete(self.key)
                    except Exception:
                        pass
        finally:
            if self._local:
                _LOCAL_LOCK["held"] = False
            self._token = None
            self._local = False


async def run_approval_email_sweep(
    *, batch_size: int = 100, per_item_timeout: float = 20.0, session=None, lock=None, **kw
) -> dict:
    """Scheduler entrypoint: single-flight, bounded pending-approval email sweep.

    Inert unless legacy env or tenant-scoped runtime flag is on. Overlapping runs
    are suppressed by the lock (``skipped_lock=True``). Never raises.
    """
    scope = await _notification_scope()
    if not scope[0]:
        out = {
            "enabled": False,
            "skipped_lock": False,
            "seen": 0,
            "sent": 0,
            "skipped": 0,
            "failed": 0,
        }
        _record_run(out)
        return out
    lock = lock if lock is not None else SweepLock()
    try:
        acquired = await lock.acquire()
    except Exception:
        acquired = True  # fail-open: better to run than to silently stall
    if not acquired:
        _HEALTH["locked_out"] += 1
        out = {"skipped_lock": True}
        out.update(get_health())
        return out
    try:
        result = await notify_pending_approvals(
            limit=batch_size,
            session=session,
            per_item_timeout=per_item_timeout,
            notification_scope=scope,
            **kw,
        )
        _record_run(result)
        result["skipped_lock"] = False
        return result
    except Exception as e:
        logger.warning(f"approval sweep error: {type(e).__name__}")
        return {"enabled": True, "skipped_lock": False, "error": True}
    finally:
        try:
            await lock.release()
        except Exception:
            pass
